# bot/formatters/user/profile.py
from datetime import datetime
import asyncio
import pytz
from bot.config import EMOJIS
from bot.language import get_string
from bot.utils.formatters import create_progress_bar, format_daily_usage, escape_markdown
from bot.utils.date_helpers import to_shamsi
from bot import combined_handler
from bot.services.context_service import ContextService
from bot.database import db
from bot.db.base import User

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
        # نکته: الان ContextService این‌ها را برمی‌گرداند
        panel_map = context_data.get('panel_map', {})
        cat_emoji_map = context_data.get('cat_emoji_map', {})
        
        daily_usage_dict = context_data.get('daily_usage', {})
        user_settings = info.get('settings', {})
        panel_access_settings = user_settings.get('panel_access', {})

        # هدر پیام
        raw_name = info.get("name", get_string('unknown_user', lang_code))
        is_active = info.get("is_active", False)
        status_text = get_string("fmt_status_active", lang_code) if is_active else get_string("fmt_status_inactive", lang_code)
        
        # هدر استاندارد مشابه olduser
        header = f"*{escape_markdown(f'{get_string('fmt_user_name_header', lang_code)} : {raw_name}')} \\({EMOJIS['success'] if is_active else EMOJIS['error']} {escape_markdown(status_text)}\\)*"
        
        report = [header, "`──────────────────`"]
        
        breakdown = info.get('breakdown', {})
        LTR = "\u200e"
        
        # تابع داخلی برای پردازش هر پنل (مشابه olduser)
        for p_name, p_details in breakdown.items():
            p_data = p_details.get('data', {})
            p_type = p_details.get('type')
            
            # --- منطق تشخیص پرچم ---
            db_info = panel_map.get(p_name) or panel_map.get(p_name.strip())
            flags_set = set()
            
            if db_info:
                if db_info.get('main_flag'): 
                    flags_set.add(db_info['main_flag'])
                
                # چک کردن نودهای مجاز
                allowed_codes = panel_access_settings.get(db_info['id'], [])
                if allowed_codes and 'nodes' in db_info:
                    for node in db_info['nodes']:
                        if node.country_code in allowed_codes:
                            flags_set.add(node.flag)
            else:
                # فال‌بک به دسته‌بندی
                cat = p_details.get('category')
                if cat and cat in cat_emoji_map:
                    flags_set.add(cat_emoji_map[cat])

            final_flag = "".join(sorted(list(flags_set))) if flags_set else "🏳️"
            
            # وضعیت
            is_panel_active = (p_data.get('status') == 'active') or (p_data.get('enable') is True)
            icon = "✅" if is_panel_active else "❌"

            # مقادیر
            limit = p_data.get("usage_limit_GB", 0.0)
            usage = p_data.get("current_usage_GB", 0.0)
            remaining = max(0, limit - usage)
            today = daily_usage_dict.get(p_type, 0.0)
            
            # انقضا
            expire_str = ProfileFormatter._format_expire(p_data, lang_code)
            
            # آخرین اتصال
            last_online = ProfileFormatter._format_last_online(p_data, p_type)

            # نوار پیشرفت
            percent = (usage / limit * 100) if limit > 0 else 0
            p_bar = create_progress_bar(percent) if limit > 0 else ""
            
            lines = [
                f"*سرور {final_flag} \\({icon}\\)*",
                f"{EMOJIS['database']} {escape_markdown('حجم کل :')} {escape_markdown(f'{LTR}{limit:.0f} GB')}",
                f"{EMOJIS['fire']} {escape_markdown('حجم مصرف شده :')} {escape_markdown(f'{LTR}{usage:.2f} GB')}",
                f"{EMOJIS['download']} {escape_markdown('حجم باقیمانده :')} {escape_markdown(f'{LTR}{remaining:.2f} GB')}",
                f"{EMOJIS['lightning']} {escape_markdown('مصرف امروز :')} {escape_markdown(f'{LTR}{format_daily_usage(today)}')}",
                f"{EMOJIS['time']} {escape_markdown('آخرین اتصال :')} {escape_markdown(last_online)}",
                f"{EMOJIS['calendar']} {escape_markdown('انقضا :')} {escape_markdown(expire_str)}",
                f"{p_bar}",
                "`──────────────────`"
            ]
            report.extend(lines)

        uuid_val = info.get('uuid')
        if uuid_val:
            report.append(f"🔑 {escape_markdown('شناسه یکتا :')} `{escape_markdown(uuid_val)}`")

        return "\n".join(report)

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

    # --- متد آمار فوری مشابه olduser.py (تکی) ---
    @staticmethod
    async def quick_stats(uuid_rows: list, page: int, lang_code: str) -> tuple[str, dict]:
        """
        نمایش آمار فوری به صورت اسلایدر (نمایش کامل یک پروفایل در هر صفحه)
        دقیقاً مشابه عملکرد فایل olduser.py
        """
        num_uuids = len(uuid_rows)
        menu_data = {"num_accounts": num_uuids, "current_page": 0}
        
        if not num_uuids: 
            return escape_markdown(get_string("fmt_no_account_registered", lang_code)), menu_data

        # اطمینان از معتبر بودن شماره صفحه
        current_page = max(0, min(page, num_uuids - 1))
        menu_data["current_page"] = current_page
        
        # دریافت اطلاعات اکانت انتخاب شده
        target_row = uuid_rows[current_page]
        uuid_str = str(target_row['uuid']) 
        
        # دریافت اطلاعات کامل سرویس
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if not info:
            return escape_markdown("خطا در دریافت اطلاعات"), menu_data

        # دریافت اطلاعات تکمیلی (تنظیمات کاربر)
        user_id = target_row.get('user_id')
        if user_id:
            async with db.get_session() as session:
                user_obj = await session.get(User, user_id)
                if user_obj and user_obj.settings:
                    info['settings'] = user_obj.settings
        
        # دریافت کانتکست (پرچم‌ها و...)
        # نکته مهم: اینجا باید کانتکست را بگیریم تا به profile_info بدهیم
        context_data = await ContextService.get_user_context_full(uuid_str)

        # تولید متن گزارش
        report_text = ProfileFormatter.profile_info(info, lang_code, context_data)
        
        return report_text, menu_data
    
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