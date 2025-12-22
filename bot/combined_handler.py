# bot/combined_handler.py

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from bot.keyboards import user
from bot.utils import validate_uuid

logger = logging.getLogger(__name__)

# --- توابع کمکی ---

async def _get_handler_for_panel(panel_name: str):
    """یک نمونه API handler (Async) از فکتوری می‌گیرد."""
    from bot.services.panels.factory import PanelFactory
    try:
        return await PanelFactory.get_panel(panel_name)
    except Exception as e:
        logger.error(f"Failed to get handler for panel {panel_name}: {e}")
        return None

def _process_and_merge_user_data(all_users_map: dict) -> List[Dict[str, Any]]:
    """اطلاعات خام جمع‌آوری شده از پنل‌ها را پردازش نهایی می‌کند."""
    processed_list = []
    for identifier, data in all_users_map.items():
        limit = data.get('usage_limit_GB', 0)
        usage = data.get('current_usage_GB', 0)
        
        data['remaining_GB'] = max(0, limit - usage)
        data['usage_percentage'] = (usage / limit * 100) if limit > 0 else 0
        
        # دیکشنری usage برای سازگاری با تمپلیت‌ها
        data['usage'] = {
            'total_usage_GB': usage,
            'data_limit_GB': limit
        }

        if 'panels' in data and isinstance(data['panels'], set):
            data['panels'] = list(data['panels'])

        final_name = "کاربر ناشناس"
        if data.get('breakdown'):
            for panel_name, panel_details in data['breakdown'].items():
                panel_data = panel_details.get('data', {})
                if panel_data.get('name') or panel_data.get('username'):
                    final_name = panel_data.get('name') or panel_data.get('username')
                    break
        data['name'] = final_name

        processed_list.append(data)
    return processed_list

# --- توابع اصلی (Async & Concurrent) ---

async def get_all_users_combined() -> List[Dict[str, Any]]:
    """اطلاعات کاربران را از تمام پنل‌های فعال به صورت همزمان دریافت و ترکیب می‌کند."""
    from bot.database import db
    
    logger.info("COMBINED_HANDLER: Fetching users from all active panels concurrently.")
    all_users_map = {}
    
    active_panels = await db.get_active_panels()

    # تابع داخلی برای دریافت لیست کاربران از یک پنل
    async def fetch_users_from_panel(panel_config):
        panel_name = panel_config['name']
        panel_type = panel_config['panel_type']
        
        handler = await _get_handler_for_panel(panel_name)
        if not handler:
            return None

        try:
            users = await handler.get_all_users() or []
            return {"users": users, "panel_name": panel_name, "panel_type": panel_type}
        except Exception as e:
            logger.error(f"Could not fetch users from panel '{panel_name}': {e}")
            return None

    # اجرای همزمان
    tasks = [fetch_users_from_panel(p) for p in active_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # پردازش نتایج
    for res in results:
        if not res or isinstance(res, Exception): continue
        
        panel_users = res['users']
        panel_name = res['panel_name']
        panel_type = res['panel_type']

        for user in panel_users:
            identifier = None
            uuid = None
            
            # استخراج شناسه
            if panel_type == 'hiddify':
                uuid = user.get('uuid')
                identifier = uuid
            elif panel_type == 'remnawave':
                uuid = user.get('uuid')
                identifier = uuid
            elif panel_type == 'marzban':
                marzban_username = user.get('username')
                # استفاده از نام کاربری به عنوان شناسه موقت برای سرعت
                identifier = f"marzban_{marzban_username}" 
                uuid = None 

            if not identifier: continue
            
            if identifier not in all_users_map:
                all_users_map[identifier] = {
                    'uuid': uuid,
                    'is_active': False, 'expire': None,
                    'last_online': None,
                    'current_usage_GB': 0, 'usage_limit_GB': 0,
                    'breakdown': {},
                    'panels': set()
                }
            
            if uuid and not all_users_map[identifier].get('uuid'):
                 all_users_map[identifier]['uuid'] = uuid

            # نرمال‌سازی حجم
            limit_gb = 0
            current_gb = 0
            if 'usage_limit_GB' in user:
                limit_gb = float(user['usage_limit_GB'] or 0)
                current_gb = float(user.get('current_usage_GB', 0) or 0)
            elif 'data_limit' in user:
                limit_gb = float(user['data_limit']) / (1024**3) if user['data_limit'] else 0
                current_gb = float(user.get('used_traffic', 0)) / (1024**3) if user.get('used_traffic') else 0

            # ذخیره breakdown
            all_users_map[identifier]['breakdown'][panel_name] = {
                "data": {
                    **user, 
                    "usage_limit_GB": limit_gb, 
                    "current_usage_GB": current_gb
                },
                "type": panel_type
            }
            all_users_map[identifier]['panels'].add(panel_name)
            
            # تجمیع آمار
            status = user.get('status', '').lower()
            is_active = status == 'active' or user.get('is_active', False)
            
            all_users_map[identifier]['is_active'] |= is_active
            all_users_map[identifier]['current_usage_GB'] += current_gb
            all_users_map[identifier]['usage_limit_GB'] += limit_gb

            # مدیریت تاریخ انقضا
            new_expire = user.get('expire')
            if new_expire is not None:
                current_expire = all_users_map[identifier]['expire']
                if current_expire is None or (new_expire > 0 and new_expire < current_expire):
                    all_users_map[identifier]['expire'] = new_expire
    
    return _process_and_merge_user_data(all_users_map)


async def get_combined_user_info(identifier: str) -> Optional[Dict[str, Any]]:
    """اطلاعات یک کاربر خاص را از تمام پنل‌های فعال به صورت همزمان دریافت می‌کند."""
    from bot.database import db
    
    is_uuid = validate_uuid(identifier)
    all_panels = await db.get_active_panels()
    
    hiddify_uuid_to_query = None
    marzban_username_to_query = None

    if is_uuid:
        hiddify_uuid_to_query = identifier
        marzban_username_to_query = await db.get_marzban_username_by_uuid(identifier)
    else:
        marzban_username_to_query = identifier
        hiddify_uuid_to_query = await db.get_uuid_by_marzban_username(identifier)

    user_data_map = {}

    # تابع داخلی درخواست تکی
    async def fetch_single_panel(panel_config):
        panel_name = panel_config['name']
        panel_type = panel_config['panel_type']
        
        handler = await _get_handler_for_panel(panel_name)
        if not handler: 
            return None

        user_info = None
        try:
            if panel_type == 'hiddify' and hiddify_uuid_to_query:
                user_info = await handler.get_user(hiddify_uuid_to_query)
            elif panel_type == 'remnawave' and hiddify_uuid_to_query:
                user_info = await handler.get_user(hiddify_uuid_to_query)
            elif panel_type == 'marzban' and marzban_username_to_query:
                user_info = await handler.get_user(marzban_username_to_query)
        except Exception as e:
            logger.error(f"❌ Error fetching from {panel_name}: {e}")
            return None

        if user_info:
            limit_gb = 0
            current_gb = 0
            if 'usage_limit_GB' in user_info:
                limit_gb = float(user_info['usage_limit_GB'] or 0)
                current_gb = float(user_info.get('current_usage_GB', 0) or 0)
            elif 'data_limit' in user_info:
                limit_gb = float(user_info['data_limit']) / (1024**3) if user_info['data_limit'] else 0
                current_gb = float(user_info.get('used_traffic', 0)) / (1024**3) if user_info.get('used_traffic') else 0
            
            return {
                "name": panel_name,
                "info": {
                    "data": {**user_info, "usage_limit_GB": limit_gb, "current_usage_GB": current_gb},
                    "type": panel_type,
                    "category": panel_config.get('category')
                }
            }
        return None

    # اجرای همزمان
    tasks = [fetch_single_panel(p) for p in all_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            logger.error(f"Unhandled exception during panel fetch: {res}")
        elif res:
            user_data_map[res['name']] = res['info']

    if not user_data_map:
        return None
    
    # تجمیع
    total_usage = sum(p['data'].get('current_usage_GB', 0) for p in user_data_map.values())
    total_limit = sum(p['data'].get('usage_limit_GB', 0) for p in user_data_map.values())
    
    is_active = any(
        (p['data'].get('status') == 'active' or p['data'].get('is_active') == True) 
        for p in user_data_map.values()
    )

    final_info = {
        'breakdown': user_data_map,
        'is_active': is_active,
        'last_online': None,
        'current_usage_GB': total_usage,
        'usage_limit_GB': total_limit,
        'expire': None,
        'uuid': hiddify_uuid_to_query,
        'name': identifier
    }
    
    expires = []
    names = []
    for p in user_data_map.values():
        if p['data'].get('expire'): expires.append(p['data']['expire'])
        if p['data'].get('username'): names.append(p['data']['username'])
        elif p['data'].get('name'): names.append(p['data']['name'])
    
    if expires:
        valid_expires = [e for e in expires if e > 0]
        if valid_expires:
            final_info['expire'] = min(valid_expires)
            
    if names:
        final_info['name'] = names[0]

    final_info['remaining_GB'] = max(0, total_limit - total_usage)
    final_info['usage_percentage'] = (total_usage / total_limit * 100) if total_limit > 0 else 0
    
    return final_info


async def search_user(query: str) -> List[Dict[str, Any]]:
    """یک کاربر را در تمام پنل‌های فعال جستجو می‌کند."""
    query_lower = query.lower()
    results = []
    
    # حالا که get_all_users_combined بهینه شده، این تابع هم سریع است
    all_users = await get_all_users_combined()
    
    for user in all_users:
        match_name = query_lower in user.get('name', '').lower()
        match_uuid = user.get('uuid', '') and query_lower in user.get('uuid', '').lower()
        
        if match_name or match_uuid:
            results.append(user)
            
    return results


async def modify_user_on_all_panels(
    identifier: str,
    add_gb: float = 0,
    add_days: int = 0,
    set_gb: Optional[float] = None,
    set_days: Optional[int] = None,
    target_panel_type: Optional[str] = None,
    target_panel_name: Optional[str] = None
) -> bool:
    """
    تغییرات کاربر را اعمال می‌کند (کاملاً همزمان و Async).
    """
    from bot.database import db
    
    logger.info(f"║ Async Modification started for: {identifier} (Target: {target_panel_name or 'ALL'})")

    is_uuid = validate_uuid(identifier)
    uuid = identifier if is_uuid else await db.get_uuid_by_marzban_username(identifier)
    marzban_username = await db.get_marzban_username_by_uuid(identifier) if is_uuid else identifier

    if not uuid and not marzban_username:
        logger.error(f"❌ User identifier '{identifier}' not resolved.")
        return False
        
    all_panels = await db.get_active_panels()

    # تابع داخلی برای تغییر روی یک پنل خاص
    async def modify_single_panel(panel_config):
        panel_type = panel_config['panel_type']
        panel_name = panel_config['name']

        if target_panel_type and panel_type != target_panel_type: return False
        if target_panel_name and panel_name != target_panel_name: return False

        handler = await _get_handler_for_panel(panel_name)
        if not handler: return False

        success = False
        try:
            if panel_type == 'hiddify' and uuid:
                if await handler.modify_user(uuid, add_gb=add_gb, add_days=add_days):
                    logger.info(f"✅ Modified on Hiddify '{panel_name}'")
                    success = True
            
            elif panel_type == 'remnawave' and uuid:
                if await handler.modify_user(uuid, add_gb=add_gb, add_days=add_days):
                    logger.info(f"✅ Modified on Remnawave '{panel_name}'")
                    success = True
            
            elif panel_type == 'marzban' and marzban_username:
                if await handler.modify_user(marzban_username, add_gb=add_gb, add_days=add_days):
                    logger.info(f"✅ Modified on Marzban '{panel_name}'")
                    success = True
        except Exception as e:
            logger.error(f"Error modifying on {panel_name}: {e}")
        
        return success

    # اجرای همزمان
    tasks = [modify_single_panel(p) for p in all_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # بررسی اینکه آیا حداقل در یک پنل موفق بوده یا نه
    any_success = False
    for res in results:
        if res is True:
            any_success = True

    # ریست کردن فلگ یادآوری تمدید
    if any_success and (add_days > 0 or set_days is not None):
        if uuid:
            uuid_id = await db.get_uuid_id_by_uuid(uuid)
            if uuid_id:
                await db.reset_renewal_reminder_sent(uuid_id)
    
    return any_success


async def delete_user_from_all_panels(identifier: str) -> bool:
    """کاربر را از تمام پنل‌هایی که در آن وجود دارد حذف می‌کند (کاملاً همزمان)."""
    from bot.database import db
    
    user_info = await get_combined_user_info(identifier)
    if not user_info: return False

    all_panels = await db.get_all_panels()
    all_panels_map = {p['name']: p for p in all_panels}

    # تابع داخلی برای حذف از یک پنل
    async def delete_single_panel(panel_name, panel_details):
        panel_config = all_panels_map.get(panel_name)
        if not panel_config: return True # نادیده گرفتن پنل‌های حذف شده
        
        handler = await _get_handler_for_panel(panel_name)
        if not handler: return True

        user_panel_data = panel_details.get('data', {})
        panel_type = panel_details.get('type')
        
        try:
            if panel_type == 'hiddify' and user_panel_data.get('uuid'):
                return await handler.delete_user(user_panel_data['uuid'])
            elif panel_type == 'remnawave' and user_panel_data.get('uuid'):
                return await handler.delete_user(user_panel_data['uuid'])
            elif panel_type == 'marzban' and user_panel_data.get('username'):
                return await handler.delete_user(user_panel_data['username'])
        except Exception as e:
            logger.error(f"Error deleting user from {panel_name}: {e}")
            return False
        
        return True

    # اجرای همزمان حذف از همه پنل‌ها
    tasks = [delete_single_panel(name, details) for name, details in user_info.get('breakdown', {}).items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_success = True
    for res in results:
        if res is False or isinstance(res, Exception):
            all_success = False

    # حذف از دیتابیس لوکال
    if user_info.get('uuid'):
        await db.delete_user_by_uuid(user_info['uuid'])
        
    return all_success