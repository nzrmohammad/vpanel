# bot/custom_bot.py

import asyncio
import logging
from dotenv import load_dotenv

# 1. بارگذاری متغیرهای محیطی (بسیار مهم که اول باشد)
load_dotenv()

from bot.bot_instance import bot
from bot.database import db
from bot.admin_router import register_admin_handlers
from bot.user_router import register_user_handlers

# تنظیمات لاگینگ برای دیدن خطاها
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """تابع اصلی اجرای ربات"""
    try:
        # 2. اتصال به دیتابیس و ساخت جداول (اگر نباشند)
        logger.info("💾 Initializing Database...")
        await db.init_db()
        
        # 3. فعال‌سازی هندلرها (فراخوانی دکوریتورها)
        logger.info("📡 Registering Handlers...")
        register_admin_handlers(bot, None)
        register_user_handlers()
        
        # 4. حذف وب‌هوک‌های احتمالی قبلی (برای جلوگیری از تداخل با پولینگ)
        await bot.delete_webhook(drop_pending_updates=True)
        
        # 5. استارت پولینگ (بی‌نهایت)
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