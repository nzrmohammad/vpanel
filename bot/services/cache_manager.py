# bot/services/cache_manager.py

import asyncio
import logging
from datetime import datetime
from bot.services import user_aggregator

logger = logging.getLogger(__name__)

# مخزن داده در رم
_cached_data = []
_is_updating = False
last_sync_time = None

async def fetch_and_update_cache():
    """آپدیت کردن لیست کاربران در رم (توسط تسک یا تغییرات دستی)"""
    global _cached_data, _is_updating, last_sync_time
    
    if _is_updating: return
    _is_updating = True
    
    try:
        new_data = await user_aggregator.fetch_all_users_from_panels()
        _cached_data = new_data
        last_sync_time = datetime.now()
        logger.info(f"✅ Cache Updated! Total Users in RAM: {len(_cached_data)}")
    except Exception as e:
        logger.error(f"❌ Cache Update Failed: {e}", exc_info=True)
    finally:
        _is_updating = False

async def get_data():
    """خواندن سریع داده‌ها"""
    if not _cached_data:
        await fetch_and_update_cache()
    return _cached_data

async def sync_task():
    """تسک پس‌زمینه برای آپدیت خودکار (هر ۱۰ دقیقه)"""
    while True:
        await fetch_and_update_cache()
        await asyncio.sleep(600)