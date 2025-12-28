# migrate_sharing.py
import asyncio
from bot.db.base import DatabaseManager, Base
import os

async def init_sharing_table():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is missing!")
        return

    print("🔌 Connecting to DB...")
    db = DatabaseManager(db_url)
    
    async with db.engine.begin() as conn:
        # این دستور فقط جداولی که وجود ندارند را می‌سازد
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ SharedRequest table created successfully.")
    await db.close()

if __name__ == "__main__":
    asyncio.run(init_sharing_table())