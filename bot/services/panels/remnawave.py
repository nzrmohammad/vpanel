# bot/services/panels/remnawave.py

import logging
import httpx
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
        expire_val = new_data.get('expire_at') or new_data.get('expireAt')
        if expire_val:
            if isinstance(expire_val, datetime):
                new_data['expire'] = int(expire_val.timestamp())
            else:
                try: 
                    # هندل کردن فرمت متنی ISO مثل 2025-12-20T12:07:53.473Z
                    if isinstance(expire_val, str) and "T" in expire_val:
                        dt = datetime.strptime(expire_val.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                        new_data['expire'] = int(dt.timestamp())
                    else:
                        new_data['expire'] = int(expire_val)
                except: new_data['expire'] = None
        
        # 2. تبدیل حجم کل (trafficLimitBytes)
        limit_bytes = new_data.get('trafficLimitBytes') or new_data.get('traffic_limit_bytes')
        if limit_bytes:
            new_data['usage_limit_GB'] = float(limit_bytes) / (1024**3)
            new_data['data_limit'] = limit_bytes
        else:
            new_data['usage_limit_GB'] = 0
            
        # 3. تبدیل حجم مصرفی (userTraffic -> usedTrafficBytes)
        used_bytes = 0
        
        # بررسی userTraffic (فرمت جدید شما)
        if 'userTraffic' in new_data and isinstance(new_data['userTraffic'], dict):
            used_bytes = new_data['userTraffic'].get('usedTrafficBytes', 0)
        # بررسی user_traffic (فرمت احتمالی دیگر)
        elif 'user_traffic' in new_data and isinstance(new_data['user_traffic'], dict):
            used_bytes = new_data['user_traffic'].get('used_traffic_bytes', 0)
        # بررسی مستقیم در روت
        elif 'trafficUsed' in new_data:
             used_bytes = new_data['trafficUsed']
        
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

    async def get_active_squads(self) -> List[dict]:
        try:
            # 1. یافتن متد صحیح
            method_ctrl = getattr(self.client, "internal_squads", None)
            if not method_ctrl: return []
            
            get_method = getattr(method_ctrl, "get_all_internal_squads", None) or \
                         getattr(method_ctrl, "get_internal_squads", None) or \
                         getattr(method_ctrl, "get_all", None)
            
            if not get_method: return []

            # 2. دریافت پاسخ
            response = await get_method()
            
            raw_items = []

            # 3. استخراج لیست بر اساس ساختار لاگ شما
            # لاگ نشان داد که response دارای فیلد internal_squads است
            if hasattr(response, 'internal_squads'):
                raw_items = response.internal_squads
            elif isinstance(response, dict) and 'internal_squads' in response:
                raw_items = response['internal_squads']
            # سایر حالت‌های احتمالی
            elif hasattr(response, 'items'):
                raw_items = response.items
            elif isinstance(response, list):
                raw_items = response
            elif hasattr(response, 'data'):
                raw_items = response.data

            squads_list = []
            
            # 4. پردازش آیتم‌ها
            for s in raw_items:
                # تلاش برای استخراج مستقیم ویژگی‌ها (چون DTO هستند)
                uuid_val = getattr(s, 'uuid', None)
                name_val = getattr(s, 'name', None)

                # اگر مستقیم نشد، تلاش برای تبدیل به دیکشنری
                if uuid_val is None:
                    try:
                        s_dict = {}
                        if hasattr(s, 'model_dump'): s_dict = s.model_dump()
                        elif hasattr(s, 'dict'): s_dict = s.dict()
                        elif isinstance(s, dict): s_dict = s
                        
                        uuid_val = s_dict.get('uuid') or s_dict.get('id')
                        name_val = s_dict.get('name') or s_dict.get('title')
                    except: pass

                if uuid_val:
                    squads_list.append({
                        'uuid': str(uuid_val),
                        'name': str(name_val or 'Unknown Squad')
                    })

            return squads_list

        except Exception as e:
            logger.error(f"Error getting squads: {e}")
            return []

    async def get_active_external_squads(self) -> List[dict]:
        """دریافت لیست External Squads"""
        try:
            # حدس زدن نام کنترلر (معمولاً external_squads است)
            method_ctrl = getattr(self.client, "external_squads", None)
            if not method_ctrl: return []
            
            get_method = getattr(method_ctrl, "get_all_external_squads", None) or \
                         getattr(method_ctrl, "get_external_squads", None) or \
                         getattr(method_ctrl, "get_all", None)
            
            if not get_method: return []

            response = await get_method()
            raw_items = []

            # استخراج دیتا از پاسخ (مشابه متد اینترنال)
            if hasattr(response, 'external_squads'):
                raw_items = response.external_squads
            elif isinstance(response, dict) and 'external_squads' in response:
                raw_items = response['external_squads']
            elif hasattr(response, 'items'):
                raw_items = response.items
            elif hasattr(response, 'data'):
                raw_items = response.data

            squads_list = []
            for s in raw_items:
                uuid_val = getattr(s, 'uuid', None)
                name_val = getattr(s, 'name', None)
                
                # تلاش برای استخراج اگر آبجکت باشد
                if uuid_val is None and hasattr(s, 'model_dump'):
                    d = s.model_dump()
                    uuid_val = d.get('uuid')
                    name_val = d.get('name')

                if uuid_val:
                    squads_list.append({
                        'uuid': str(uuid_val),
                        'name': str(name_val or 'External Squad')
                    })
            return squads_list

        except Exception as e:
            logger.error(f"Error getting external squads: {e}")
            return []

    # 2. متد add_user را با این نسخه جایگزین کنید (اضافه شدن external_squad_uuid)
    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None, external_squad_uuid: str = None) -> Optional[dict]:
        try:
            traffic_limit = 0
            if limit_gb and float(limit_gb) > 0:
                traffic_limit = int(float(limit_gb) * 1024 * 1024 * 1024)
            
            expire_at = None
            if expire_days and int(expire_days) > 0:
                expire_date = datetime.utcnow() + timedelta(days=int(expire_days))
                expire_at = expire_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            
            # ساخت payload طبق نمونه JSON صحیح
            payload = {
                "username": name,
                "status": "ACTIVE",
                "trafficLimitBytes": traffic_limit,
                "trafficLimitStrategy": "NO_RESET",
                "expireAt": expire_at,
                "telegramId": int(telegram_id) if telegram_id and str(telegram_id).isdigit() else None,
                "activeInternalSquads": [],
                "externalSquadUuid": None # فیلد جدید
            }

            if uuid:
                payload["uuid"] = str(uuid)

            # افزودن Internal Squad
            if squad_uuid:
                payload["activeInternalSquads"] = [str(squad_uuid)]
            
            # افزودن External Squad (جدید)
            if external_squad_uuid:
                payload["externalSquadUuid"] = str(external_squad_uuid)
            
            # ارسال درخواست مستقیم
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    url = f"{self.api_url}/api/users"
                    headers = {
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    
                    logger.info(f"Creating user {name} via direct API")
                    response = await client.post(url, json=payload, headers=headers)
                    
                    if response.status_code in [200, 201]:
                        user_data = response.json()
                        if "response" in user_data:
                            user_data = user_data["response"]
                        return self._normalize(user_data)
                    else:
                        logger.error(f"Failed to create user: {response.status_code} | {response.text}")
                        return None

            except Exception as req_err:
                logger.error(f"Direct request failed: {req_err}")
                return None
            
        except Exception as e:
            logger.error(f"Remnawave add_user error: {e}")
            return None
        
    # سایر متدها...
    async def get_user(self, identifier: str) -> Optional[dict]:
        # روش اول: تلاش با استفاده از SDK
        try:
            user = await self.client.users.get_user(identifier)
            return self._normalize(user.model_dump())
        except Exception:
            # روش دوم: اگر SDK کار نکرد، درخواست مستقیم (Fallback)
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    url = f"{self.api_url}/api/users/{identifier}"
                    headers = {
                        "Authorization": f"Bearer {self.api_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                    resp = await client.get(url, headers=headers, timeout=10)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        # هندل کردن ساختار response wrapper
                        if "response" in data:
                            data = data["response"]
                        return self._normalize(data)
                    else:
                        logger.error(f"Direct get_user failed: {resp.status_code} | {resp.text}")
            except Exception as e:
                logger.error(f"Direct get_user exception: {e}")
            
            return None

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