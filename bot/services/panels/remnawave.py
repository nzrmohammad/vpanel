# bot/services/panels/remnawave.py

import logging
import uuid as uuid_lib
from typing import Optional, List, Any
from datetime import datetime, timedelta
from remnawave import RemnawaveSDK
from remnawave.models import (
    UserResponseDto, 
    CreateUserRequestDto, 
    UpdateUserRequestDto,
)
from .base import BasePanel

logger = logging.getLogger(__name__)

class RemnawavePanel(BasePanel):
    def __init__(self, api_url: str, api_token: str, extra_config: dict = None):
        if not api_url.startswith(("http://", "https://")):
            api_url = f"https://{api_url}"
            
        super().__init__(api_url, api_token, extra_config)
        self.client = RemnawaveSDK(base_url=self.api_url, token=self.api_token)

    def _normalize(self, data: dict) -> dict:
        """استانداردسازی داده‌های دریافتی از پنل"""
        if not data: return {}
        new_data = data.copy()
        
        # 1. تبدیل زمان انقضا (datetime یا int)
        expire_val = new_data.get('expire_at') or new_data.get('expireAt')
        if expire_val:
            if isinstance(expire_val, datetime):
                new_data['expire'] = int(expire_val.timestamp())
            else:
                try: new_data['expire'] = int(expire_val)
                except: new_data['expire'] = None
        
        # 2. تبدیل حجم کل (traffic_limit_bytes به گیگابایت)
        limit_bytes = new_data.get('traffic_limit_bytes') or new_data.get('traffic_limit') or new_data.get('trafficLimit')
        if limit_bytes:
            new_data['usage_limit_GB'] = float(limit_bytes) / (1024**3)
            new_data['data_limit'] = limit_bytes
        else:
            new_data['usage_limit_GB'] = 0
            
        # 3. تبدیل حجم مصرفی
        used_bytes = new_data.get('traffic_used_bytes') or new_data.get('traffic_used') or new_data.get('trafficUsed')
        if not used_bytes and 'user_traffic' in new_data and isinstance(new_data['user_traffic'], dict):
             used_bytes = new_data['user_traffic'].get('used_traffic_bytes')
        
        if used_bytes:
            new_data['current_usage_GB'] = float(used_bytes) / (1024**3)
            new_data['used_traffic'] = used_bytes
        else:
            new_data['current_usage_GB'] = 0
            
        # 4. نام کاربر
        if 'username' in new_data and not new_data.get('name'):
            new_data['name'] = new_data['username']
            
        # 5. وضعیت
        status = str(new_data.get('status', '')).upper()
        new_data['is_active'] = ('ACTIVE' in status)

        return new_data

    # ✅ دریافت لیست اسکوادها
    async def get_active_squads(self) -> List[dict]:
        try:
            # تلاش برای یافتن متد صحیح در SDK برای لیست کردن Squads
            method_ctrl = getattr(self.client, "internal_squads", None)
            if not method_ctrl: return []
            
            get_method = getattr(method_ctrl, "get_all_internal_squads", None) or \
                         getattr(method_ctrl, "get_internal_squads", None) or \
                         getattr(method_ctrl, "get_all", None)
            
            if not get_method: return []

            response = await get_method()
            
            squads_list = []
            raw_items = response.items if hasattr(response, 'items') else (response if isinstance(response, list) else [])
            
            for s in raw_items:
                # تبدیل مدل به دیکشنری
                s_dict = s.model_dump() if hasattr(s, 'model_dump') else (s.__dict__ if hasattr(s, '__dict__') else str(s))
                if isinstance(s_dict, dict):
                    squads_list.append({
                        'uuid': str(s_dict.get('uuid', '')),
                        'name': s_dict.get('name', 'Unknown Squad')
                    })
            return squads_list
        except Exception as e:
            logger.error(f"Error getting squads: {e}")
            return []

    # ✅ متد کامل ساخت کاربر
    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None) -> Optional[dict]:
        try:
            # محاسبه حجم به بایت
            traffic_limit = 0
            if limit_gb and float(limit_gb) > 0:
                traffic_limit = int(float(limit_gb) * 1024 * 1024 * 1024)
            
            # محاسبه زمان انقضا
            expire_at = None
            if expire_days and int(expire_days) > 0:
                expire_date = datetime.now() + timedelta(days=int(expire_days))
                expire_at = int(expire_date.timestamp())
            
            # تنظیم درخواست
            request_data = CreateUserRequestDto(
                username=name,
                traffic_limit_bytes=traffic_limit,  # نام فیلد صحیح (Bytes)
                expire_at=expire_at, 
                status="ACTIVE", # حروف بزرگ
                telegram_id=int(telegram_id) if telegram_id and str(telegram_id).isdigit() else None
            )
            
            if uuid:
                try:
                    request_data.uuid = uuid if isinstance(uuid, uuid_lib.UUID) else uuid_lib.UUID(uuid)
                except ValueError: pass

            # 1. ارسال درخواست ساخت کاربر
            user_resp: UserResponseDto = await self.client.users.create_user(request_data)
            
            # 2. افزودن به اسکواد (اگر انتخاب شده باشد)
            if squad_uuid:
                try:
                    squads_ctrl = getattr(self.client, "internal_squads", None)
                    if squads_ctrl:
                        add_method = getattr(squads_ctrl, "add_users_to_internal_squad", None) or \
                                     getattr(squads_ctrl, "add_users", None)
                        
                        if add_method:
                            # ارسال درخواست عضویت در گروه
                            await add_method(uuid=squad_uuid, users=[user_resp.uuid])
                            logger.info(f"User {name} added to squad {squad_uuid}")
                except Exception as ex:
                    logger.error(f"Failed to add to squad: {ex}")

            return self._normalize(user_resp.model_dump())
            
        except Exception as e:
            logger.error(f"Remnawave add_user error: {e}")
            return None

    # سایر متدها...
    async def get_user(self, identifier: str) -> Optional[dict]:
        try:
            user = await self.client.users.get_user(identifier)
            return self._normalize(user.model_dump())
        except: return None

    async def get_all_users(self) -> List[dict]:
        try:
            method = getattr(self.client.users, "get_all_users_v2", None) or \
                     getattr(self.client.users, "get_all_users", None) or \
                     getattr(self.client.users, "get_users", None)
            if not method: return []
            response = await method()
            users_list = response.users if hasattr(response, 'users') else (response if isinstance(response, list) else [])
            return [self._normalize(u.model_dump()) for u in users_list]
        except: return []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        try:
            user = await self.client.users.get_user(identifier)
            if not user: return False

            update_data = UpdateUserRequestDto()
            should_update = False
            
            # استفاده از traffic_limit_bytes
            current_limit = getattr(user, 'traffic_limit_bytes', 0) or 0

            if new_limit_gb is not None:
                update_data.traffic_limit_bytes = int(float(new_limit_gb) * 1024**3)
                should_update = True
            elif add_gb != 0:
                update_data.traffic_limit_bytes = int(current_limit + (float(add_gb) * 1024**3))
                should_update = True

            if new_expire_ts is not None:
                update_data.expire_at = new_expire_ts
                should_update = True
            elif add_days != 0:
                import time
                current_expire = user.expire_at
                if isinstance(current_expire, datetime):
                    current_expire = int(current_expire.timestamp())
                base_time = max(current_expire or int(time.time()), int(time.time()))
                update_data.expire_at = int(base_time + (int(add_days) * 86400))
                should_update = True

            if should_update:
                await self.client.users.update_user(identifier, update_data)
            return True
        except: return False

    async def delete_user(self, identifier: str) -> bool:
        try:
            await self.client.users.delete_user(identifier)
            return True
        except: return False