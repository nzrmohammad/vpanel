# bot/services/panels/hiddify.py
import aiohttp
import logging
import asyncio
from typing import Optional, List, Any
from .base import BasePanel

logger = logging.getLogger(__name__)

class HiddifyPanel(BasePanel):
    def __init__(self, api_url: str, api_key: str, extra_config: dict = None):
        super().__init__(api_url, api_key, extra_config)
        
        # مدیریت Proxy Path طبق داکیومنت (اگر ادمین پث تغییر کرده باشد)
        self.proxy_path = extra_config.get("proxy_path", "")
        base = self.api_url
        if self.proxy_path:
            base = f"{base}/{self.proxy_path.strip('/')}"
        
        # اندپوینت استاندارد API v2
        self.base_url = f"{base}/api/v2/admin"
        
        self.headers = {
            "Hiddify-API-Key": self.api_token,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # ایجاد یک نشست پایدار (Persistent Session)
        # طبق داکیومنت aiohttp، کلاینت سشن باید یک بار ساخته شود.
        timeout = aiohttp.ClientTimeout(total=20, connect=10)
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)

    async def close(self):
        """بستن کانکشن طبق استاندارد"""
        if not self.session.closed:
            await self.session.close()

    async def _request(self, method: str, endpoint: str, json: dict = None) -> Any:
        """ارسال درخواست به API با مدیریت خطای استاندارد"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}/"
        
        try:
            async with self.session.request(method, url, json=json) as resp:
                # طبق استاندارد HTTP:
                # 200-299: موفق
                # 401: خطای احراز هویت
                # 404: منبع پیدا نشد
                
                if resp.status == 401:
                    logger.error(f"Hiddify Auth Error: API Key is invalid. URL: {url}")
                    return None
                
                if resp.status == 404:
                    return None

                if resp.status == 204: # No Content (موفقیت‌آمیز ولی بدون بدنه)
                    return True

                # خواندن بدنه پاسخ
                try:
                    response_data = await resp.json()
                except Exception:
                    # اگر جیسون برنگرداند اما کد 200 بود (برخی اندپوینت‌های خاص)
                    if resp.status < 300:
                        return True
                    logger.error(f"Hiddify Invalid JSON Response: {resp.status}")
                    return None

                if resp.status >= 400:
                    logger.error(f"Hiddify API Error [{resp.status}]: {response_data}")
                    return None
                
                return response_data

        except Exception as e:
            logger.error(f"Hiddify Network Error [{method} {endpoint}]: {e}")
            return None

    # --- پیاده‌سازی متدها طبق داکیومنت Hiddify API v2 ---

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None) -> Optional[dict]:
        payload = {
            "name": name,
            "usage_limit_GB": limit_gb,
            "package_days": expire_days,
            "mode": "no_reset",
            "telegram_id": telegram_id
        }
        # اگر UUID خاصی مد نظر است (معمولاً برای Restore کردن بکاپ)
        if uuid:
            payload["uuid"] = uuid
            
        return await self._request("POST", "user", json=payload)

    async def get_user(self, identifier: str) -> Optional[dict]:
        # در هیدیفای v2، دریافت کاربر با UUID انجام می‌شود: /api/v2/admin/user/{uuid}
        return await self._request("GET", f"user/{identifier}")

    async def get_all_users(self) -> List[dict]:
        """
        طبق خروجی استاندارد پنل شما، این متد یک لیست برمی‌گرداند.
        API: GET /api/v2/admin/user/
        Response: [ {user1}, {user2}, ... ]
        """
        res = await self._request("GET", "user")
        
        if isinstance(res, list):
            return res
            
        # اگر خروجی لیست نبود، یعنی فرمت API با چیزی که انتظار داریم فرق دارد
        # در این حالت لیست خالی برمی‌گردانیم تا برنامه کرش نکند و لاگ می‌زنیم
        logger.warning(f"Unexpected Hiddify Response format (Expected List): {type(res)}")
        return []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        """
        ویرایش کاربر.
        نکته: هیدیفای اندپوینت PATCH دارد که فقط فیلدهای ارسال شده را آپدیت می‌کند.
        """
        payload = {}

        # --- سناریوی ۱: تنظیم مقدار جدید (Set) ---
        if new_limit_gb is not None:
            payload['usage_limit_GB'] = new_limit_gb
        
        # --- سناریوی ۲: افزودن به مقدار قبلی (Add) ---
        # چون API دستور "Add" ندارد، باید اول کاربر را بگیریم، محاسبه کنیم و مقدار جدید را بفرستیم.
        elif add_gb or add_days:
            user = await self.get_user(identifier)
            if not user:
                return False
            
            if add_gb:
                current_limit = user.get('usage_limit_GB', 0) or 0
                payload['usage_limit_GB'] = current_limit + add_gb
            
            if add_days:
                current_days = user.get('package_days', 0) or 0
                payload['package_days'] = current_days + add_days

        # نکته: هیدیفای معمولاً `expire_ts` مستقیم نمی‌پذیرد و `package_days` دارد.
        # اما اگر پنل شما فیلد expiry time دارد، می‌توانید اینجا اضافه کنید.
        
        if not payload:
            return True

        res = await self._request("PATCH", f"user/{identifier}", json=payload)
        return res is not None

    async def delete_user(self, identifier: str) -> bool:
        res = await self._request("DELETE", f"user/{identifier}")
        return res is True

    async def reset_user_usage(self, identifier: str) -> bool:
        # طبق استاندارد برای ریست مصرف، باید current_usage_GB را صفر کنیم
        payload = {"current_usage_GB": 0}
        res = await self._request("PATCH", f"user/{identifier}", json=payload)
        return res is not None

    async def get_system_stats(self) -> dict:
        # اندپوینت اطلاعات سیستم: /api/v2/panel/info
        panel_info_url = self.base_url.replace("/admin", "/panel/info")
        # اینجا از _request استفاده نمی‌کنیم چون URL کمی فرق دارد
        try:
            async with self.session.get(panel_info_url) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return {}
    
    async def check_connection(self) -> bool:
        # برای تست اتصال، سریع‌ترین راه گرفتن اطلاعات سیستم است
        stats = await self.get_system_stats()
        return bool(stats)