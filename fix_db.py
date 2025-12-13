# fix_db.py
import asyncio
from sqlalchemy import text
from bot.database import db

async def add_column():
    print("⏳ در حال اضافه کردن ستون description به دیتابیس...")
    try:
        async with db.get_session() as session:
            # دستور اضافه کردن ستون
            await session.execute(text("ALTER TABLE server_categories ADD COLUMN description TEXT;"))
            await session.commit()
        print("✅ انجام شد! ستون description با موفقیت اضافه شد.")
    except Exception as e:
        print(f"❌ خطا: {e}")
        print("احتمالا ستون از قبل وجود دارد یا مشکل اتصال دارید.")

if __name__ == "__main__":
    asyncio.run(add_column())