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
        ویرایش کاربر در هیدیفای (هماهنگ با purchase.py)
        """
        try:
            # 1. دریافت اطلاعات فعلی کاربر (برای حفظ نام و تنظیمات دیگر)
            # متد get_user باید قبلاً در کلاس پیاده‌سازی شده باشد
            current_user = await self.get_user(uuid_str)
            
            if not current_user:
                # اگر کاربر پیدا نشد، شاید بهتر باشد لاگ کنید
                return False

            # 2. آماده‌سازی مسیر API
            # نکته: در هیدیفای معمولاً ادیت همان مسیر ساخت است
            path = f"{self.api_path}/user/"
            
            # 3. محاسبه حجم به بایت (هیدیفای بایت می‌گیرد)
            # اگر مقدار جدید فرستاده شده بود، تبدیل کن، وگرنه مقدار قبلی را نگه دار
            if usage_limit_GB is not None:
                final_limit_bytes = int(usage_limit_GB * 1024**3)
            else:
                # تلاش برای خواندن مقدار قبلی از خروجی get_user
                final_limit_bytes = current_user.get('usage_limit', 0)

            # 4. تنظیم تاریخ انقضا
            # purchase.py تایم‌استمپ می‌فرستد. هیدیفای expiry_time را قبول می‌کند
            final_expiry = expire_date if expire_date is not None else current_user.get('expiry_time')

            payload = {
                "uuid": uuid_str,
                "name": current_user.get('name', f"user_{uuid_str[:8]}"),
                "usage_limit": final_limit_bytes,
                "package_days": 0, # وقتی expiry_time می‌دهیم، این را صفر می‌گذاریم تا تداخل نکند
                "expiry_time": final_expiry,
                # برخی تنظیمات که نباید بپرند:
                "mode": current_user.get('mode', "no_reset"), 
                "enable": True
            }

            # 5. ارسال درخواست
            # نکته: اگر متد post جواب نداد، متد patch را تست کنید. 
            # اما استاندارد هیدیفای برای آپدیت معمولا POST روی UUID موجود است.
            async with self.session.post(path, json=payload) as resp:
                if resp.status in [200, 201, 204]:
                    return True
                else:
                    # اگر ارور داد، ممکن است نیاز به PATCH باشد (بسته به نسخه پنل)
                    # text = await resp.text()
                    # print(f"Edit failed with POST: {text}")
                    return False
                    
        except Exception as e:
            print(f"Error in Hiddify edit_user: {e}")
            return False

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        # هیدیفای لاجیک جمع زدن ندارد، باید ابتدا یوزر را بگیریم
        # اما برای سادگی، اگر payload مستقیم دارید اینجا پیاده کنید.
        # چون API هیدیفای معمولا مقادیر نهایی را می‌گیرد:
        
        payload = {}
        # نکته: هیدیفای به جای Expire Timestamp معمولا Package Days دارد.
        # اما اینجا فرض را بر API استاندارد v2 می‌گذاریم که usage_limit_GB میگیرد.
        
        # اگر نیاز به محاسبه دقیق دارید، ابتدا get_user کنید:
        user = await self.get_user(identifier)
        if not user: return False
        
        if new_limit_gb:
            payload['usage_limit_GB'] = new_limit_gb
        elif add_gb:
             current_limit = user.get('usage_limit_GB', 0)
             payload['usage_limit_GB'] = current_limit + add_gb
             
        # برای روز در هیدیفای کمی پیچیده است (package_days vs expiry date).
        # ساده‌ترین راه افزایش package_days است اگر supported باشد.
        if add_days:
            current_days = user.get('package_days', 0) or 0
            payload['package_days'] = current_days + add_days

        return await self._request("PATCH", f"user/{identifier}", json=payload) is not None

    async def delete_user(self, identifier: str) -> bool:
        res = await self._request("DELETE", f"user/{identifier}")
        return res is True

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