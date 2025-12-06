# bot/utils.py

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
from .config import PROGRESS_COLORS, LOYALTY_REWARDS, RANDOM_SERVERS_COUNT

logger = logging.getLogger(__name__)
bot = None

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def initialize_utils(b_instance):
    global bot
    bot = b_instance

# ==============================================================================
# Sync Helper Functions (توابع محاسباتی و فرمت‌بندی - بدون نیاز به دیتابیس)
# ==============================================================================

def to_shamsi(dt: Optional[Union[datetime, date, str]], include_time: bool = False, month_only: bool = False) -> str:
    """
    تبدیل تاریخ میلادی به شمسی با مدیریت صحیح تایم‌زون.
    """
    if not dt:
        return "نامشخص"
        
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

def format_usage(usage_gb: float) -> str:
    if usage_gb is None: return "0 MB"
    if usage_gb < 1: return f"{usage_gb * 1024:.0f} MB"
    return f"{usage_gb:.2f} GB"

def format_daily_usage(gb: float) -> str:
    return format_usage(gb)

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

def format_currency(amount: float) -> str:
    try: return f"{int(amount):,}"
    except (ValueError, TypeError): return "0"

def format_date(dt) -> str:
    return to_shamsi(dt, include_time=True)

def get_status_emoji(is_active: bool) -> str:
    return "✅" if is_active else "❌"

def bytes_to_gb(bytes_value: int) -> float:
    if not bytes_value: return 0.0
    return round(bytes_value / (1024**3), 2)

def find_best_plan_upgrade(current_usage_gb: float, current_limit_gb: float, all_plans: list) -> Dict[str, Any]:
    if not all_plans: return {}
    recommendations = {}
    plan_types = ['combined', 'germany', 'france', 'turkey']
    for p_type in plan_types:
        suitable_upgrades = []
        for plan in all_plans:
            # بررسی نوع پلن (میتواند کلید type یا server_location باشد، بسته به ساختار دیتابیس)
            p_cat = plan.get('type') or ('combined' if len(plan.get('allowed_categories') or []) > 1 else 'general')
            
            if p_cat == p_type or (p_type == 'combined' and len(plan.get('allowed_categories') or []) > 1):
                vol = plan.get('volume_gb', 0)
                if vol > current_usage_gb and vol > current_limit_gb:
                    suitable_upgrades.append(plan)
        
        if suitable_upgrades:
            suitable_upgrades.sort(key=lambda x: x.get('price', 0))
            recommendations[p_type] = suitable_upgrades[0]
            
    return recommendations

# --- User Agent Parsers ---

def parse_user_agent(user_agent: str) -> Optional[Dict[str, Optional[str]]]:
    if not user_agent or "TelegramBot" in user_agent: return None
    
    CLIENT_PATTERNS = [
        {"regex": re.compile(r"^(Happ)/([\d.]+)(?:/(\w+))?"), "extractor": lambda m: {"client": "Happ", "version": m.group(2), "os": m.group(3).capitalize() if m.group(3) else "Unknown"}},
        {"regex": re.compile(r"^(NekoBox)/(\w+)/([\d.]+)"), "extractor": lambda m: {"client": "NekoBox", "version": m.group(3), "os": m.group(2).upper()}},
        {"regex": re.compile(r"^(v2box|V2Box)/([\d.]+)$"), "extractor": lambda m: {"client": "V2Box", "version": m.group(2), "os": "Unknown"}},
        {"regex": re.compile(r"^(V2Box)/([\d.]+)\s+\((Android)\s+([\d.]+)\)"), "extractor": lambda m: {"client": "V2Box", "version": m.group(2), "os": f"Android {m.group(4)}"}},
        {"regex": re.compile(r"^(V2Box)\s+([\d.]+);(IOS)\s+([\d.]+)"), "extractor": lambda m: {"client": m.group(1), "version": m.group(2), "os": f"iOS {m.group(4)}"}},
        {"regex": re.compile(r"CFNetwork/.*? Darwin/([\d.]+)"), "extractor": lambda m: _extract_apple_client_details(user_agent, m)},
        {"regex": re.compile(r'HiddifyNextX?/([\d.]+)\s+\((\w+)\)'), "extractor": lambda m: {"client": "Hiddify", "version": m.group(1), "os": m.group(2).capitalize()}},
        {"regex": re.compile(r"v2rayNG/([\d.]+)"), "extractor": lambda m: {"client": "v2rayNG", "version": m.group(1), "os": "Android"}},
        {"regex": re.compile(r"v2rayN/([\d.]+)"), "extractor": lambda m: {"client": "v2rayN", "version": m.group(1), "os": "Windows"}},
        {"regex": re.compile(r"nekoray/([\d.]+)"), "extractor": lambda m: {"client": "NekoRay", "version": m.group(1), "os": "Linux"}},
        {"regex": re.compile(r'Throne/([\d.]+)\s+\((\w+);\s*(\w+)\)'), "extractor": lambda m: {"client": "Throne", "version": m.group(1), "os": f"{m.group(2).capitalize()} {m.group(3)}"}},
        {"regex": re.compile(r'NapsternetV/([\d.]+)'), "extractor": lambda m: {"client": "NapsternetV", "version": m.group(1), "os": "Android" if 'android' in user_agent.lower() else "iOS" if 'ios' in user_agent.lower() else None}},
        {"regex": re.compile(r"(Chrome|Firefox|Safari|OPR)/([\d.]+)"), "extractor": lambda m: _extract_browser_details(user_agent, m)}
    ]

    for pattern in CLIENT_PATTERNS:
        match = pattern["regex"].search(user_agent)
        if match:
            result = pattern["extractor"](match)
            if result: return result

    generic_client = user_agent.split('/')[0].split(' ')[0]
    return {"client": generic_client, "os": "Unknown", "version": None}

def _extract_apple_client_details(user_agent: str, darwin_match: re.Match) -> Dict[str, Optional[str]]:
    client_name, client_version = "Unknown Apple Client", None
    known_clients = ["Shadowrocket", "Stash", "Quantumult%20X", "Loon", "V2Box", "Streisand", "Fair%20VPN", "Happ"]
    for client in known_clients:
        if user_agent.startswith(client.replace('%20', ' ')):
            match = re.search(r"^{}/([\d.]+)".format(re.escape(client)), user_agent.replace('%20', ' '))
            if match:
                client_name = client.replace('%20', ' ')
                client_version = match.group(1)
                break
    
    darwin_version = int(darwin_match.group(1).split('.')[0])
    darwin_to_os = { 25: "26", 24: "18", 23: "17", 22: "16", 21: "15", 20: "14", 19: "13" }
    os_version = darwin_to_os.get(darwin_version)
    os_name = "macOS" if "Mac" in user_agent else "iOS"
    
    device_model_match = re.search(r'\((iPhone|iPad|Mac)[^;]*;', user_agent)
    if device_model_match:
        os_name = device_model_match.group(1).replace("iPhone", "iOS").replace("iPad", "iPadOS")

    return {"client": client_name, "os": f"{os_name} {os_version}" if os_version else os_name, "version": client_version}

def _extract_browser_details(user_agent: str, browser_match: re.Match) -> Optional[Dict[str, Optional[str]]]:
    browser_name = browser_match.group(1)
    if browser_name == 'OPR': browser_name = 'Opera'
    if browser_name == 'Safari' and 'Chrome' in user_agent: return None

    os_str = "Unknown OS"
    if "Windows NT 10.0" in user_agent: os_str = "Windows 10/11"
    elif "Windows" in user_agent: os_str = "Windows"
    elif "Android" in user_agent:
        android_match = re.search(r"Android ([\d.]+)", user_agent)
        os_str = android_match.group(0) if android_match else "Android"
    elif "Mac OS X" in user_agent:
        mac_match = re.search(r"Mac OS X ([\d_]+)", user_agent)
        os_str = f"macOS {mac_match.group(1).replace('_', '.')}" if mac_match else "macOS"
    elif "Linux" in user_agent: os_str = "Linux"
    
    return {"client": browser_name, "os": os_str, "version": browser_match.group(2)}

# ==============================================================================
# Async Helper Functions (توابع نیازمند دیتابیس یا API - حتما باید await شوند)
# ==============================================================================

async def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    if not bot: return
    try:
        kwargs.setdefault('parse_mode', 'MarkdownV2')
        await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id, **kwargs)
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            logger.error(f"Safe edit failed: {e}")

async def get_service_plans() -> List[dict]:
    """دریافت پلن‌ها از دیتابیس به صورت Async"""
    # Import داخل تابع برای جلوگیری از Circular Import
    from .database import db 
    try:
        # متد get_all_plans قبلاً در ProductDB تعریف شده است
        return await db.get_all_plans(active_only=True)
    except Exception as e:
        logger.error(f"Error fetching plans: {e}")
        return []

async def get_processed_user_data(uuid: str) -> Optional[dict]:
    """دریافت داده‌های پردازش شده کاربر به صورت Async"""
    from .database import db
    from . import combined_handler
    
    # ✅ استفاده از await برای توابع async
    info = await combined_handler.get_combined_user_info(uuid)
    if not info: return None

    processed_info = info.copy()
    breakdown = info.get('breakdown', {})
    
    processed_info['on_hiddify'] = 'hiddify' in breakdown and bool(breakdown.get('hiddify'))
    processed_info['on_marzban'] = 'marzban' in breakdown and bool(breakdown.get('marzban'))
    processed_info['last_online_relative'] = format_relative_time(info.get('last_online'))
    
    # دریافت مصرف روزانه از دیتابیس (Async)
    daily_usage = await db.get_usage_since_midnight_by_uuid(uuid)

    if processed_info['on_hiddify']:
        h_info = breakdown['hiddify']
        h_info['last_online_shamsi'] = to_shamsi(h_info.get('data', {}).get('last_online'), include_time=True)
        h_info['daily_usage_formatted'] = format_usage(daily_usage.get('hiddify', 0.0))

    if processed_info['on_marzban']:
        m_info = breakdown['marzban']
        m_info['last_online_shamsi'] = to_shamsi(m_info.get('data', {}).get('last_online'), include_time=True)
        m_info['daily_usage_formatted'] = format_usage(daily_usage.get('marzban', 0.0))

    expire_days = info.get('expire')
    if expire_days is not None and expire_days >= 0:
        expire_date = datetime.now() + timedelta(days=expire_days)
        processed_info['expire_shamsi'] = to_shamsi(expire_date)
    else:
        processed_info['expire_shamsi'] = "نامحدود" if expire_days is None else "منقضی"

    user_record = await db.get_user_uuid_record(uuid) # ✅ await
    if user_record:
        processed_info['created_at'] = user_record.get('created_at')

    return processed_info

async def create_info_config(user_uuid: str) -> Optional[str]:
    """تولید کانفیگ اطلاع‌رسانی (Async)"""
    from .database import db
    from . import combined_handler

    # ✅ await
    info = await combined_handler.get_combined_user_info(user_uuid)
    if not info: return None

    # ✅ await
    user_record = await db.get_user_uuid_record(user_uuid)
    if not user_record: return None
    
    # دریافت دسترسی‌ها از دیتابیس (از طریق متد جدید یا محاسبه از روی پنل‌های مجاز)
    # فرض بر این است که در user_record (دیکشنری) کلیدها وجود ندارند، باید محاسبه شوند
    # اما اگر متد get_user_uuid_record دیکشنری ساده برمی‌گرداند، باید دسترسی‌ها را جدا بگیریم
    # راه ساده‌تر: استفاده از متد get_user_access_rights اگر user_id داشته باشیم
    # اما اینجا فقط UUID داریم. بهتر است از روی پنل‌های موجود در info استفاده کنیم یا دستی چک کنیم.
    
    # راه حل: استفاده از متد get_user_allowed_panels برای UUID
    uuid_id = await db.get_uuid_id_by_uuid(user_uuid)
    allowed_panels = await db.get_user_allowed_panels(uuid_id) if uuid_id else []
    allowed_cats = {p['category'] for p in allowed_panels if p.get('category')}

    parts = []
    breakdown = info.get('breakdown', {})
    
    # استخراج اطلاعات از breakdown
    # نکته: breakdown کلیدش نام پنل است.
    
    # نمایش پرچم‌ها بر اساس دسترسی
    flags = []
    cat_emoji_map = {
        'de': '🇩🇪', 'fr': '🇫🇷', 'tr': '🇹🇷', 'us': '🇺🇸', 
        'ro': '🇷🇴', 'fi': '🇫🇮', 'ir': '🇮🇷'
    }
    
    for cat in allowed_cats:
        emoji = cat_emoji_map.get(cat)
        if emoji: flags.append(emoji)
        
    flag_str = "".join(flags)

    total_usage = info.get('current_usage_GB', 0)
    total_limit = info.get('usage_limit_GB', 0)
    limit_str = f"{total_limit:.0f}" if total_limit > 0 else '∞'
    
    # بخش اول: پرچم‌ها و حجم
    usage_text = f"{total_usage:.1f}/{limit_str}GB"
    if flag_str:
        parts.append(f"{flag_str} {usage_text}")
    else:
        parts.append(f"📊 {usage_text}")

    # بخش دوم: انقضا
    days_left = info.get('expire')
    if days_left is not None:
        days_str = str(days_left) if days_left >= 0 else 'پایان'
        parts.append(f"📅 {days_str}")

    if not parts: return None
        
    final_name_parts = " | ".join(parts)
    encoded_name = urllib.parse.quote(final_name_parts)
    return f"vless://00000000-0000-0000-0000-000000000000@1.1.1.1:443?type=ws&path=/&security=tls#{encoded_name}"

async def generate_user_subscription_configs(user_main_uuid: str, user_id: int) -> list[str]:
    """تولید تمام کانفیگ‌های کاربر (Async)"""
    from .database import db
    from . import combined_handler

    # ✅ await
    user_info = await combined_handler.get_combined_user_info(user_main_uuid)
    user_record = await db.get_user_uuid_record(user_main_uuid)
    
    if not user_info or not user_record: return []

    user_settings = await db.get_user_settings(user_id) # ✅ await
    show_info_conf = user_settings.get('show_info_config', True)
    
    final_configs = []

    if show_info_conf:
        info_config = await create_info_config(user_main_uuid) # ✅ await
        if info_config:
            final_configs.append(info_config)

    # دریافت دسترسی‌ها
    uuid_id = user_record['id']
    allowed_panels = await db.get_user_allowed_panels(uuid_id)
    allowed_cats = {p['category'] for p in allowed_panels if p.get('category')}
    
    is_vip = user_record.get('is_vip', False)
    user_name = user_record.get('name', 'کاربر')

    # دریافت تمپلیت‌ها
    all_templates = await db.get_active_config_templates() # ✅ await

    eligible_templates = []
    for tpl in all_templates:
        is_special = tpl.get('is_special', False)
        srv_cat = tpl.get('server_category_code') # نام ستون جدید در دیتابیس
        
        # فیلتر VIP
        if is_special and not is_vip: continue
        
        # فیلتر دسته‌بندی (اگر تمپلیت مختص دسته‌ای باشد که کاربر ندارد)
        if srv_cat and srv_cat not in allowed_cats: continue
            
        eligible_templates.append(tpl)

    # مدیریت Random Pool
    fixed = [t for t in eligible_templates if not t.get('is_random_pool')]
    pool = [t for t in eligible_templates if t.get('is_random_pool')]
    
    selected_pool = []
    if RANDOM_SERVERS_COUNT > 0 and len(pool) > RANDOM_SERVERS_COUNT:
        selected_pool = random.sample(pool, RANDOM_SERVERS_COUNT)
    else:
        selected_pool = pool

    final_objs = fixed + selected_pool
    # مرتب‌سازی بر اساس ID برای نظم همیشگی
    final_objs.sort(key=lambda x: x['id'])

    for tpl in final_objs:
        config_str = tpl['template_str']
        if "{new_uuid}" in config_str:
            config_str = config_str.replace("{new_uuid}", user_main_uuid)
        if "{name}" in config_str:
            config_str = config_str.replace("{name}", urllib.parse.quote(user_name))
        final_configs.append(config_str)

    return final_configs

async def get_loyalty_progress_message(user_id: int) -> Optional[Dict[str, Any]]:
    """محاسبه وضعیت وفاداری (Async)"""
    from .database import db
    if not LOYALTY_REWARDS: return None

    try:
        user_uuids = await db.uuids(user_id) # ✅ await
        if not user_uuids: return None
        
        uuid_id = user_uuids[0]['id']
        # ✅ await
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

async def set_template_server_type_service(template_id: int, server_type: str):
    from .database import db
    # ✅ await
    await db.set_template_server_type(template_id, server_type)
    return True

async def reset_all_templates():
    from .database import db
    # ✅ await
    await db.reset_templates_table()
    return True