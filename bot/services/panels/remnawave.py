# bot/services/panels/remnawave.py

import logging
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
        super().__init__(api_url, api_token, extra_config)
        # اتصال به SDK
        self.client = RemnawaveSDK(
            base_url=self.api_url,
            token=self.api_token
        )

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None) -> Optional[dict]:
        try:
            # تبدیل گیگابایت به بایت
            traffic_limit = int(limit_gb * 1024 * 1024 * 1024) if limit_gb > 0 else 0
            
            # ✅ محاسبه تاریخ انقضا (Timestamp)
            expire_at = None
            if expire_days > 0:
                # محاسبه زمان فعلی + تعداد روزها -> تبدیل به تایم‌استمپ (عدد صحیح)
                expire_date = datetime.now() + timedelta(days=expire_days)
                expire_at = int(expire_date.timestamp())
            
            # ساخت DTO برای درخواست
            request_data = CreateUserRequestDto(
                username=name,
                traffic_limit=traffic_limit,
                expire_at=expire_at, # ✅ فیلد اجباری اضافه شد
                status="ACTIVE" # ✅ حروف بزرگ (ACTIVE) طبق مستندات و ارور
            )
            
            if uuid:
                request_data.uuid = uuid

            # ارسال درخواست
            user: UserResponseDto = await self.client.users.create_user(request_data)
            return user.model_dump() # تبدیل مدل به دیکشنری برای سازگاری با ربات
            
        except Exception as e:
            logger.error(f"Remnawave add_user error: {e}")
            return None

    async def get_user(self, identifier: str) -> Optional[dict]:
        try:
            # در Remnawave شناسه معمولاً UUID است
            user: UserResponseDto = await self.client.users.get_user(identifier)
            return user.model_dump()
        except Exception as e:
            logger.error(f"Remnawave get_user error: {e}")
            return None

    async def get_all_users(self) -> List[dict]:
        try:
            # متد get_all_users_v2 برای دریافت لیست کامل
            response = await self.client.users.get_all_users_v2()
            return [u.model_dump() for u in response.users]
        except Exception as e:
            logger.error(f"Remnawave get_all_users error: {e}")
            return []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        try:
            user = await self.client.users.get_user(identifier)
            if not user: return False

            update_data = UpdateUserRequestDto()
            should_update = False

            # ویرایش حجم
            if new_limit_gb is not None:
                update_data.traffic_limit = int(new_limit_gb * 1024**3)
                should_update = True
            elif add_gb != 0:
                current_limit = user.traffic_limit or 0
                update_data.traffic_limit = int(current_limit + (add_gb * 1024**3))
                should_update = True

            # ویرایش زمان
            if new_expire_ts is not None:
                update_data.expire_at = new_expire_ts
                should_update = True
            elif add_days != 0:
                # منطق افزودن روز (نیاز به محاسبه Timestamp فعلی + روز)
                import time
                current_expire = user.expire_at or int(time.time())
                # اگر زمان انقضا گذشته باشد، از زمان حال محاسبه می‌کنیم
                base_time = max(current_expire, int(time.time()))
                update_data.expire_at = int(base_time + (add_days * 86400))
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
            # متد ریست ترافیک
            await self.client.users.reset_traffic(identifier)
            return True
        except Exception:
            return False

    async def get_system_stats(self) -> dict:
        try:
            # اگر متد system در SDK موجود باشد
            # stats = await self.client.system.get_stats()
            # return stats.model_dump()
            return {} 
        except:
            return {}
            
    async def check_connection(self) -> bool:
        try:
            # یک درخواست سبک برای چک کردن اتصال
            await self.client.users.get_all_users_v2(limit=1)
            return True
        except:
            return False