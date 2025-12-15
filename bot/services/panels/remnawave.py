# bot/services/panels/remnawave.py

import logging
from typing import Optional, List, Any
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
            
            # محاسبه تاریخ انقضا (اگر پنل روز را مستقیم نپذیرد، باید محاسبه شود)
            # اما معمولاً Remnawave قابلیت expire_strategy یا expiration_date دارد.
            # فرض می‌کنیم API یک فیلد برای روز یا تاریخ دارد. 
            # اگر SDK فیلد days نداشت، باید Timestamp بفرستید.
            
            # ساخت DTO برای درخواست
            request_data = CreateUserRequestDto(
                username=name,
                traffic_limit=traffic_limit,
                # برخی نسخه‌ها expiration_days دارند، برخی expiration_date
                # این بخش را بر اساس نسخه دقیق API چک کنید. 
                # فرض بر استاندارد پنل:
                status="active"
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

            # ویرایش زمان (بسته به فیلد موجود در مدل یوزر - مثلا expire_at)
            if new_expire_ts is not None:
                update_data.expire_at = new_expire_ts
                should_update = True
            elif add_days != 0:
                # منطق افزودن روز (نیاز به محاسبه Timestamp فعلی + روز)
                import time
                current_expire = user.expire_at or time.time()
                update_data.expire_at = int(current_expire + (add_days * 86400))
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
            return {} # فعلا خالی تا زمانی که متد دقیق را پیدا کنید
        except:
            return {}
            
    async def check_connection(self) -> bool:
        try:
            # یک درخواست سبک برای چک کردن اتصال
            await self.client.users.get_all_users_v2(limit=1)
            return True
        except:
            return False