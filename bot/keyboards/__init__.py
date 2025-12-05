# bot/keyboards/__init__.py

from .user import UserMenu
from .admin import AdminMenu
from .base import BaseMenu

# تعریف نمونه‌های اصلی کلاس‌ها
user = UserMenu()
admin = AdminMenu()
base = BaseMenu()

# تعریف نام‌های جایگزین (Alias) برای جلوگیری از خطای ایمپورت در فایل‌های دیگر
user_menu = user
admin_menu = admin