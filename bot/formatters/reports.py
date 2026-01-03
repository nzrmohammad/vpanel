# bot/formatters/reports.py

import jdatetime
import pytz
from datetime import datetime
import logging
from bot.utils.formatters import escape_markdown, format_daily_usage, bytes_to_gb

logger = logging.getLogger(__name__)

# مپینگ کد کشور به ایموجی
COUNTRY_TO_EMOJI = {
    'ir': '🇮🇷', 'fr': '🇫🇷', 'de': '🇩🇪', 'tr': '🇹🇷',
    'us': '🇺🇸', 'gb': '🇬🇧', 'nl': '🇳🇱', 'fi': '🇫🇮',
    'ro': '🇷🇴', 'ru': '🇷🇺', 'ua': '🇺🇦', 'ae': '🇦🇪',
    'pl': '🇵🇱', 'ca': '🇨🇦', 'es': '🇪🇸', 'ch': '🇨🇭',
    'se': '🇸🇪', 'no': '🇳🇴', 'it': '🇮🇹', 'in': '🇮🇳'
}

# اولویت نمایش (فقط برای مرتب‌سازی زیباتر)
# پنل‌هایی که اینجا نیستند، به ترتیب حروف الفبا بعد از این‌ها نمایش داده می‌شوند
PANEL_DISPLAY_PRIORITY = {
    'hiddify': 1,
    'marzban': 2,
    'remnawave': 3,
    'pasargad': 4
}

def get_current_jalali_datetime():
    """تاریخ و ساعت فعلی شمسی"""
    return jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")

def get_flag_for_country(country_code: str) -> str:
    """تبدیل کد کشور به پرچم"""
    return COUNTRY_TO_EMOJI.get(country_code.lower(), '🌐')

def get_dynamic_flags_for_user(user_db_record: dict, panel_type: str) -> str:
    """تولید داینامیک پرچم‌ها بر اساس پنل‌های مجاز کاربر"""
    if not user_db_record:
        return '🌐'

    unique_countries = set()
    
    # روش جدید: بررسی لیست پنل‌های مجاز (اگر در دیتابیس لود شده باشد)
    panels = user_db_record.get('allowed_panels', [])
    
    if panels:
        for panel in panels:
            # اگر نوع پنل مشخص است، فقط پرچم‌های همان نوع را برگردان
            p_type = getattr(panel, 'type', '').lower()
            if panel_type and p_type and p_type != panel_type:
                continue
            
            code = getattr(panel, 'country', None) or getattr(panel, 'category', None)
            if code: unique_countries.add(code)
    else:
        # روش فال‌بک (سازگار با ساختار قدیمی یا دیکشنری ساده)
        for key, value in user_db_record.items():
            if key.startswith('has_access_') and value:
                # اینجا چون نوع پنل در کلید نیست، همه را برمی‌گردانیم (مگر اینکه سیستم نامگذاری را تغییر دهید)
                code = key.replace('has_access_', '')
                unique_countries.add(code)

    if not unique_countries:
        return '🏳️' # پرچم خنثی

    flags = [get_flag_for_country(c) for c in unique_countries]
    return "".join(sorted(flags))

def sort_panel_keys(keys):
    """مرتب‌سازی کلیدهای پنل: اولویت‌دارها اول، بقیه الفبایی"""
    return sorted(keys, key=lambda k: (PANEL_DISPLAY_PRIORITY.get(k, 999), k))

async def fmt_user_nightly_report(user_info: dict, db_manager) -> str:
    """گزارش شبانه کاربر (کاملاً داینامیک)"""
    try:
        uuid = user_info.get('uuid')
        
        # 1. دریافت دیتای دیتابیس
        user_db_rec = await db_manager.get_user_uuid_record(uuid) if uuid else {}
        
        # 2. دریافت مصرف (دیکشنری داینامیک: هر پنلی که باشد برمی‌گرداند)
        # مثال خروجی: {'hiddify': 0.5, 'marzban': 1.2, 'pasargad': 0.1}
        usage_data = {}
        if uuid:
            usage_data = await db_manager.get_usage_since_midnight_by_uuid(uuid)

        total_today_usage = sum(usage_data.values())

        # اطلاعات اکانت
        name = escape_markdown(user_info.get('name', 'User'))
        limit_gb = float(user_info.get('usage_limit_GB', 0) or 0)
        used_gb = float(user_info.get('current_usage_GB', 0) or 0)
        remain_gb = bytes_to_gb((limit_gb * 1024**3) - (used_gb * 1024**3))
        
        expire_str = "نامشخص"
        if 'remaining_days' in user_info and user_info['remaining_days'] is not None:
             expire_str = f"{int(user_info['remaining_days'])} روز"

        lines = [
            f"🌙 گزارش شبانه - {get_current_jalali_datetime()}",
            "──────────────────",
            f"👤 اکانت : *{name}*",
            f"📊 حجم‌کل : *{limit_gb:.2f} GB*",
            f"🔥 حجم‌مصرف شده : *{used_gb:.2f} GB*",
            f"📥 حجم‌باقی‌مانده : *{remain_gb:.2f} GB*",
            f"⚡️ حجم مصرف شده امروز:"
        ]

        # 3. حلقه داینامیک روی کلیدهای موجود در usage_data
        # اگر Pasargad اضافه شده باشد، در usage_data وجود دارد و نمایش داده می‌شود
        sorted_panels = sort_panel_keys(usage_data.keys())
        
        has_usage = False
        for p_type in sorted_panels:
            val = usage_data[p_type]
            if val > 0.0001:
                has_usage = True
                flags = get_dynamic_flags_for_user(user_db_rec, p_type)
                lines.append(f"{flags} : `{format_daily_usage(val)}`")

        if not has_usage:
            lines.append(" (بدون مصرف)")

        lines.append(f"📅 انقضا : {expire_str}")
        lines.append("")
        lines.append(f"⚡️ مجموع کل مصرف امروز : *{format_daily_usage(total_today_usage)}*")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"User Report Error: {e}", exc_info=True)
        return "❌ خطا در ساخت گزارش"


async def fmt_admin_comprehensive_report(all_users_from_api: list, db_manager) -> str:
    """گزارش جامع ادمین (کاملاً داینامیک برای هر تعداد پنل)"""
    try:
        db_users_list = await db_manager.get_all_bot_users_with_uuids()
        db_users_map = {str(u['uuid']): u for u in db_users_list}
        
        all_daily_usages = await db_manager.get_all_daily_usage_since_midnight()
        
        active_count = 0
        new_users_count = 0
        
        # دیکشنری برای جمع کل مصرف هر نوع پنل (هر چی که باشه)
        total_usage_map = {} 
        
        active_users_list = []
        expiring_list = []
        expired_list = []
        top_consumer = {"name": "N/A", "usage": 0.0}
        
        now = datetime.now(pytz.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for user in all_users_from_api:
            uuid = user.get('uuid')
            
            if user.get('is_active') or user.get('enable'):
                active_count += 1
            
            # دریافت استت کاربر
            u_stats = all_daily_usages.get(uuid, {})
            user['daily_stats'] = u_stats # ذخیره برای چاپ
            
            user_total = 0.0
            
            # حلقه روی هر پنلی که کاربر دارد (Hiddify, Marzban, Pasargad, ...)
            for p_type, val in u_stats.items():
                val = float(val)
                user_total += val
                
                # اضافه کردن به آمار کلی پنل
                total_usage_map[p_type] = total_usage_map.get(p_type, 0.0) + val
            
            # قهرمان
            d_name = user.get('name') or user.get('username') or 'Unknown'
            if user_total > top_consumer['usage']:
                top_consumer = {'name': d_name, 'usage': user_total}
            
            if user_total > 0.001:
                active_users_list.append(user)
                
            # انقضا و جدید
            rem_days = None
            if 'remaining_days' in user and user['remaining_days'] is not None:
                rem_days = int(user['remaining_days'])
            elif 'expire' in user and user['expire']:
                 try:
                    ts = float(user['expire'])
                    if ts > 0: rem_days = int((ts - datetime.now().timestamp()) / 86400)
                 except: pass
            
            if rem_days is not None:
                user['_rem_days'] = rem_days
                if 0 <= rem_days <= 3: expiring_list.append(user)
                elif -2 <= rem_days < 0: expired_list.append(user)
            
            db_rec = db_users_map.get(uuid)
            if db_rec and db_rec.get('created_at'):
                c_at = db_rec['created_at']
                if c_at.tzinfo is None: c_at = pytz.utc.localize(c_at)
                if (now - c_at).days < 1: new_users_count += 1

        payments_today = await db_manager.get_total_payments_in_range(start_of_today, now)
        total_all_usage = sum(total_usage_map.values())

        # --- تولید متن گزارش ---
        lines = [
            f"👑 گزارش جامع - {get_current_jalali_datetime()}",
            "──────────────────",
            "⚙️ خلاصه وضعیت کل پنل",
            f"👤 کل اکانت‌ها : {len(all_users_from_api)} | ✅ فعال : {active_count}",
            f"➕ جدید : {new_users_count} | 💳 پرداخت : {payments_today}",
            f"⚡️ مصرف کل امروز : {format_daily_usage(total_all_usage)}"
        ]
        
        # نمایش داینامیک مصرف کل به تفکیک پنل‌ها
        # کلیدها را مرتب می‌کنیم تا Hiddify و Marzban اول باشند، بقیه زیرش
        sorted_types = sort_panel_keys(total_usage_map.keys())
        
        for p_type in sorted_types:
            usage = total_usage_map[p_type]
            if usage > 0:
                # نام پنل را زیبا می‌کنیم (حرف اول بزرگ)
                label = p_type.title() 
                lines.append(f"   ▫️ {label}: `{format_daily_usage(usage)}`")

        if top_consumer['usage'] > 0:
            lines.append(f"🔥 قهرمان امروز : {escape_markdown(top_consumer['name'])} ({format_daily_usage(top_consumer['usage'])})")
            
        lines.append("──────────────────")
        lines.append("✅ کاربران فعال امروز و مصرفشان")
        
        active_users_list.sort(key=lambda x: x.get('name', '').lower())
        
        for u in active_users_list:
            name = escape_markdown(u.get('name') or 'Unknown')
            uuid = u.get('uuid')
            db_rec = db_users_map.get(uuid)
            
            is_vip = db_rec.get('is_vip', False) if db_rec else False
            emoji = "👑" if is_vip else "👤"
            
            stats = u.get('daily_stats', {})
            parts = []
            
            # نمایش داینامیک مصرف کاربر برای هر پنل
            user_panel_types = sort_panel_keys(stats.keys())
            
            for p_type in user_panel_types:
                val = stats[p_type]
                if val > 0.001:
                    # دریافت پرچم داینامیک برای همین نوع پنل
                    flags = get_dynamic_flags_for_user(db_rec, p_type)
                    parts.append(f"{flags} {format_daily_usage(val)}")
            
            usage_str = " | ".join(parts)
            lines.append(f"{emoji} {name} : {usage_str}")

        lines.append("──────────────────")
        
        if expiring_list:
            lines.append("⚠️ کاربرانی که تا ۳ روز آینده منقضی می شوند")
            expiring_list.sort(key=lambda x: x.get('_rem_days', 0))
            for u in expiring_list:
                name = escape_markdown(u.get('name') or 'Unknown')
                lines.append(f"👤 {name} : {u['_rem_days']} روز")
            lines.append("──────────────────")

        if expired_list:
            lines.append("❌ کاربران منقضی (24 ساعت اخیر)")
            for u in expired_list:
                name = escape_markdown(u.get('name') or 'Unknown')
                lines.append(f"👤 {name}")
            lines.append("──────────────────")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Admin Report Error: {e}", exc_info=True)
        return f"❌ خطا: {e}"