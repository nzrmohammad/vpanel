import re
import json
import logging
import os
import urllib.parse
import random
from datetime import datetime, date, timedelta
from typing import Union, Optional, Dict, Any, List

import pytz
import jdatetime
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from bot.config import PROGRESS_COLORS, LOYALTY_REWARDS, RANDOM_SERVERS_COUNT, EMOJIS
from bot.database import db
from bot.db.base import UserUUID, User, ConfigTemplate, ServerCategory, Plan

logger = logging.getLogger(__name__)
bot = None

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def initialize_utils(b_instance):
    global bot
    bot = b_instance

# --- توابع کمکی تاریخ و زمان (Sync) ---

def to_shamsi(dt: Optional[Union[datetime, date, str]], include_time: bool = False, month_only: bool = False) -> str:
    """تبدیل تاریخ میلادی به شمسی."""
    if not dt: return "نامشخص"
    try:
        gregorian_dt = None
        if isinstance(dt, datetime):
            gregorian_dt = dt
        elif isinstance(dt, date):
            gregorian_dt = datetime(dt.year, dt.month, dt.day)
        elif isinstance(dt, str):
            try:
                gregorian_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except ValueError:
                if '.' in dt: dt = dt.split('.')[0]
                gregorian_dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')

        if not gregorian_dt: return "نامشخص"

        if gregorian_dt.tzinfo is None:
            gregorian_dt = pytz.utc.localize(gregorian_dt)
        
        tehran_tz = pytz.timezone("Asia/Tehran")
        local_dt = gregorian_dt.astimezone(tehran_tz)
        dt_shamsi = jdatetime.datetime.fromgregorian(datetime=local_dt)
        
        if month_only:
            return f"{jdatetime.date.j_months_fa[dt_shamsi.month - 1]} {dt_shamsi.year}"
        if include_time:
            return dt_shamsi.strftime("%Y/%m/%d %H:%M:%S")
        return dt_shamsi.strftime("%Y/%m/%d")
    except Exception as e:
        logger.error(f"Error in to_shamsi: {e}")
        return "خطا"

def format_relative_time(dt: Optional[datetime]) -> str:
    """تبدیل زمان به صورت نسبی (مثلاً: ۲ ساعت پیش)."""
    if not dt or not isinstance(dt, datetime): return "هرگز"
    now = datetime.now(pytz.utc)
    dt_utc = dt if dt.tzinfo else pytz.utc.localize(dt)
    delta = now - dt_utc
    seconds = delta.total_seconds()
    if seconds < 60: return "همین الان"
    if seconds < 3600: return f"{int(seconds / 60)} دقیقه پیش"
    if seconds < 86400: return f"{int(seconds / 3600)} ساعت پیش"
    if seconds < 172800: return "دیروز"
    return f"{delta.days} روز پیش"

def days_until_next_birthday(birth_date: Optional[date]) -> Optional[int]:
    if not birth_date: return None
    try:
        today = datetime.now().date()
        if isinstance(birth_date, datetime): birth_date = birth_date.date()
        next_birthday = birth_date.replace(year=today.year)
        if next_birthday < today: next_birthday = next_birthday.replace(year=today.year + 1)
        return (next_birthday - today).days
    except (ValueError, TypeError): return None

def format_daily_usage(gb: float) -> str:
    if gb < 0: return "0 MB"
    if gb < 1: return f"{gb * 1024:.0f} MB"
    return f"{gb:.2f} GB"

def format_usage(usage_gb: float) -> str:
    return format_daily_usage(usage_gb)

# --- توابع پردازش متن و داده (Sync) ---

def validate_uuid(uuid_str: str) -> bool:
    return bool(_UUID_RE.match(uuid_str.strip())) if uuid_str else False

def safe_float(value, default: float = 0.0) -> float:
    try: return float(value)
    except (ValueError, TypeError): return default

def escape_markdown(text: Union[str, int, float]) -> str:
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def create_progress_bar(percent: float, length: int = 15) -> str:
    percent = max(0, min(100, percent))
    filled_count = int(percent / 100 * length)
    filled_bar = '█' * filled_count
    empty_bar = '░' * (length - filled_count)
    return f"`{filled_bar}{empty_bar} {percent:.1f}%`"

def parse_volume_string(volume_str: str) -> int:
    if not isinstance(volume_str, str): return 0
    numbers = re.findall(r'\d+', volume_str)
    return int(numbers[0]) if numbers else 0

def parse_user_agent(user_agent: str) -> Optional[Dict[str, Optional[str]]]:
    """تحلیل User-Agent برای تشخیص نوع کلاینت و سیستم عامل."""
    if not user_agent or "TelegramBot" in user_agent: return None
    
    # الگوهای ساده شده برای تشخیص کلاینت‌ها
    patterns = [
        (r"v2rayNG/([\d.]+)", "v2rayNG", "Android"),
        (r"v2rayN/([\d.]+)", "v2rayN", "Windows"),
        (r"HiddifyNext/([\d.]+)", "Hiddify", "Unknown"),
        (r"NekoBox/([\d.]+)", "NekoBox", "Android"),
        (r"Streisand/([\d.]+)", "Streisand", "iOS"),
        (r"Shadowrocket/([\d.]+)", "Shadowrocket", "iOS"),
        (r"FoXray/([\d.]+)", "FoXray", "iOS"),
    ]
    
    for pattern, client_name, os_name in patterns:
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if match:
            return {"client": client_name, "version": match.group(1), "os": os_name}
            
    # فال‌بک برای موارد ناشناس
    return {"client": "Unknown", "version": None, "os": "Unknown"}

# --- توابع Async مربوط به دیتابیس و تلگرام ---

async def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    """ویرایش پیام با هندل کردن خطاها (Async)."""
    if not bot: return
    try:
        kwargs.setdefault('parse_mode', 'MarkdownV2')
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, **kwargs)
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            logger.error(f"Safe edit failed for {chat_id}: {e}")

async def get_service_plans() -> List[dict]:
    """
    دریافت پلن‌ها از دیتابیس (جایگزین load_service_plans جیسونی).
    """
    try:
        async with db.get_session() as session:
            stmt = select(Plan).where(Plan.is_active == True).order_by(Plan.display_order, Plan.price)
            result = await session.execute(stmt)
            plans = result.scalars().all()
            
            # تبدیل به دیکشنری برای سازگاری با کدهای قبلی
            return [
                {
                    'id': p.id,
                    'name': p.name,
                    'price': p.price,
                    'total_volume': f"{p.volume_gb} GB", # فرمت قدیمی برای سازگاری
                    'volume_gb': p.volume_gb,
                    'duration': p.days, # فرمت قدیمی
                    'days': p.days,
                    'allowed_categories': p.allowed_categories,
                    # تعیین نوع برای نمایش در منوها (usa, germany, combined, ...)
                    'type': 'combined' if len(p.allowed_categories or []) > 1 else (p.allowed_categories[0] if p.allowed_categories else 'general')
                }
                for p in plans
            ]
    except Exception as e:
        logger.error(f"Error fetching plans: {e}")
        return []

# --- توابع اصلی تولید کانفیگ و اطلاعات (Async & Dynamic) ---

async def create_info_config(user_uuid: str) -> Optional[str]:
    """
    تولید لینک کانفیگ "اطلاعات" که حجم و انقضا را نشان می‌دهد.
    """
    from . import combined_handler
    
    # دریافت اطلاعات ترکیبی (لایو)
    info = await combined_handler.get_combined_user_info(user_uuid)
    if not info: return None

    # دریافت اطلاعات دسته‌بندی‌ها برای نمایش پرچم
    async with db.get_session() as session:
        # دریافت تنظیمات کانفیگ و دسترسی‌ها
        stmt = select(UserUUID).where(UserUUID.uuid == user_uuid).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        user_record = result.scalar_one_or_none()
        
        if not user_record: return None
        
        # نگاشت دسته‌بندی پنل‌ها
        allowed_cats = set()
        if user_record.allowed_panels:
            allowed_cats = {p.category for p in user_record.allowed_panels if p.category}
            
        # دریافت ایموجی‌ها
        cat_emojis = {}
        if allowed_cats:
            stmt_cat = select(ServerCategory).where(ServerCategory.code.in_(allowed_cats))
            res_cat = await session.execute(stmt_cat)
            for c in res_cat.scalars():
                cat_emojis[c.code] = c.emoji

    parts = []
    breakdown = info.get('breakdown', {})
    
    # گروه‌بندی حجم‌ها بر اساس دسته‌بندی
    cat_stats = {} # {'de': {'usage': 10, 'limit': 50}, ...}
    
    for p_name, p_detail in breakdown.items():
        # پیدا کردن دسته‌بندی این پنل (نیاز به مپ نام پنل به دسته داریم که در بالا نگرفتیم)
        # راه حل: در breakdown باید نوع پنل یا نامش را با دیتابیس تطبیق دهیم
        # برای سادگی فعلا از type استفاده می‌کنیم یا کل را نشان می‌دهیم
        # اما برای دقت بالا، بهتر است total را نشان دهیم
        pass

    # نمایش حجم کل (ساده و تمیز)
    total_usage = info.get('current_usage_GB', 0)
    total_limit = info.get('usage_limit_GB', 0)
    limit_str = f"{total_limit:.0f}" if total_limit > 0 else '∞'
    parts.append(f"📊 {total_usage:.1f}/{limit_str} GB")

    # نمایش انقضا
    days_left = info.get('expire')
    if days_left is not None:
        days_str = f"{days_left} روز" if days_left >= 0 else "منقضی"
        parts.append(f"📅 {days_str}")

    if not parts: return None
        
    final_name = " | ".join(parts)
    encoded_name = urllib.parse.quote(final_name)
    return f"vless://00000000-0000-0000-0000-000000000000@1.1.1.1:443?type=ws&path=/&security=tls#{encoded_name}"

async def generate_user_subscription_configs(user_main_uuid: str, user_id: int) -> list[str]:
    """
    تولید لیست کامل کانفیگ‌های اشتراک کاربر (شامل Info و کانفیگ‌های اصلی).
    کاملاً داینامیک و Async.
    """
    from . import combined_handler # جلوگیری از ایمپورت چرخشی

    # 1. دریافت اطلاعات پایه
    async with db.get_session() as session:
        # دریافت تنظیمات کاربر
        user = await session.get(User, user_id)
        user_settings = user.settings if user else {}
        show_info_conf = user_settings.get('show_info_config', True)

        # دریافت رکورد UUID و دسترسی‌ها
        stmt = select(UserUUID).where(UserUUID.uuid == user_main_uuid).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        user_record = result.scalar_one_or_none()

        if not user_record: return []

        allowed_cats = {p.category for p in user_record.allowed_panels if p.category}
        is_vip = user_record.is_vip
        user_name = user_record.name or "User"

        # دریافت تمام قالب‌های کانفیگ فعال
        stmt_tpl = select(ConfigTemplate).where(ConfigTemplate.is_active == True).order_by(ConfigTemplate.id)
        result_tpl = await session.execute(stmt_tpl)
        all_templates = result_tpl.scalars().all()

    final_configs = []

    # 2. افزودن کانفیگ Info (در صورت فعال بودن)
    if show_info_conf:
        info_conf = await create_info_config(user_main_uuid)
        if info_conf:
            final_configs.append(info_conf)

    # 3. فیلتر و انتخاب کانفیگ‌ها
    eligible_templates = []
    for tpl in all_templates:
        # فیلتر VIP
        if tpl.is_special and not is_vip:
            continue
        
        # فیلتر دسته‌بندی (اگر قالب مختص کشور خاصی است)
        if tpl.server_category_code and tpl.server_category_code not in allowed_cats:
            continue
            
        eligible_templates.append(tpl)

    # 4. مدیریت استخر تصادفی (Random Pool)
    fixed_templates = [t for t in eligible_templates if not t.is_random_pool]
    pool_templates = [t for t in eligible_templates if t.is_random_pool]
    
    selected_pool = []
    if RANDOM_SERVERS_COUNT > 0 and len(pool_templates) > RANDOM_SERVERS_COUNT:
        selected_pool = random.sample(pool_templates, RANDOM_SERVERS_COUNT)
    else:
        selected_pool = pool_templates

    # ترکیب و مرتب‌سازی نهایی
    final_selection = fixed_templates + selected_pool
    final_selection.sort(key=lambda x: x.id) # حفظ ترتیب دیتابیس

    # 5. جایگزینی متغیرها
    for tpl in final_selection:
        config_str = tpl.template_str
        # جایگزینی UUID
        if "{new_uuid}" in config_str:
            config_str = config_str.replace("{new_uuid}", user_main_uuid)
        # جایگزینی نام
        if "{name}" in config_str:
            # انکد کردن نام برای URL
            enc_name = urllib.parse.quote(user_name)
            config_str = config_str.replace("{name}", enc_name)
            
        final_configs.append(config_str)

    return final_configs

async def get_loyalty_progress_message(user_id: int) -> Optional[Dict[str, Any]]:
    """محاسبه وضعیت وفاداری کاربر (Async)."""
    if not LOYALTY_REWARDS: return None

    try:
        user_uuids = await db.uuids(user_id)
        if not user_uuids: return None
        
        # استفاده از اولین سرویس برای محاسبه سابقه
        uuid_id = user_uuids[0].id
        history = await db.get_user_payment_history(uuid_id)
        payment_count = len(history)

        next_tier = 0
        reward = None
        
        for tier in sorted(LOYALTY_REWARDS.keys()):
            if payment_count < tier:
                next_tier = tier
                reward = LOYALTY_REWARDS[tier]
                break
        
        if not reward: return None

        return {
            "payment_count": payment_count,
            "renewals_left": next_tier - payment_count,
            "gb_reward": reward.get("gb", 0),
            "days_reward": reward.get("days", 0)
        }
    except Exception as e:
        logger.error(f"Loyalty check error: {e}")
        return None

def find_best_plan_upgrade(current_usage: float, current_limit: float, all_plans: list) -> Dict[str, Any]:
    """پیشنهاد ارتقا (Sync - محاسباتی)."""
    if not all_plans: return {}
    
    recommendations = {}
    # گروه‌بندی پلن‌ها بر اساس نوع
    grouped_plans = {}
    for p in all_plans:
        p_type = p.get('type', 'general')
        if p_type not in grouped_plans: grouped_plans[p_type] = []
        grouped_plans[p_type].append(p)

    for p_type, plans in grouped_plans.items():
        # پیدا کردن پلن‌هایی که حجمشان بیشتر از مصرف و لیمیت فعلی است
        upgrades = [
            p for p in plans 
            if p.get('volume_gb', 0) > current_usage and p.get('volume_gb', 0) > current_limit
        ]
        if upgrades:
            # انتخاب ارزان‌ترین گزینه مناسب
            upgrades.sort(key=lambda x: x.get('price', 0))
            recommendations[p_type] = upgrades[0]
            
    return recommendations