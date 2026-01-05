# bot/formatters/__init__.py

# 1. ایمپورت کلاس‌های فرمتر بخش کاربر
from .user import (
    ProfileFormatter, 
    ServiceFormatter, 
    WalletFormatter, 
    NotificationFormatter
)

# 2. ایمپورت کلاس‌های فرمتر بخش ادمین
from .admin import (
    AdminUserFormatter, 
    AdminReportFormatter, 
    AdminSystemFormatter
)

# 3. ساخت کلاس تجمیعی برای دسترسی آسان به متدهای کاربر
class UserFormatters:
    """
    کلاس Facade برای دسترسی یکپارچه به تمام فرمترهای مربوط به کاربر.
    مثال: user_formatter.profile.profile_info(...)
    """
    profile = ProfileFormatter()
    services = ServiceFormatter()
    wallet = WalletFormatter()
    notification = NotificationFormatter()

# 4. ساخت کلاس تجمیعی برای دسترسی آسان به متدهای ادمین
class AdminFormatters:
    """
    کلاس Facade برای دسترسی یکپارچه به تمام فرمترهای مربوط به ادمین.
    مثال: admin_formatter.users.user_details(...)
    """
    users = AdminUserFormatter()
    reports = AdminReportFormatter()
    system = AdminSystemFormatter()

# 5. ایجاد نمونه‌های آماده (Instances) برای استفاده در پروژه
user_formatter = UserFormatters()
admin_formatter = AdminFormatters()

# 6. مشخص کردن آنچه که با 'from bot.formatters import *' صادر می‌شود
__all__ = [
    'user_formatter',
    'admin_formatter',
    'UserFormatters',
    'AdminFormatters'
]