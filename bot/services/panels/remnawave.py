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
        
        # 1. تبدیل زمان انقضا
        # پنل ممکن است expire_at یا expireAt برگرداند
        expire_val = new_data.get('expire_at') or new_data.get('expireAt')
        if expire_val:
            new_data['expire'] = int(expire_val)
        
        # 2. تبدیل حجم کل (بایت به گیگابایت)
        limit_bytes = new_data.get('traffic_limit') or new_data.get('trafficLimit')
        if limit_bytes:
            new_data['usage_limit_GB'] = float(limit_bytes) / (1024**3)
            new_data['data_limit'] = limit_bytes
        else:
            new_data['usage_limit_GB'] = 0
            
        # 3. تبدیل حجم مصرفی
        used_bytes = new_data.get('traffic_used') or new_data.get('trafficUsed')
        if used_bytes:
            new_data['current_usage_GB'] = float(used_bytes) / (1024**3)
            new_data['used_traffic'] = used_bytes
        else:
            new_data['current_usage_GB'] = 0
            
        # 4. نام کاربر
        if 'username' in new_data and not new_data.get('name'):
            new_data['name'] = new_data['username']
            
        # 5. وضعیت
        status = new_data.get('status', '').upper()
        new_data['is_active'] = (status == 'ACTIVE')

        return new_data

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None) -> Optional[dict]:
        try:
            # محاسبه دقیق بایت
            traffic_limit = 0
            if limit_gb and float(limit_gb) > 0:
                traffic_limit = int(float(limit_gb) * 1024 * 1024 * 1024)
            
            # محاسبه دقیق زمان (Timestamp)
            expire_at = None
            if expire_days and int(expire_days) > 0:
                expire_date = datetime.now() + timedelta(days=int(expire_days))
                expire_at = int(expire_date.timestamp())
            
            # ساخت درخواست
            request_data = CreateUserRequestDto(
                username=name,
                traffic_limit=traffic_limit,
                expire_at=expire_at, 
                status="active"  # ✅ اصلاح شد: حروف کوچک
            )
            
            if uuid:
                try:
                    request_data.uuid = uuid if isinstance(uuid, uuid_lib.UUID) else uuid_lib.UUID(uuid)
                except ValueError:
                    pass

            logger.info(f"Adding Remnawave User: {name}, Limit: {traffic_limit}, Expire: {expire_at}")

            user: UserResponseDto = await self.client.users.create_user(request_data)
            return self._normalize(user.model_dump())
            
        except Exception as e:
            logger.error(f"Remnawave add_user error: {e}")
            return None

    async def get_user(self, identifier: str) -> Optional[dict]:
        try:
            user: UserResponseDto = await self.client.users.get_user(identifier)
            return self._normalize(user.model_dump())
        except Exception as e:
            # لاگ نکنیم بهتر است چون ممکن است کاربر نباشد
            return None

    async def get_all_users(self) -> List[dict]:
        try:
            # تلاش برای متدهای مختلف (سازگاری با نسخه‌های مختلف SDK)
            method = getattr(self.client.users, "get_all_users_v2", None) or \
                     getattr(self.client.users, "get_all_users", None) or \
                     getattr(self.client.users, "get_users", None)
            
            if not method:
                logger.error("Remnawave: No list method found!")
                return []

            response = await method()
            
            users_list = []
            if hasattr(response, 'users'):
                users_list = response.users
            elif isinstance(response, list):
                users_list = response
            
            return [self._normalize(u.model_dump()) for u in users_list]

        except Exception as e:
            logger.error(f"Remnawave get_all_users error: {e}")
            return []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        try:
            user = await self.client.users.get_user(identifier)
            if not user: return False

            update_data = UpdateUserRequestDto()
            should_update = False

            if new_limit_gb is not None:
                update_data.traffic_limit = int(float(new_limit_gb) * 1024**3)
                should_update = True
            elif add_gb != 0:
                current_limit = user.traffic_limit or 0
                update_data.traffic_limit = int(current_limit + (float(add_gb) * 1024**3))
                should_update = True

            if new_expire_ts is not None:
                update_data.expire_at = new_expire_ts
                should_update = True
            elif add_days != 0:
                import time
                current_expire = user.expire_at or int(time.time())
                # اگر زمان انقضا گذشته باشد، از زمان حال محاسبه می‌کنیم
                base_time = max(current_expire, int(time.time()))
                update_data.expire_at = int(base_time + (int(add_days) * 86400))
                should_update = True

            if should_update:
                await self.client.users.update_user(identifier, update_data)
            
            return True
        except Exception as e:
            logger.error(f"Remnawave modify_user error: {e}")
            return False

    async def delete_user(self, identifier: str) -> bool:
        try:
            await self.client.users.delete_user(identifier)
            return True
        except Exception as e:
            logger.error(f"Remnawave delete_user error: {e}")
            return False
            
    async def reset_user_usage(self, identifier: str) -> bool:
        try:
            await self.client.users.reset_traffic(identifier)
            return True
        except Exception:
            return False

    async def get_system_stats(self) -> dict:
        return {} 
            
    async def check_connection(self) -> bool:
        try:
            method = getattr(self.client.users, "get_all_users_v2", None) or \
                     getattr(self.client.users, "get_all_users", None) or \
                     getattr(self.client.users, "get_users", None)
            if method:
                await method(limit=1)
                return True
            return False
        except:
            return False