# فایل update_db_columns.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

# لود کردن متغیرهای محیطی برای دسترسی به آدرس دیتابیس
load_dotenv()

# دریافت آدرس دیتابیس
DATABASE_URL = os.getenv("DATABASE_URL")

# اصلاح درایور برای asyncpg
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

async def add_columns():
    if not DATABASE_URL:
        print("❌ خطا: DATABASE_URL پیدا نشد. مطمئن شوید فایل .env وجود دارد.")
        return

    print("🔌 در حال اتصال به دیتابیس...")
    engine = create_async_engine(DATABASE_URL)

    async with engine.begin() as conn:
        try:
            print("⚙️ در حال اضافه کردن ستون remnawave_usage_gb...")
            
            # دستور SQL برای اضافه کردن ستون
            await conn.execute(text("""
                ALTER TABLE usage_snapshots 
                ADD COLUMN IF NOT EXISTS remnawave_usage_gb FLOAT DEFAULT 0.0;
            """))
            
            print("✅ ستون 'remnawave_usage_gb' با موفقیت اضافه شد!")
            
        except Exception as e:
            print(f"❌ خطا: {e}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(add_columns())