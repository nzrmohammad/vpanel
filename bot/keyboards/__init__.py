# bot/keyboards/__init__.py

# 1. ایمپورت کردن نمونه‌های کلاس که در فایل‌های __init__ پوشه‌های user و admin ساخته شده‌اند
from .user import user_keyboard
from .admin import admin_keyboard

# 2. تعریف متغیرهای عمومی برای دسترسی راحت در کل پروژه
# نکته مهم: این متغیرها باید برابر با user_keyboard باشند (که کلاس است)، نه user (که ماژول است)
user_menu = user_keyboard
admin_menu = admin_keyboard

# 3. نام‌های مستعار دیگر (اختیاری، برای سازگاری با کدهای قدیمی)
UserMenu = user_keyboard
AdminMenu = admin_keyboard