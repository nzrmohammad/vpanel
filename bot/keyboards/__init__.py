# bot/keyboards/__init__.py
from .user import user_keyboard
from .admin import admin_keyboard

# ایجاد نمونه‌های کلاس‌ها برای استفاده در پروژه
UserMenu = user_keyboard
AdminMenu = admin_keyboard

# برای سازگاری با ایمپورت‌های احتمالی دیگر
user_menu = user
admin_menu = admin