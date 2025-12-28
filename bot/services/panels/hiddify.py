# bot/services/panels/hiddify.py
import aiohttp
import logging
from datetime import datetime
from typing import Optional, List, Any
from .base import BasePanel

logger = logging.getLogger(__name__)

class HiddifyPanel(BasePanel):
    def __init__(self, api_url: str, api_key: str, extra_config: dict = None):
        super().__init__(api_url, api_key, extra_config)
        self.proxy_path = extra_config.get("proxy_path", "")
        # ساخت آدرس پایه بر اساس کانفیگ (برخی نسخه ها path دارند)
        base = self.api_url
        if self.proxy_path:
            base = f"{base}/{self.proxy_path.strip('/')}"
        self.base_url = f"{base}/api/v2/admin"
        
        self.headers = {
            "Hiddify-API-Key": self.api_token,
            "Accept": "application/json"
        }

    async def _request(self, method: str, endpoint: str, json: dict = None) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}/" # Hiddify usually likes trailing slash
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.request(method, url, json=json, timeout=15) as resp:
                    if resp.status == 401:
                        logger.error("Hiddify Unauthorized! Check API Key.")
                        return None
                    if resp.status == 204:
                        return True
                        
                    try:
                        resp.raise_for_status()
                        return await resp.json()
                    except Exception:
                        return True # Sometimes endpoints return empty body on success
        except Exception as e:
            logger.error(f"Hiddify Request Error [{endpoint}]: {e}")
            return None

    # --- Implementation ---

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None) -> Optional[dict]:
        payload = {
            "name": name,
            "usage_limit_GB": limit_gb,
            "package_days": expire_days,
            "mode": "no_reset"
        }
        if uuid:
            payload["uuid"] = uuid
            
        return await self._request("POST", "user", json=payload)

    async def get_user(self, identifier: str) -> Optional[dict]:
        # در هیدیفای identifier همان UUID است
        return await self._request("GET", f"user/{identifier}")

    async def get_all_users(self) -> List[dict]:
        res = await self._request("GET", "user")
        # ممکن است ساختار بازگشتی {'users': [...]} یا لیست مستقیم باشد
        if isinstance(res, dict):
            return res.get('users', []) or res.get('results', [])
        return res if isinstance(res, list) else []
    
    async def edit_user(self, uuid_str: str, usage_limit_GB: float = None, expire_date: int = None, **kwargs) -> bool:
        """
        ویرایش کاربر (تمدید) در هیدیفای با لاگ‌های دقیق برای عیب‌یابی
        """
        logger.info(f"🔄 START Hiddify edit_user for {uuid_str}")
        logger.info(f"📥 Inputs: usage_limit_GB={usage_limit_GB}, expire_date={expire_date}")

        try:
            # 1. دریافت اطلاعات فعلی کاربر از پنل
            current_user = await self.get_user(uuid_str)
            if not current_user:
                logger.error(f"❌ User {uuid_str} not found in panel.")
                return False

            logger.info(f"🔍 Current Panel Data: Limit={current_user.get('usage_limit_GB')}, Days={current_user.get('package_days')}")

            final_limit_gb = usage_limit_GB if usage_limit_GB is not None else current_user.get('usage_limit_GB', 0)
            
            final_days = current_user.get('package_days', 0)
            
            if expire_date is not None:
                import time
                now_ts = time.time()
                remaining_seconds = expire_date - now_ts
                final_days = max(0, int(remaining_seconds / 86400))
                logger.info(f"🧮 Calculated Package Days: {remaining_seconds}s / 86400 = {final_days} days")

            payload = {
                "uuid": uuid_str,
                "name": current_user.get('name', f"user_{uuid_str[:8]}"),
                "usage_limit_GB": float(final_limit_gb),
                "package_days": int(final_days),
                "mode": current_user.get('mode', "no_reset"),
                "enable": True,
                "telegram_id": current_user.get('telegram_id'),
                "comment": current_user.get('comment')
            }

            logger.info(f"📤 Sending Edit Payload (POST): {payload}")

            res = await self._request("POST", "user/", json=payload)
            
            if res:
                logger.info(f"✅ Edit User Success. Response UUID: {res.get('uuid')}")
                return True
            else:
                logger.error("❌ Edit User Failed: API returned None or Error.")
                return False

        except Exception as e:
            logger.error(f"❌ Exception in Hiddify edit_user: {e}")
            return False

    async def modify_user(self, uuid: str, data: dict) -> bool:
        """
        ویرایش کاربر با استفاده از متد POST (نسخه Async + لاگ دقیق)
        """
        logger.info(f"🔄 START Modifying user {uuid}")
        logger.info(f"📥 Requested Changes: {data}")

        # 1. دریافت اطلاعات خام کاربر (برای حفظ تنظیمات قبلی)
        # نکته: اینجا باید await داشته باشد
        current_user_raw = await self._request("GET", f"/user/{uuid}/")
        
        if not current_user_raw:
            logger.error(f"❌ User {uuid} not found in Hiddify Panel.")
            return False

        # لاگ اطلاعات فعلی برای مقایسه
        logger.info(f"🔍 Current Panel Data: usage={current_user_raw.get('usage_limit_GB')}, days={current_user_raw.get('package_days')}")

        # 2. جایگذاری مقادیر جدید
        # اگر مقداری در data ارسال شده باشد، جایگزین می‌شود. در غیر این صورت از مقدار قبلی استفاده می‌شود.
        
        # نام
        final_name = data.get("name") or current_user_raw.get("name")
        
        # حجم (GB)
        final_limit = data.get("usage_limit_GB")
        if final_limit is None:
            final_limit = current_user_raw.get("usage_limit_GB", 0)
            
        # روز (Package Days)
        final_days = data.get("package_days")
        if final_days is None:
            final_days = current_user_raw.get("package_days", 0)

        # مود (Mode)
        final_mode = data.get("mode") or current_user_raw.get("mode", "no_reset")

        # 3. ساخت پِی‌لود نهایی (Payload)
        payload = {
            "uuid": uuid,
            "name": final_name,
            "usage_limit_GB": float(final_limit),
            "package_days": int(final_days),
            "mode": final_mode,
            "enable": True,  # معمولاً می‌خواهیم کاربر فعال بماند
            
            # حفظ سایر فیلدهای اختیاری اگر در دیتای خام بودند
            "telegram_id": current_user_raw.get("telegram_id"),
            "comment": current_user_raw.get("comment"),
            "start_date": current_user_raw.get("start_date") 
        }

        # اگر دستور ریست مصرف داده شده باشد
        if data.get("reset_usage"):
             logger.info("⚠️ Reset usage requested via payload flag.")
             # await self.reset_user_usage(uuid) # اگر این متد را هم async کرده‌اید، await بگذارید

        logger.info(f"📤 Sending POST Payload to Panel: {payload}")

        # 4. ارسال درخواست (اینجا هم await لازم است)
        result = await self._request("POST", "/user/", json=payload)
        
        if result:
            logger.info(f"✅ User {uuid} updated successfully.")
            return True
        else:
            logger.error(f"❌ Failed to update user {uuid} (POST request returned None).")
            return False

    async def reset_user_usage(self, identifier: str) -> bool:
        """
        در هیدیفای منیجر جدید، برای ریست حجم باید current_usage_GB را صفر کنیم.
        """
        # روش صحیح برای Hiddify v2/v10+
        payload = {"current_usage_GB": 0}
        
        # ارسال درخواست PATCH به آدرس user/{uuid}
        res = await self._request("PATCH", f"user/{identifier}", json=payload)
        
        # اگر نتیجه None نباشد یعنی موفقیت‌آمیز بوده
        return res is not None

    async def get_system_stats(self) -> dict:
        # هیدیفای پنل اینفو دارد
        base_url_panel = self.base_url.replace("/api/v2/admin", "/api/v2/panel/info")
        try:
             async with aiohttp.ClientSession(headers=self.headers) as session:
                 async with session.get(base_url_panel) as resp:
                     if resp.status == 200:
                         return await resp.json()
        except:
            pass
        return {}

    async def check_connection(self) -> bool:
        stats = await self.get_system_stats()
        return bool(stats)