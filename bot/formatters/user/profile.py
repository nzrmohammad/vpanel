# bot/formatters/user/profile.py
from datetime import datetime
import pytz
from bot.config import EMOJIS
from bot.language import get_string
from bot.utils.formatters import create_progress_bar, format_daily_usage
from bot.utils.date_helpers import to_shamsi
from bot.utils.formatters import escape_markdown, format_volume

class ProfileFormatter:
    
    @staticmethod
    def profile_info(info: dict, lang_code: str, context_data: dict) -> str:
        """
        info: دیکشنری اطلاعات سرویس (از combined_handler)
        context_data: خروجی ContextService (شامل پنل مپ و...)
        """
        if not info:
            return escape_markdown(get_string("fmt_err_getting_info", lang_code))

        # استخراج داده‌های کمکی
        panel_map = context_data.get('panel_map', {})
        cat_emoji_map = context_data.get('cat_emoji_map', {})
        daily_usage_dict = context_data.get('daily_usage', {})
        user_settings = info.get('settings', {})
        panel_access_settings = user_settings.get('panel_access', {})

        # هدر پیام
        raw_name = info.get("name", get_string('unknown_user', lang_code))
        is_active = info.get("is_active", False)
        status_emoji = get_string("fmt_status_active", lang_code) if is_active else get_string("fmt_status_inactive", lang_code)
        
        header = f"*{escape_markdown(f'{get_string('fmt_user_name_header', lang_code)} : {raw_name}')} ({EMOJIS['success'] if is_active else EMOJIS['error']} {status_emoji})*"
        report = [header, "`──────────────────`"]
        
        breakdown = info.get('breakdown', {})
        
        # حلقه روی سرویس‌ها
        for p_name, p_details in breakdown.items():
            section = ProfileFormatter._format_single_panel(
                p_name, p_details, lang_code, 
                panel_map, cat_emoji_map, 
                panel_access_settings, daily_usage_dict
            )
            report.extend(section)

        uuid_val = info.get('uuid')
        if uuid_val:
            report.append(f"🔑 {escape_markdown('شناسه یکتا :')} `{escape_markdown(uuid_val)}`")

        return "\n".join(report)

    @staticmethod
    def _format_single_panel(name, details, lang_code, panel_map, cat_map, access_settings, daily_usage):
        """فرمت کردن یک پنل خاص (تابع داخلی)"""
        p_data = details.get('data', {})
        p_type = details.get('type')
        
        # تعیین پرچم
        db_info = panel_map.get(name) or panel_map.get(name.strip())
        flags_set = set()
        
        if db_info:
            if db_info['main_flag']: flags_set.add(db_info['main_flag'])
            allowed_codes = access_settings.get(db_info['id'], [])
            if allowed_codes:
                for node in db_info['nodes']:
                    if node.country_code in allowed_codes:
                        flags_set.add(node.flag)
        else:
            cat = details.get('category')
            if cat and cat in cat_map:
                flags_set.add(cat_map[cat])

        final_flag = "".join(sorted(list(flags_set))) if flags_set else "🏳️"
        
        # وضعیت فعال/غیرفعال پنل
        is_active = (p_data.get('status') == 'active') or (p_data.get('enable') is True)
        icon = "✅" if is_active else "❌"

        # محاسبات حجم
        limit = p_data.get("usage_limit_GB", 0.0)
        usage = p_data.get("current_usage_GB", 0.0)
        remaining = max(0, limit - usage)
        today = daily_usage.get(p_type, 0.0)
        
        # انقضا
        expire_str = ProfileFormatter._format_expire(p_data, lang_code)
        
        # آخرین اتصال
        last_online = ProfileFormatter._format_last_online(p_data, p_type)

        # نوار پیشرفت
        percent = (usage / limit * 100) if limit > 0 else 0
        p_bar = create_progress_bar(percent) if limit > 0 else ""
        
        LTR = "\u200e"
        
        lines = [
            f"*سرور {final_flag} \({icon}\)*",
            f"{EMOJIS['database']} {escape_markdown('حجم کل :')} {escape_markdown(f'{LTR}{limit:.0f} GB')}",
            f"{EMOJIS['fire']} {escape_markdown('حجم مصرف شده :')} {escape_markdown(f'{LTR}{usage:.2f} GB')}",
            f"{EMOJIS['download']} {escape_markdown('حجم باقیمانده :')} {escape_markdown(f'{LTR}{remaining:.2f} GB')}",
            f"{EMOJIS['lightning']} {escape_markdown('مصرف امروز :')} {escape_markdown(f'{LTR}{format_daily_usage(today)}')}",
            f"{EMOJIS['time']} {escape_markdown('آخرین اتصال :')} {escape_markdown(last_online)}",
            f"{EMOJIS['calendar']} {escape_markdown('انقضا :')} {escape_markdown(expire_str)}",
            f"{p_bar}",
            "`──────────────────`"
        ]
        return lines

    @staticmethod
    def _format_expire(data, lang_code):
        expire_val = data.get('expire')
        pkg_days = data.get('package_days')
        start_date = data.get('start_date')
        
        if isinstance(expire_val, (int, float)) and expire_val > 100_000_000:
            try:
                rem = (datetime.fromtimestamp(expire_val) - datetime.now()).days
                return get_string("fmt_status_expired", lang_code) if rem < 0 else get_string("fmt_expire_days", lang_code).format(days=rem)
            except: pass
        elif pkg_days is not None:
            try:
                if start_date:
                    start = datetime.strptime(str(start_date).split(' ')[0], "%Y-%m-%d")
                    passed = (datetime.now() - start).days
                    rem = int(pkg_days) - passed
                    return get_string("fmt_expire_days", lang_code).format(days=max(0, rem))
                return get_string("fmt_expire_days", lang_code).format(days=int(pkg_days))
            except: pass
            
        return get_string("fmt_expire_unlimited", lang_code)

    @staticmethod
    def _format_last_online(data, p_type):
        raw = data.get('last_online') or data.get('online_at')
        if not raw: return "---"
        
        if p_type == 'hiddify' and isinstance(raw, str):
            try:
                dt = datetime.strptime(raw.replace('T', ' ').split('.')[0], '%Y-%m-%d %H:%M:%S')
                if dt.year > 2000:
                    raw = pytz.timezone("Asia/Tehran").localize(dt)
            except: pass
            
        return to_shamsi(raw, include_time=True)
    
    @staticmethod
    def inline_result(info: dict, context_data: dict) -> str:
        if not info: return "❌"
        uuid_str = info.get("uuid", "")
        cat_map = context_data.get('cat_emoji_map', {})
        user_cats = context_data.get('user_categories', [])
        
        name = escape_markdown(info.get("name", "کاربر"))
        flags = "".join([cat_map.get(c, "") for c in user_cats])
        
        lines = [
            f"📊 *{name}*",
            f"🛰️ سرورها : {flags}" if flags else "",
            f"📦 حجم: {info.get('usage_limit_GB', 0):.2f} GB",
            f"🔥 مصرف: {info.get('current_usage_GB', 0):.2f} GB",
            f"⏳ انقضا: {info.get('expire', '?')}",
            f"\n`{escape_markdown(uuid_str)}`"
        ]
        return "\n".join([l for l in lines if l])