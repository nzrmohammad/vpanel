# bot/utils/v2ray.py
import random
import urllib.parse
import logging
from bot.database import db

logger = logging.getLogger(__name__)

async def create_info_config(user_uuid: str) -> str:
    """تولید کانفیگ اطلاع‌رسانی حجم و زمان (بدون اتصال واقعی)"""
    from . import combined_handler # ایمپورت داخلی برای جلوگیری از Circular Import
    
    info = await combined_handler.get_combined_user_info(user_uuid)
    if not info: return None

    total_usage = info.get('current_usage_GB', 0)
    total_limit = info.get('usage_limit_GB', 0)
    limit_str = f"{total_limit:.0f}" if total_limit > 0 else '∞'
    
    # بخش اول: وضعیت حجم
    usage_part = f"📊 {total_usage:.1f}/{limit_str}GB"

    # بخش دوم: وضعیت روزها
    days_left = info.get('expire')
    if days_left is not None:
        days_str = str(days_left) if days_left >= 0 else 'Expired'
        date_part = f"📅 {days_str} Days"
    else:
        date_part = "📅 Unlimited"

    final_name = f"{usage_part} | {date_part}"
    encoded_name = urllib.parse.quote(final_name)
    
    # تولید یک لینک نمایشی (Dummy)
    return f"vless://00000000-0000-0000-0000-000000000000@1.1.1.1:443?type=ws&path=/&security=tls#{encoded_name}"

async def generate_user_subscription_configs(user_main_uuid: str, user_id: int) -> list[str]:
    """تولید لیست کامل کانفیگ‌های اشتراک کاربر بر اساس دسترسی‌ها و تمپلیت‌ها"""
    from . import combined_handler
    
    user_info = await combined_handler.get_combined_user_info(user_main_uuid)
    user_record = await db.get_user_uuid_record(user_main_uuid)
    if not user_info or not user_record: return []

    # چک کردن تنظیمات نمایش کانفیگ اینفو
    user_settings = await db.get_user_settings(user_id)
    show_info_conf = user_settings.get('show_info_config', True)
    
    final_configs = []

    # ۱. افزودن کانفیگ اینفو (اگر فعال باشد)
    if show_info_conf:
        info_conf = await create_info_config(user_main_uuid)
        if info_conf: final_configs.append(info_conf)

    # ۲. دریافت دسترسی‌های کاربر (کتگوری‌های مجاز)
    uuid_id = user_record['id']
    allowed_panels = await db.get_user_allowed_panels(uuid_id)
    allowed_cats = {p['category'] for p in allowed_panels if p.get('category')}
    
    is_vip = user_record.get('is_vip', False)
    user_name = user_record.get('name', 'User')

    # ۳. دریافت تمپلیت‌های فعال از دیتابیس
    all_templates = await db.get_active_config_templates()
    
    # ۴. دریافت تعداد سرور رندوم از تنظیمات سیستم (دیتابیس)
    # جایگزین config.RANDOM_SERVERS_COUNT
    random_count_str = await db.get_config('random_servers_count', '10')
    random_servers_limit = int(random_count_str)

    eligible_templates = []
    for tpl in all_templates:
        # فیلتر VIP
        if tpl.get('is_special', False) and not is_vip: continue
        
        # فیلتر دسته‌بندی کشورها
        srv_cat = tpl.get('server_category_code')
        if srv_cat and srv_cat not in allowed_cats: continue
            
        eligible_templates.append(tpl)

    # ۵. جداسازی سرورهای ثابت و استخر رندوم
    fixed = [t for t in eligible_templates if not t.get('is_random_pool')]
    pool = [t for t in eligible_templates if t.get('is_random_pool')]
    
    selected_pool = []
    if random_servers_limit > 0 and len(pool) > random_servers_limit:
        selected_pool = random.sample(pool, random_servers_limit)
    else:
        selected_pool = pool

    final_objs = fixed + selected_pool
    final_objs.sort(key=lambda x: x['id'])

    # ۶. جایگزینی متغیرها در رشته کانفیگ
    for tpl in final_objs:
        config_str = tpl['template_str']
        if "{new_uuid}" in config_str:
            config_str = config_str.replace("{new_uuid}", user_main_uuid)
        if "{name}" in config_str:
            config_str = config_str.replace("{name}", urllib.parse.quote(user_name))
        final_configs.append(config_str)

    return final_configs