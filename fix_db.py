# فایل موقت: add_column.py
import asyncio
from bot.database import db
from sqlalchemy import text

async def add_column():
    print("⏳ در حال اضافه کردن ستون allowed_categories...")
    async with db.get_session() as session:
        # دستور SQL برای اضافه کردن ستون JSONB اگر وجود نداشته باشد
        await session.execute(text("""
            ALTER TABLE user_uuids 
            ADD COLUMN IF NOT EXISTS allowed_categories JSONB DEFAULT '[]'::jsonb;
        """))
        await session.commit()
    print("✅ ستون با موفقیت اضافه شد!")

if __name__ == "__main__":
    asyncio.run(add_column())