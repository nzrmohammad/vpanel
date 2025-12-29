# bot/admin_handlers/user_management/state.py

# متغیرهای سراسری که قبلاً در فایل اصلی بودند
bot = None
admin_conversations = {}

def set_bot(b):
    """تنظیم آبجکت ربات"""
    global bot
    bot = b

def set_conversations(conv_dict):
    """تنظیم دیکشنری استیت‌ها"""
    global admin_conversations
    # ما رفرنس دیکشنری اصلی را آپدیت می‌کنیم تا هماهنگی حفظ شود
    admin_conversations = conv_dict