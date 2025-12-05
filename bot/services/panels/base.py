from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any

class BasePanel(ABC):
    """
    کلاس پایه برای پنل‌ها که متدهای مشترک را تعریف می‌کند.
    تمام پنل‌های جدید باید از این کلاس ارث‌بری کرده و متدهای آن را پیاده‌سازی کنند.
    """

    def __init__(self, api_url: str, api_token: str, extra_config: dict = None):
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token
        self.extra_config = extra_config or {}

    @abstractmethod
    async def add_user(self, name: str, limit_gb: int, expire_days: int, uuid: str = None) -> Optional[dict]:
        """
        ساخت کاربر جدید در پنل.
        
        Args:
            name: نام کاربر
            limit_gb: محدودیت حجم به گیگابایت
            expire_days: تعداد روز اعتبار
            uuid: شناسه یکتا (اختیاری)
            
        Returns:
            دیکشنری اطلاعات کاربر ساخته شده یا None در صورت خطا
        """
        pass

    @abstractmethod
    async def get_user(self, identifier: str) -> Optional[dict]:
        """
        دریافت اطلاعات یک کاربر خاص.
        
        Args:
            identifier: شناسه کاربر (UUID در هیدیفای، Username در مرزبان)
        """
        pass

    @abstractmethod
    async def modify_user(self, identifier: str, add_gb: float = 0, add_days: int = 0, new_limit_gb: float = None, new_expire_ts: int = None) -> bool:
        """
        ویرایش اطلاعات کاربر (افزودن حجم/زمان یا تنظیم مقدار جدید).
        
        Args:
            identifier: شناسه کاربر
            add_gb: مقدار حجمی که باید اضافه شود (می‌تواند منفی باشد)
            add_days: تعداد روزی که باید اضافه شود
            new_limit_gb: تنظیم لیمیت حجم جدید (جایگزین قبلی)
            new_expire_ts: تنظیم تاریخ انقضای جدید (Timestamp)
            
        Returns:
            True در صورت موفقیت، False در صورت خطا
        """
        pass

    @abstractmethod
    async def delete_user(self, identifier: str) -> bool:
        """
        حذف کاربر از پنل.
        
        Args:
            identifier: شناسه کاربر
        """
        pass

    # متدهای اختیاری (اگر همه پنل‌ها ندارند، می‌توانند اینجا pass باشند یا raise NotImplementedError ندهند)
    async def get_all_users(self) -> List[dict]:
        """دریافت لیست تمام کاربران"""
        return []

    async def get_system_stats(self) -> dict:
        """دریافت وضعیت منابع سرور"""
        return {}
    
    async def check_connection(self) -> bool:
        """بررسی اتصال به پنل"""
        return False