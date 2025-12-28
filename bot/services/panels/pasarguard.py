# bot/services/panels/pasarguard.py
import logging
import aiohttp
import time
from typing import Optional, List, Any
from datetime import datetime, timedelta
from .base import BasePanel

logger = logging.getLogger(__name__)

class PasarGuardPanel(BasePanel):
    def __init__(self, api_url: str, username: str, password: str, extra_config: dict = None):
        super().__init__(api_url, username, extra_config)
        self.username = username
        self.password = password
        self.access_token = None
        
        # هدرهای پیش‌فرض
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # ایجاد سشن پایدار (Connection Pooling)
        timeout = aiohttp.ClientTimeout(total=20, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if not self.session.closed:
            await self.session.close()

    async def _get_access_token(self) -> bool:
        """دریافت توکن ادمین از پاسارگارد"""
        # نکته: در اکثر پنل‌های FastAPI آدرس توکن به این صورت است
        url = f"{self.api_url}/api/admin/token"
        data = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            # ارسال به صورت x-www-form-urlencoded
            async with self.session.post(url, data=data) as resp:
                if resp.status == 200:
                    json_resp = await resp.json()
                    self.access_token = json_resp.get("access_token")
                    self.headers["Authorization"] = f"Bearer {self.access_token}"
                    return True
                else:
                    logger.error(f"PasarGuard Login Failed: {resp.status} | {await resp.text()}")
                    return False
        except Exception as e:
            logger.error(f"PasarGuard Token Error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, json: dict = None, retry_auth: bool = True) -> Any:
        if not self.access_token:
            if not await self._get_access_token():
                return None

        url = f"{self.api_url}/api/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.request(method, url, json=json, headers=self.headers) as resp:
                if resp.status == 401 and retry_auth:
                    logger.warning("PasarGuard Token Expired. Refreshing...")
                    if await self._get_access_token():
                        return await self._request(method, endpoint, json, retry_auth=False)
                    return None

                if resp.status == 204:
                    return True

                if resp.status >= 400:
                    logger.error(f"PasarGuard API Error [{resp.status}]: {await resp.text()}")
                    return None
                
                return await resp.json()
        except Exception as e:
            logger.error(f"PasarGuard Request Exception: {e}")
            return None

    # --- پیاده‌سازی متدها ---

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None) -> Optional[dict]:
        expire_ts = 0
        if expire_days > 0:
            expire_ts = int((datetime.utcnow() + timedelta(days=expire_days)).timestamp())
        
        # تنظیمات پروکسی (ممکن است بسته به کانفیگ پنل شما متفاوت باشد)
        proxies = {"vless": {}, "vmess": {}, "trojan": {}, "shadowsocks": {}}

        payload = {
            "username": name,
            "proxies": proxies,
            "data_limit": int(limit_gb * (1024**3)) if limit_gb else 0,
            "expire": expire_ts if expire_ts > 0 else None,
            "status": "active",
            "note": f"Created by Bot (TG ID: {telegram_id})" if telegram_id else "Created by Bot"
        }
        
        return await self._request("POST", "user", json=payload)

    async def get_user(self, identifier: str) -> Optional[dict]:
        return await self._request("GET", f"user/{identifier}")

    async def get_all_users(self) -> List[dict]:
        resp = await self._request("GET", "users")
        # معمولاً {'users': [...]} برمی‌گرداند
        if isinstance(resp, dict):
            return resp.get("users", [])
        return resp if isinstance(resp, list) else []

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        if add_gb or add_days:
            user = await self.get_user(identifier)
            if not user: return False
        
        payload = {}
        
        if new_limit_gb is not None:
            payload['data_limit'] = int(new_limit_gb * (1024**3))
        elif add_gb != 0:
            current = user.get('data_limit', 0) or 0
            payload['data_limit'] = int(current + (add_gb * (1024**3)))
            
        if new_expire_ts is not None:
            payload['expire'] = new_expire_ts
        elif add_days != 0:
            current_expire = user.get('expire', 0)
            now_ts = int(time.time())
            base_time = max(current_expire, now_ts) if current_expire else now_ts
            payload['expire'] = base_time + (add_days * 86400)

        if not payload: return True

        res = await self._request("PUT", f"user/{identifier}", json=payload)
        return res is not None

    async def delete_user(self, identifier: str) -> bool:
        res = await self._request("DELETE", f"user/{identifier}")
        return res is True

    async def reset_user_usage(self, identifier: str) -> bool:
        res = await self._request("POST", f"user/{identifier}/reset")
        return res is not None
        
    async def get_system_stats(self) -> dict:
        return await self._request("GET", "system") or {}

    async def check_connection(self) -> bool:
        stats = await self.get_system_stats()
        return bool(stats)