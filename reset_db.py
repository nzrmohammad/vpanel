import asyncio
from sqlalchemy import text
from bot.database import db
from bot.db.base import Base

async def reset_tables():
    async with db.engine.begin() as conn:
        print("⚠️ در حال پاکسازی دیتابیس...")
        
        # اجرای دستورات به صورت جداگانه برای جلوگیری از ارور Multiple Commands
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        
        print("✅ دیتابیس کاملاً پاکسازی شد.")
        
        print("🛠 در حال ساخت جداول جدید...")
        await conn.run_sync(Base.metadata.create_all)
        print("🚀 عملیات با موفقیت انجام شد. حالا می‌توانید ربات را اجرا کنید.")

if __name__ == "__main__":
    asyncio.run(reset_tables())