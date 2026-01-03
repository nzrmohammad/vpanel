# bot/formatters/admin.py

from bot.utils.formatters import format_currency, format_date, get_status_emoji
from bot.utils.date_helpers import to_shamsi, days_until_next_birthday
from bot.config import EMOJIS

class AdminFormatter:
    
    @staticmethod
    def _get_val(data, attr, default=None):
        """تابع کمکی برای دریافت مقدار از دیکشنری یا آبجکت"""
        if isinstance(data, dict):
            return data.get(attr, default)
        return getattr(data, attr, default)

    @staticmethod
    def user_details(user_data, panel_name: str) -> str:
        """
        نمایش ریز جزئیات کاربر (کانفیگ) در پنل مدیریت
        قابل استفاده برای دیکشنری یا آبجکت UserUUID
        """
        # استخراج داده‌ها با تابع کمکی (سازگار با هر دو حالت)
        name = AdminFormatter._get_val(user_data, 'name') or "بی‌نام"
        uuid = AdminFormatter._get_val(user_data, 'uuid') or "---"
        is_active = AdminFormatter._get_val(user_data, 'is_active', True)
        status = "🟢 فعال" if is_active else "🔴 غیرفعال"
        
        # تشخیص آنلاین بودن (مخصوص پنل‌هایی که این دیتا را می‌دهند)
        last_online = AdminFormatter._get_val(user_data, 'last_online') or AdminFormatter._get_val(user_data, 'online_at')
        if last_online:
            online_str = f"🕒 {format_date(last_online) if isinstance(last_online, (int, float)) else last_online}"
        else:
            online_str = "⚫️ آفلاین"

        # حجم مصرفی (اگر آبجکت دیتابیس باشد، ممکن است نیاز به محاسبه جدا باشد)
        # فرض بر این است که مقادیر usage قبلاً محاسبه و به اتریبیوت اضافه شده‌اند
        usage_val = AdminFormatter._get_val(user_data, 'current_usage_GB', 0)
        limit_val = AdminFormatter._get_val(user_data, 'usage_limit_GB', 0)
        usage_str = f"{usage_val} / {limit_val} GB"
        
        expire_days = AdminFormatter._get_val(user_data, 'expire_days') # یا نام فیلد مشابه
        if expire_days is None:
             expire_days = AdminFormatter._get_val(user_data, 'remaining_days')

        expire_str = f"{expire_days} روز" if expire_days is not None else "نامحدود"

        return (
            f"👤 <b>اطلاعات کاربر در {panel_name}</b>\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"🔖 <b>نام:</b> {name}\n"
            f"🔑 <b>UUID:</b> <code>{uuid}</code>\n"
            f"📡 <b>وضعیت:</b> {status}\n"
            f"🔋 <b>وضعیت اتصال:</b> {online_str}\n"
            f"📊 <b>مصرف:</b> {usage_str}\n"
            f"⏳ <b>اعتبار:</b> {expire_str}\n"
        )

    @staticmethod
    def user_list_row(user, index: int) -> str:
        """
        یک خط خلاصه برای نمایش در لیست‌های طولانی (Pagination)
        """
        is_active = AdminFormatter._get_val(user, 'is_active', False)
        status_icon = "✅" if is_active else "❌"
        
        name = AdminFormatter._get_val(user, 'name') or AdminFormatter._get_val(user, 'first_name') or 'Unknown'
        
        # هندل کردن تفاوت فیلدها در User (تلگرام) و UserUUID (کانفیگ)
        if hasattr(user, 'wallet_balance'): # اگر آبجکت User تلگرام باشد
            balance = AdminFormatter._get_val(user, 'wallet_balance', 0)
            extra_info = f"{int(balance):,} T"
        else: # اگر کانفیگ باشد
            usage = AdminFormatter._get_val(user, 'current_usage_GB', 0)
            extra_info = f"{usage:.1f}GB"

        return f"{index}. {status_icon} <b>{name}</b> | {extra_info}"

    @staticmethod
    def birthdays_list(users, page: int, total_count: int, page_size: int = 15) -> str:
        """
        لیست تولد کاربران (فرمت HTML)
        """
        title = "🎂 لیست تولد کاربران (مرتب شده بر اساس ماه)"
        if not users:
            return f"<b>{title}</b>\n\nهیچ کاربری تاریخ تولد خود را ثبت نکرده است."
        
        total_pages = (total_count + page_size - 1) // page_size
        header = f"<b>{title}</b>\n(صفحه {page + 1} از {total_pages} | کل: {total_count})\n➖➖➖➖➖➖➖➖"
        
        lines = [header]
        
        for user in users:
            # دریافت نام
            name = AdminFormatter._get_val(user, 'first_name') or AdminFormatter._get_val(user, 'name') or "بی‌نام"
            # ایمن‌سازی نام برای HTML
            name = str(name).replace('<', '&lt;').replace('>', '&gt;')
            
            # تاریخ تولد
            birthday = AdminFormatter._get_val(user, 'birthday')
            date_str = to_shamsi(birthday)
            
            # روزهای باقیمانده
            days = days_until_next_birthday(birthday)
            if days == 0:
                days_str = "امروز! 🎉"
            elif days is not None:
                days_str = f"{days} روز"
            else:
                days_str = "نامشخص"
            
            # ساخت خط: 🎂 Name | Date | Days
            lines.append(f"🎂 <b>{name}</b> | {date_str} | {days_str}")
            
        return "\n".join(lines)

    @staticmethod
    def system_stats(stats: dict) -> str:
        """نمایش وضعیت منابع سرور (معمولاً دیکشنری است)"""
        return (
            f"🖥 <b>وضعیت سلامت سرور</b>\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"🧠 <b>رم (RAM):</b> {stats.get('ram_used', 0)} / {stats.get('ram_total', 0)} GB\n"
            f"⚙️ <b>پردازنده (CPU):</b> {stats.get('cpu_load', 0)}%\n"
            f"💾 <b>هارد (Disk):</b> {stats.get('disk_used', 0)}%\n"
            f"⏱ <b>آپتایم:</b> {stats.get('uptime', 'نامشخص')}\n"
            f"\n"
            f"🔄 <i>به‌روزرسانی خودکار: هر 5 دقیقه</i>"
        )
    @staticmethod
    def purchase_report(user_name, user_id, service_name, type_text, plan_name, limit_gb, days, price, uuid_str, date_str, wallet_balance, server_name) -> str:
        """
        گزارش خرید برای ادمین (ارسال به سوپرگروه)
        """
        return (
            f"🛒 <b>گزارش خرید جدید</b>\n"
            f"👤 کاربر : {user_name} (<code>{user_id}</code>)\n"
            f"🔑 نام سرویس : <code>{service_name}</code>\n"
            f"🏷 نوع : {type_text}\n"
            f"📦 پلن : {plan_name} ({limit_gb}GB - {days} روز)\n"
            f"💰 مبلغ : {price:,} تومان\n"
            f"💳 <b>مانده کیف پول : {wallet_balance:,} تومان</b>\n"
            f"🖥 <b>سرور : {server_name}</b>\n"
            f"شناسه ورود : <code>{uuid_str}</code>\n"
            f"📅 تاریخ : {date_str}"
        )