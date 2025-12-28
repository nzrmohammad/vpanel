# bot/utils/network.py

import logging
import asyncio
from bot.bot_instance import bot

logger = logging.getLogger(__name__)

async def _safe_edit(chat_id: int, msg_id: int, text: str, **kwargs):
    """
    ویرایش امن پیام با قابلیت دیباگ و مدیریت خطاهای رایج تلگرام.
    """
    try:
        # تنظیم پیش‌فرض برای حالت نمایش
        kwargs.setdefault('parse_mode', 'MarkdownV2')
        
        await bot.edit_message_text(
            text=text, 
            chat_id=chat_id, 
            message_id=msg_id, 
            **kwargs
        )
        
    except Exception as e:
        # نادیده گرفتن خطای "پیام تغییر نکرده است" (چون عملیات عملاً موفق بوده)
        if 'message is not modified' in str(e).lower():
            return

        # نمایش دقیق خطا و متنی که باعث خطا شده در کنسول
        print("\n" + "🔴" * 20)
        print(f"[ERROR] Safe Edit Failed for User: {chat_id}")
        print(f"❌ Exception: {e}")
        print(f"📩 Content:")
        print(f"'{text}'") 
        print("🔴" * 20 + "\n")
        
        logger.error(f"Safe edit failed for {chat_id}: {e}")

async def delete_message_delayed(chat_id, message_id, delay):
    """
    حذف پیام با تاخیر (قابل استفاده در تسک‌های پس‌زمینه)
    این تابع عمومی است و در همه جای ربات قابل استفاده می‌باشد.
    """
    if delay <= 0:
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        return

    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        # خطاهای معمول مثل "پیام یافت نشد" را لاگ نکنیم بهتر است
        if "message to delete not found" not in str(e):
            logger.warning(f"Failed to delete message (delayed): {e}")