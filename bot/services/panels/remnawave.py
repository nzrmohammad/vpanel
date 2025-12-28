# bot/services/panels/remnawave.py
import logging
import aiohttp
from typing import Optional, List, Any
from datetime import datetime, timedelta
from .base import BasePanel

logger = logging.getLogger(__name__)

class RemnawavePanel(BasePanel):
    def __init__(self, api_url: str, api_token: str, extra_config: dict = None):
        # استانداردسازی URL
        if not api_url.startswith(("http://", "https://")):
            api_url = f"https://{api_url}"
        
        super().__init__(api_url, api_token, extra_config)
        
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # ✅ بهینه‌سازی: ایجاد سشن پایدار
        timeout = aiohttp.ClientTimeout(total=20)
        self.session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)

    async def close(self):
        """بستن سشن طبق استاندارد"""
        if not self.session.closed:
            await self.session.close()

    async def _request(self, method: str, endpoint: str, json: dict = None) -> Any:
        """متد مرکزی ارسال درخواست"""
        url = f"{self.api_url}/api/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.request(method, url, json=json) as resp:
                if resp.status == 401:
                    logger.error("Remnawave Unauthorized! Check API Token.")
                    return None
                
                if resp.status == 204:
                    return True

                try:
                    data = await resp.json()
                except:
                    # اگر موفق بود ولی بادی نداشت
                    if resp.status < 300: return True
                    return None

                if resp.status >= 400:
                    logger.error(f"Remnawave API Error [{resp.status}]: {data}")
                    return None
                
                # رمنیو معمولاً پاسخ را در کلید response می‌گذارد
                return data.get("response", data)

        except Exception as e:
            logger.error(f"Remnawave Request Error [{endpoint}]: {e}")
            return None

    def _normalize_user(self, data: dict) -> dict:
        """تبدیل فرمت دیتای رمنیو به فرمت استاندارد بات"""
        if not data: return {}
        
        # 1. مدیریت نام
        name = data.get("username") or data.get("name") or "Unknown"

        # 2. مدیریت حجم (بایت به گیگابایت)
        limit_bytes = data.get("trafficLimitBytes") or data.get("trafficLimit") or 0
        limit_gb = float(limit_bytes) / (1024**3)

        used_bytes = 0
        if "userTraffic" in data and isinstance(data["userTraffic"], dict):
            used_bytes = data["userTraffic"].get("usedTrafficBytes", 0)
        elif "trafficUsed" in data:
            used_bytes = data.get("trafficUsed", 0)
        
        used_gb = float(used_bytes) / (1024**3)

        # 3. مدیریت زمان (ISO/Millisecond -> Timestamp)
        expire_ts = None
        expire_raw = data.get("expireAt") or data.get("expiration")
        
        if expire_raw:
            try:
                if isinstance(expire_raw, (int, float)):
                    # تشخیص میلی‌ثانیه (اعداد خیلی بزرگ)
                    if expire_raw > 100_000_000_000:
                        expire_ts = int(expire_raw / 1000)
                    else:
                        expire_ts = int(expire_raw)
                elif isinstance(expire_raw, str):
                    # تبدیل فرمت ISO 8601 (2025-01-01T12:00:00Z)
                    dt = datetime.fromisoformat(expire_raw.replace('Z', '+00:00'))
                    expire_ts = int(dt.timestamp())
            except:
                pass

        return {
            "uuid": data.get("uuid"),
            "name": name,
            "usage_limit_GB": limit_gb,
            "current_usage_GB": used_gb,
            "expire": expire_ts,
            "status": str(data.get("status", "")).lower(),
            "panel_url": self.api_url
        }

    # --- متدهای اصلی ---

    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None, external_squad_uuid: str = None) -> Optional[dict]:
        # تبدیل گیگ به بایت
        traffic_limit = int(limit_gb * (1024**3)) if limit_gb else 0
        
        # تبدیل روز به فرمت ISO
        expire_at = None
        if expire_days and expire_days > 0:
            expire_date = datetime.utcnow() + timedelta(days=expire_days)
            # فرمت دقیق مورد نیاز رمنیو: YYYY-MM-DDTHH:MM:SS.mmmZ
            expire_at = expire_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        payload = {
            "username": name,
            "status": "ACTIVE",
            "trafficLimitBytes": traffic_limit,
            "trafficLimitStrategy": "NO_RESET",
            "expireAt": expire_at,
            "telegramId": int(telegram_id) if telegram_id and str(telegram_id).isdigit() else None,
            "activeInternalSquads": [str(squad_uuid)] if squad_uuid else [],
            "externalSquadUuid": str(external_squad_uuid) if external_squad_uuid else None
        }

        if uuid:
            payload["uuid"] = str(uuid)

        res = await self._request("POST", "users", json=payload)
        return self._normalize_user(res) if res else None

    async def get_user(self, identifier: str) -> Optional[dict]:
        res = await self._request("GET", f"users/{identifier}")
        return self._normalize_user(res) if res else None

    async def get_all_users(self) -> List[dict]:
        res = await self._request("GET", "users")
        # ممکن است داخل کلید users باشد یا لیست مستقیم
        raw_list = []
        if isinstance(res, dict):
            raw_list = res.get("users", [])
        elif isinstance(res, list):
            raw_list = res
            
        return [self._normalize_user(u) for u in raw_list]

    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        # برای آپدیت باید دیتا را آماده کنیم
        payload = {}
        
        # دریافت کاربر فعلی برای محاسبات افزایشی
        if add_gb or add_days:
            user = await self.get_user(identifier)
            if not user: return False

        # --- لاجیک حجم ---
        if new_limit_gb is not None:
            payload['trafficLimitBytes'] = int(new_limit_gb * (1024**3))
        elif add_gb:
            current_bytes = int(user.get('usage_limit_GB', 0) * (1024**3))
            payload['trafficLimitBytes'] = current_bytes + int(add_gb * (1024**3))

        # --- لاجیک زمان ---
        if new_expire_ts is not None:
            # تبدیل Timestamp به ISO
            dt = datetime.fromtimestamp(new_expire_ts)
            payload['expireAt'] = dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        elif add_days:
            current_ts = user.get('expire') or int(datetime.utcnow().timestamp())
            # اگر منقضی شده، از الان اضافه کن، اگر نه، به تهش بچسبان
            base_ts = max(current_ts, int(datetime.utcnow().timestamp()))
            new_ts = base_ts + (add_days * 86400)
            
            dt = datetime.fromtimestamp(new_ts)
            payload['expireAt'] = dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        if not payload: return True

        res = await self._request("PATCH", f"users/{identifier}", json=payload)
        return res is not None

    async def delete_user(self, identifier: str) -> bool:
        # رمنیو DELETE برنمی‌گرداند (204) که هندل کردیم
        res = await self._request("DELETE", f"users/{identifier}")
        return res is True

    # --- متدهای کمکی (مخصوص رمنیو) ---
    
    async def get_active_squads(self) -> List[dict]:
        """دریافت لیست Squads داخلی"""
        res = await self._request("GET", "internal_squads")
        squads = res.get("internal_squads", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
        
        return [{"uuid": s.get("uuid"), "name": s.get("name")} for s in squads]

    async def get_active_external_squads(self) -> List[dict]:
        """دریافت لیست External Squads"""
        res = await self._request("GET", "external_squads")
        squads = res.get("external_squads", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
        
        return [{"uuid": s.get("uuid"), "name": s.get("name")} for s in squads]