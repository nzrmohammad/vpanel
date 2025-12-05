# bot/formatters/__init__.py
from .user import UserFormatter
from .admin import AdminFormatter
from .utils import bytes_to_gb, format_currency, format_date, get_status_emoji

# ایجاد نمونه‌ها (Instances) برای دسترسی راحت در کل پروژه
# با این کار نیازی نیست هر بار کلاس را صدا بزنید
user_formatter = UserFormatter()
admin_formatter = AdminFormatter()

__all__ = [
    'user_formatter',
    'admin_formatter',
    'bytes_to_gb',
    'format_currency',
    'format_date',
    'get_status_emoji'
]