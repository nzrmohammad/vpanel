# fix_db.py
import asyncio
from sqlalchemy import text
from bot.database import db

async def fix_database():
    print("⏳ در حال اضافه کردن ستون plan_id به جدول users...")
    try:
        async with db.get_session() as session:
            # دستور SQL برای اضافه کردن ستون plan_id و برقراری رابطه با جدول plans
            await session.execute(text("ALTER TABLE users ADD COLUMN plan_id INTEGER REFERENCES plans(id) ON DELETE SET NULL;"))
            await session.commit()
        print("✅ انجام شد! ستون plan_id با موفقیت اضافه شد.")
    except Exception as e:
        print(f"❌ خطا: {e}")
        print("راهنما: احتمالا ستون از قبل وجود دارد یا دیتابیس متصل نیست.")

if __name__ == "__main__":
    asyncio.run(fix_database())