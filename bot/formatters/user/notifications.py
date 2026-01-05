# bot/formatters/user/notifications.py
from bot.language import get_string
from bot.utils.formatters import format_daily_usage
from bot.utils.formatters import escape_markdown

class NotificationFormatter:
    
    @staticmethod
    def nightly_report(user_reports: list, total_usage: float) -> str:
        """
        user_reports: لیستی از متن‌های آماده شده برای هر کاربر
        total_usage: مجموع کل مصرف
        """
        if not user_reports:
            return ""
            
        text = "\n\n".join(user_reports)
        footer = f"\n\n⚡️ مجموع مصرف امروز کل کاربران : {escape_markdown(format_daily_usage(total_usage))}"
        return text + footer

    @staticmethod
    def sharing_alert(requester, uuid_name):
        r_name = escape_markdown(requester.first_name or "Unknown")
        uuid_safe = escape_markdown(uuid_name)
        return (
            f"⚠️ *یک کاربر دیگر قصد دارد به اکانت «{uuid_safe}» شما متصل شود*\\.\n\n"
            f"👤 *اطلاعات درخواست دهنده:*\n"
            f"نام: {r_name}\n"
            f"آیدی: `{requester.id}`\n\n"
            f"❓ آیا اجازه می‌دهید؟"
        )