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

async def update_schema():
    if not DATABASE_URL:
        print("❌ خطا: DATABASE_URL پیدا نشد. مطمئن شوید فایل .env وجود دارد.")
        return

    print("🔌 در حال اتصال به دیتابیس...")
    engine = create_async_engine(DATABASE_URL)

    async with engine.begin() as conn:
        # ---------------------------------------------------------
        # 1. اضافه کردن ستون remnawave_usage_gb (تغییر قبلی)
        # ---------------------------------------------------------
        try:
            print("⚙️ [1/2] بررسی ستون remnawave_usage_gb...")
            await conn.execute(text("""
                ALTER TABLE usage_snapshots 
                ADD COLUMN IF NOT EXISTS remnawave_usage_gb FLOAT DEFAULT 0.0;
            """))
            print("✅ ستون 'remnawave_usage_gb' بررسی/اضافه شد.")
        except Exception as e:
            print(f"⚠️ خطا در بخش 1: {e}")

        # ---------------------------------------------------------
        # 2. اصلاح ستون updated_at در جدول broadcast_tasks (رفع ارور)
        # ---------------------------------------------------------
        try:
            print("⚙️ [2/2] اصلاح ستون updated_at در جدول broadcast_tasks...")
            await conn.execute(text("""
                ALTER TABLE broadcast_tasks 
                ALTER COLUMN updated_at DROP NOT NULL;
            """))
            print("✅ محدودیت NOT NULL از ستون 'updated_at' با موفقیت برداشته شد.")
        except Exception as e:
            # اگر ارور داد شاید جدول هنوز ساخته نشده یا مشکل دیگری است
            print(f"⚠️ خطا در بخش 2 (ممکن است قبلاً انجام شده باشد): {e}")

    await engine.dispose()
    print("🏁 عملیات دیتابیس به پایان رسید.")

if __name__ == "__main__":
    asyncio.run(update_schema())