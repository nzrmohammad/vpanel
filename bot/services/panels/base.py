# bot/services/panels/base.py
from abc import ABC, abstractmethod
from typing import Optional, List

class BasePanel(ABC):
    def __init__(self, api_url: str, api_token: str, extra_config: dict = None):
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token
        self.extra_config = extra_config or {}

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None, telegram_id: str = None, squad_uuid: str = None) -> Optional[dict]:
        pass

    @abstractmethod
    async def get_user(self, identifier: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        pass

    @abstractmethod
    async def delete_user(self, identifier: str) -> bool:
        pass

    async def get_all_users(self) -> List[dict]:
        return []

    async def get_system_stats(self) -> dict:
        return {}
    
    async def check_connection(self) -> bool:
        return False