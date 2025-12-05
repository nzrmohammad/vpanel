# bot/keyboards/__init__.py

from .user import UserMenu
from .admin import AdminMenu
from .base import BaseMenu

# تعریف نمونه‌ها با نام‌های صحیح (همانطور که در فایل‌های دیگر صدا زده شده‌اند)
user = UserMenu()
admin = AdminMenu()
base = BaseMenu()