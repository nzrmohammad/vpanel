# bot/keyboards/__init__.py
from .user import UserMenu
from .admin import AdminMenu

# ایجاد نمونه‌های کلاس‌ها برای استفاده در پروژه
user = UserMenu()
admin = AdminMenu()

# برای سازگاری با ایمپورت‌های احتمالی دیگر
user_menu = user
admin_menu = admin