# bot/services/user_aggregator.py

import logging
import asyncio
from typing import Dict, Any, List, Optional
from bot.services.panels.factory import PanelFactory
from bot.database import db

logger = logging.getLogger(__name__)

async def _get_handler(panel_name: str):
    try:
        return await PanelFactory.get_panel(panel_name)
    except Exception as e:
        logger.error(f"Failed to get handler for panel {panel_name}: {e}")
        return None

def _process_and_merge_user_data(all_users_map: dict) -> List[Dict[str, Any]]:
    """تبدیل دیکشنری تجمیع شده به لیست نهایی"""
    processed_list = []
    for identifier, data in all_users_map.items():
        limit = data.get('usage_limit_GB', 0)
        usage = data.get('current_usage_GB', 0)
        
        data['remaining_GB'] = max(0, limit - usage)
        data['usage_percentage'] = (usage / limit * 100) if limit > 0 else 0
        data['usage'] = {'total_usage_GB': usage, 'data_limit_GB': limit}

        if 'panels' in data and isinstance(data['panels'], set):
            data['panels'] = list(data['panels'])

        # پیدا کردن بهترین نام برای نمایش
        final_name = "کاربر ناشناس"
        if data.get('breakdown'):
            for _, panel_details in data['breakdown'].items():
                p_data = panel_details.get('data', {})
                if p_data.get('name') or p_data.get('username'):
                    final_name = p_data.get('name') or p_data.get('username')
                    break
        data['name'] = final_name
        processed_list.append(data)
    return processed_list

async def fetch_all_users_from_panels() -> List[Dict[str, Any]]:
    """
    اطلاعات را از تمام پنل‌ها می‌گیرد.
    نکته مهم: Hiddify و Remnawave اگر UUID یکسان داشته باشند، اینجا یکی می‌شوند.
    """
    logger.info("AGGREGATOR: Fetching users from all active panels concurrently.")
    all_users_map = {}
    active_panels = await db.get_active_panels()

    async def fetch_single(panel_config):
        p_name = panel_config['name']
        p_type = panel_config['panel_type']
        handler = await _get_handler(p_name)
        if not handler: return None
        try:
            users = await handler.get_all_users() or []
            return {"users": users, "panel_name": p_name, "panel_type": p_type}
        except Exception as e:
            logger.error(f"Fetch error {p_name}: {e}")
            return None

    tasks = [fetch_single(p) for p in active_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if not res or isinstance(res, Exception): continue
        
        panel_users = res['users']
        panel_name = res['panel_name']
        panel_type = res['panel_type']

        for user in panel_users:
            identifier = None
            uuid = None
            
            # --- منطق شناسایی و ادغام اولیه ---
            if panel_type in ['hiddify', 'remnawave']:
                # برای این پنل‌ها، شناسه همان UUID است
                uuid = user.get('uuid')
                identifier = uuid
            elif panel_type == 'marzban':
                # برای مرزبان شناسه موقت می‌سازیم
                username = user.get('username')
                identifier = f"marzban_{username}"
                uuid = None 

            if not identifier: continue
            
            # ایجاد ساختار کاربر اگر وجود ندارد
            if identifier not in all_users_map:
                all_users_map[identifier] = {
                    'uuid': uuid,
                    'is_active': False, 'expire': None,
                    'last_online': None,
                    'current_usage_GB': 0, 'usage_limit_GB': 0,
                    'breakdown': {},
                    'panels': set()
                }
            
            # آپدیت UUID اگر قبلاً نداشته (مثلاً در مرزبان)
            if uuid and not all_users_map[identifier].get('uuid'):
                 all_users_map[identifier]['uuid'] = uuid

            # نرمال‌سازی حجم‌ها
            limit_gb = 0
            current_gb = 0
            if 'usage_limit_GB' in user:
                limit_gb = float(user['usage_limit_GB'] or 0)
                current_gb = float(user.get('current_usage_GB', 0) or 0)
            elif 'data_limit' in user:
                limit_gb = float(user['data_limit']) / (1024**3) if user['data_limit'] else 0
                current_gb = float(user.get('used_traffic', 0)) / (1024**3) if user.get('used_traffic') else 0

            # ذخیره جزئیات پنل
            all_users_map[identifier]['breakdown'][panel_name] = {
                "data": {**user, "usage_limit_GB": limit_gb, "current_usage_GB": current_gb},
                "type": panel_type
            }
            all_users_map[identifier]['panels'].add(panel_name)
            
            # جمع‌بندی آمار
            status = str(user.get('status', '')).lower()
            is_active = status == 'active' or user.get('is_active', False)
            all_users_map[identifier]['is_active'] |= is_active
            all_users_map[identifier]['current_usage_GB'] += current_gb
            all_users_map[identifier]['usage_limit_GB'] += limit_gb

            # مدیریت انقضا (کمترین انقضای معتبر)
            new_expire = user.get('expire')
            
            # --- اصلاحیه برای هیدیفای ---
            # اگر پارامتر expire وجود نداشت، پارامترهای دیگر مثل package_days بررسی می‌شوند
            if new_expire is None:
                new_expire = user.get('package_days')  # این معمولا در هیدیفای عدد روز است
                if new_expire is None:
                     new_expire = user.get('expiry_time') # برای اطمینان
            # ---------------------------

            if new_expire:
                curr_expire = all_users_map[identifier]['expire']
                if curr_expire is None or (new_expire > 0 and new_expire < curr_expire):
                    all_users_map[identifier]['expire'] = new_expire

    return _process_and_merge_user_data(all_users_map)