# bot/utils/decorators.py

from functools import wraps
from telebot import types
from bot.config import ADMIN_IDS
from bot.database import db

def admin_only(func):
    """
    دکوریتور: فقط اجازه دسترسی به ادمین‌های تعریف شده در کانفیگ را می‌دهد.
    اگر کاربر ادمین نباشد، تابع اصلا اجرا نمی‌شود.
    """
    @wraps(func)
    async def wrapper(message, *args, **kwargs):
        # پشتیبانی از Message و CallbackQuery
        if isinstance(message, types.CallbackQuery):
            user_id = message.from_user.id
        else:
            user_id = message.from_user.id

        if user_id not in ADMIN_IDS:
            # می‌توانیم اینجا لاگ کنیم که یک فرد ناشناس تلاش کرده
            return
            
        return await func(message, *args, **kwargs)
    return wrapper

def require_auth(func):
    """
    دکوریتور: چک می‌کند کاربر در دیتابیس وجود داشته باشد و مسدود (Ban) نباشد.
    """
    @wraps(func)
    async def wrapper(message, *args, **kwargs):
        if isinstance(message, types.CallbackQuery):
            user_id = message.from_user.id
            chat_id = message.message.chat.id
        else:
            user_id = message.from_user.id
            chat_id = message.chat.id

        user = await db.get_user(user_id)
        
        if not user:
            # کاربر اصلا وجود ندارد (شاید دیتابیس پاک شده)
            # اینجا می‌توانیم کاربر را ثبت نام کنیم یا ارور بدهیم
            return

        if user.get('is_banned'):
            # اگر بن بود، هیچ کاری نکنیم (سکوت)
            return 
            
        return await func(message, *args, **kwargs)
    return wrapper