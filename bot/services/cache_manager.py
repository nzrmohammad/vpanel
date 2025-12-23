# bot/services/cache_manager.py

import asyncio
import logging
from datetime import datetime
from bot.services import user_aggregator

logger = logging.getLogger(__name__)

_cached_data = []
_is_updating = False
last_sync_time = None

async def fetch_and_update_cache():
    global _cached_data, _is_updating, last_sync_time
    if _is_updating: return
    _is_updating = True
    try:
        logger.info("♻️ Cache: Syncing from panels...")
        _cached_data = await user_aggregator.fetch_all_users_from_panels()
        last_sync_time = datetime.now()
        logger.info(f"✅ Cache Updated. Total Users: {len(_cached_data)}")
    except Exception as e:
        logger.error(f"❌ Cache Update Failed: {e}")
    finally:
        _is_updating = False

async def get_data():
    if not _cached_data:
        await fetch_and_update_cache()
    return _cached_data

async def sync_task():
    while True:
        await fetch_and_update_cache()
        await asyncio.sleep(600) # 10 Minutes