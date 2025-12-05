# bot/services/panels/marzban.py
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Any
import pytz
from .base import BasePanel

logger = logging.getLogger(__name__)

class MarzbanPanel(BasePanel):
    def __init__(self, api_url: str, username: str, password: str, extra_config: dict = None):
        # در مرزبان ما یوزر/پسورد داریم، پس توکن اولیه نداریم
        super().__init__(api_url, username, extra_config)
        self.username = username
        self.password = password
        self.access_token = None
        self.headers = {"Accept": "application/json"}
        self.utc_tz = pytz.utc

    async def _get_access_token(self) -> bool:
        """توکن جدید از مرزبان می‌گیرد."""
        url = f"{self.api_url}/api/admin/token"
        data = {"username": self.username, "password": self.password}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=10) as resp:
                    if resp.status == 200:
                        json_resp = await resp.json()
                        self.access_token = json_resp.get("access_token")
                        self.headers["Authorization"] = f"Bearer {self.access_token}"
                        return True
                    else:
                        logger.error(f"Marzban Login Failed: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Marzban Token Error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, json: dict = None, retry: bool = True) -> Any:
        """متد مرکزی درخواست‌ها با قابلیت تلاش مجدد در صورت انقضای توکن."""
        if not self.access_token:
            if not await self._get_access_token():
                return None

        url = f"{self.api_url}/api/{endpoint.lstrip('/')}"
        
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.request(method, url, json=json, timeout=15) as resp:
                    if resp.status == 401 and retry:
                        logger.warning("Marzban Token Expired. Retrying...")
                        if await self._get_access_token():
                            return await self._request(method, endpoint, json, retry=False)
                    
                    if resp.status == 204: # Success no content
                        return True
                    if resp.status >= 400:
                        logger.error(f"Marzban API Error [{resp.status}]: {await resp.text()}")
                        return None
                        
                    return await resp.json()
        except Exception as e:
            logger.error(f"Marzban Request Exception: {e}")
            return None

    # --- Implementation of Base Methods ---

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None) -> Optional[dict]:
        expire_ts = 0
        if expire_days > 0:
            expire_ts = int((datetime.now() + timedelta(days=expire_days)).timestamp())
        
        payload = {
            "username": name,
            "proxies": {"vless": {}, "vmess": {}, "trojan": {}, "shadowsocks": {}},
            "data_limit": int(limit_gb * (1024**3)),
            "expire": expire_ts,
            "status": "active"
        }
        return await self._request("POST", "user", json=payload)

    async def get_user(self, identifier: str) -> Optional[dict]:
        return await self._request("GET", f"user/{identifier}")

    async def get_all_users(self) -> List[dict]:
        resp = await self._request("GET", "users")
        return resp.get("users", []) if resp else []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        user = await self.get_user(identifier)
        if not user: return False
        
        payload = {}
        
        # --- مدیریت حجم (تبدیل گیگابایت به بایت) ---
        if new_limit_gb is not None:
            payload['data_limit'] = int(new_limit_gb * (1024**3))
        elif add_gb != 0:
            current_limit = user.get('data_limit', 0) or 0
            # اضافه کردن حجم به بایت
            payload['data_limit'] = int(current_limit + (add_gb * (1024**3)))

        # --- مدیریت زمان (Timestamp) ---
        if new_expire_ts is not None:
            payload['expire'] = new_expire_ts
        elif add_days != 0:
            current_expire = user.get('expire', 0)
            now_ts = int(datetime.now().timestamp())
            
            # اگر اشتراک تمام شده بود، از الان اضافه کن، اگر نه، به انتهای قبلی اضافه کن
            base_time = max(current_expire, now_ts) if current_expire else now_ts
            
            # افزودن روزها (۸۶۴۰۰ ثانیه در روز)
            payload['expire'] = base_time + (add_days * 86400)

        if not payload: return True

        res = await self._request("PUT", f"user/{identifier}", json=payload)
        return res is not None

    async def delete_user(self, identifier: str) -> bool:
        res = await self._request("DELETE", f"user/{identifier}")
        return res is True

    async def reset_user_usage(self, identifier: str) -> bool:
        """
        ریست ترافیک در مرزبان با اندپوینت مخصوص انجام می‌شود.
        """
        res = await self._request("POST", f"user/{identifier}/reset")
        return res is not None
        
    async def get_system_stats(self) -> dict:
        return await self._request("GET", "system") or {}

    async def check_connection(self) -> bool:
        try:
            stats = await self.get_system_stats()
            return bool(stats)
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False