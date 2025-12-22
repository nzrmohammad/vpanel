# bot/formatters/admin.py

from bot.utils.formatters import format_currency, format_date, get_status_emoji
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