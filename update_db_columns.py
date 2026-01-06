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
        # 1. اضافه کردن ستون remnawave_usage_gb
        # ---------------------------------------------------------
        try:
            print("⚙️ [1/3] بررسی ستون remnawave_usage_gb...")
            await conn.execute(text("""
                ALTER TABLE usage_snapshots 
                ADD COLUMN IF NOT EXISTS remnawave_usage_gb FLOAT DEFAULT 0.0;
            """))
            print("✅ ستون 'remnawave_usage_gb' بررسی شد.")
        except Exception as e:
            print(f"⚠️ خطا در بخش 1: {e}")

        # ---------------------------------------------------------
        # 2. اضافه کردن ستون pasarguard_usage_gb (جدید - حل مشکل شما)
        # ---------------------------------------------------------
        try:
            print("⚙️ [2/3] بررسی ستون pasarguard_usage_gb...")
            await conn.execute(text("""
                ALTER TABLE usage_snapshots 
                ADD COLUMN IF NOT EXISTS pasarguard_usage_gb FLOAT DEFAULT 0.0;
            """))
            print("✅ ستون 'pasarguard_usage_gb' با موفقیت اضافه شد.")
        except Exception as e:
            print(f"⚠️ خطا در بخش 2: {e}")

        # ---------------------------------------------------------
        # 3. اصلاح ستون updated_at در جدول broadcast_tasks
        # ---------------------------------------------------------
        try:
            print("⚙️ [3/3] اصلاح ستون updated_at در جدول broadcast_tasks...")
            await conn.execute(text("""
                ALTER TABLE broadcast_tasks 
                ALTER COLUMN updated_at DROP NOT NULL;
            """))
            print("✅ محدودیت NOT NULL از ستون 'updated_at' برداشته شد.")
        except Exception as e:
            print(f"⚠️ خطا در بخش 3 (احتمالاً قبلاً انجام شده): {e}")

    await engine.dispose()
    print("🏁 عملیات دیتابیس به پایان رسید.")

if __name__ == "__main__":
    asyncio.run(update_schema())