# bot/custom_bot.py

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

from bot.bot_instance import bot
from bot.database import db
from bot.admin_router import register_admin_handlers
from bot.user_router import register_user_handlers
from bot.services import cache_manager 

# تنظیمات لاگینگ برای دیدن خطاها
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """تابع اصلی اجرای ربات"""
    try:
        # 1. اتصال به دیتابیس و ساخت جداول
        logger.info("💾 Initializing Database...")
        await db.init_db()
        
        # 2. فعال‌سازی هندلرها
        logger.info("📡 Registering Handlers...")
        register_admin_handlers(bot, None)
        register_user_handlers()
        
        # --- NEW: شروع تسک بروزرسانی خودکار کش در پس‌زمینه ---
        logger.info("⏳ Starting Background Cache Sync...")
        asyncio.create_task(cache_manager.sync_task())
        
        # 3. حذف وب‌هوک‌های احتمالی قبلی
        await bot.delete_webhook(drop_pending_updates=True)
        
        # 4. استارت پولینگ (بی‌نهایت)
        print("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
        print("   🤖 Bot is running successfully!   ")
        print("   Press Ctrl+C to stop              ")
        print("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
        
        await bot.infinity_polling()

    except Exception as e:
        logger.error(f"❌ Critical Error: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
    except Exception as e:
        print(f"\n❌ Failed to start bot: {e}")