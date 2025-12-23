# bot/combined_handler.py

import logging
import asyncio
from typing import List, Dict, Any, Optional
from bot.services import cache_manager
from bot.services import user_modifier
from bot.database import db
from bot.utils.parsers import validate_uuid

logger = logging.getLogger(__name__)

# --- توابع کمکی برای ترکیب در لحظه ---
def _merge_users_runtime(users_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    کاربران پیدا شده را با هم ادغام می‌کند.
    """
    if not users_list: return None
    if len(users_list) == 1: return users_list[0]

    base = users_list[0].copy()
    if 'breakdown' not in base: base['breakdown'] = {}
    if 'panels' not in base: base['panels'] = []

    for other in users_list[1:]:
        base['current_usage_GB'] += other.get('current_usage_GB', 0)
        base['usage_limit_GB'] += other.get('usage_limit_GB', 0)
        
        if other.get('is_active'): base['is_active'] = True
        
        if other.get('breakdown'):
            base['breakdown'].update(other['breakdown'])
        
        if isinstance(other.get('panels'), list):
            base['panels'].extend(other['panels'])
            
        exp1 = base.get('expire')
        exp2 = other.get('expire')
        if exp2 and exp2 > 0:
            if not exp1 or exp2 < exp1:
                base['expire'] = exp2

    limit = base['usage_limit_GB']
    usage = base['current_usage_GB']
    base['remaining_GB'] = max(0, limit - usage)
    base['usage_percentage'] = (usage / limit * 100) if limit > 0 else 0
    
    return base

# --- توابع اصلی (READ) ---

async def get_all_users_combined() -> List[Dict[str, Any]]:
    return await cache_manager.get_data()

async def search_user(query: str) -> List[Dict[str, Any]]:
    q = query.lower()
    res = []
    data = await cache_manager.get_data()
    for u in data:
        if q in str(u.get('name', '')).lower() or q in str(u.get('uuid', '')).lower():
            res.append(u)
    return res

async def get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    """
    نسخه فیکس شده: جلوگیری از ادغام اشتباهی کاربرانی که نام مشابه ولی UUID متفاوت دارند.
    """
    # 1. تشخیص هویت (Resolve Identity)
    is_uuid = validate_uuid(identifier)
    
    search_uuid = identifier if is_uuid else await db.get_uuid_by_marzban_username(identifier)
    search_name = await db.get_marzban_username_by_uuid(identifier) if is_uuid else identifier
    
    logger.info(f"🔍 Searching Cache For: UUID={search_uuid} | Name={search_name}")

    # 2. دریافت داده‌ها از کش
    all_users = await cache_manager.get_data()
    found_entries = []

    for user in all_users:
        # الف) اولویت اول: تطبیق دقیق UUID (برای هیدیفای/رمنا)
        if search_uuid and str(user.get('uuid')) == str(search_uuid):
            found_entries.append(user)
            continue
        
        # ب) اولویت دوم: تطبیق نام (برای مرزبان)
        u_name = str(user.get('name', '')).lower()
        if search_name and u_name == str(search_name).lower():
            
            # ⛔️ فیکس باگ: بررسی تداخل UUID
            # اگر کاربری که پیدا کردیم خودش UUID دارد (یعنی مال هیدیفای است)
            # اما UUID آن با چیزی که ما دنبالش هستیم فرق دارد، پس این یک تشابه اسمی است!
            # نباید این کاربر را اضافه کنیم.
            
            user_uuid = user.get('uuid')
            
            if user_uuid and search_uuid and str(user_uuid) != str(search_uuid):
                # نامش "Mohammad" است اما UUIDش با محمدِ مدنظر ما فرق دارد -> نادیده بگیر
                continue 
            
            # اگر UUID نداشت (یعنی مرزبان خالص بود) یا UUIDش همخوانی داشت -> اضافه کن
            found_entries.append(user)

    # حذف تکراری‌ها (ممکن است یک یوزر با هر دو شرط مچ شده باشد)
    unique_entries = []
    seen_ids = set()
    for entry in found_entries:
        if id(entry) not in seen_ids:
            unique_entries.append(entry)
            seen_ids.add(id(entry))

    if not unique_entries:
        return None

    return _merge_users_runtime(unique_entries)

# --- توابع تغییرات (WRITE) ---

async def modify_user_on_all_panels(identifier: str, **kwargs) -> bool:
    res = await user_modifier.modify_user_logic(identifier, **kwargs)
    if res:
        asyncio.create_task(cache_manager.fetch_and_update_cache())
    return res

async def delete_user_from_all_panels(identifier: str) -> bool:
    user_info = await get_combined_user_info(identifier)
    res = await user_modifier.delete_user_logic(identifier, user_breakdown=user_info)
    if res:
        asyncio.create_task(cache_manager.fetch_and_update_cache())
    return res