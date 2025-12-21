# bot/db/settings.py

import logging
from sqlalchemy import select, delete, update
from .base import SystemConfig, PaymentMethod

logger = logging.getLogger(__name__)

class SettingsDB:
    """
    توابع مدیریت تنظیمات و روش‌های پرداخت.
    این کلاس به DatabaseManager اضافه خواهد شد.
    """

    # --- تنظیمات عمومی (مثل آیدی کانال‌ها) ---

    async def set_config(self, key: str, value: str):
        """ذخیره یا بروزرسانی یک تنظیم سیستم"""
        async with self.get_session() as session:
            config = await session.get(SystemConfig, key)
            if config:
                config.value = str(value)
            else:
                session.add(SystemConfig(key=key, value=str(value)))
            await session.commit()

    async def get_config(self, key: str, default=None):
        """دریافت مقدار یک تنظیم"""
        async with self.get_session() as session:
            config = await session.get(SystemConfig, key)
            return config.value if config else default

    # --- مدیریت روش‌های پرداخت ---

    async def add_payment_method(self, method_type: str, title: str, details: dict):
        """
        افزودن روش پرداخت جدید
        Example:
            method_type='card', 
            title='بانک ملت', 
            details={'card_number': '...', 'holder': '...'}
        """
        async with self.get_session() as session:
            method = PaymentMethod(
                method_type=method_type,
                title=title,
                details=details, # SQLAlchemy خودش تبدیل به JSONB می‌کند
                is_active=True
            )
            session.add(method)
            await session.commit()
            return method.id

    async def get_payment_methods(self, method_type: str = None, active_only: bool = True):
        """دریافت لیست روش‌های پرداخت به صورت دیکشنری"""
        async with self.get_session() as session:
            stmt = select(PaymentMethod)
            
            if method_type:
                stmt = stmt.where(PaymentMethod.method_type == method_type)
            
            if active_only:
                stmt = stmt.where(PaymentMethod.is_active == True)
            
            # مرتب‌سازی بر اساس جدیدترین
            stmt = stmt.order_by(PaymentMethod.id.desc())
            
            result = await session.execute(stmt)
            methods = result.scalars().all()
            
            # تبدیل آبجکت‌ها به دیکشنری ساده برای استفاده راحت‌تر در ربات
            output = []
            for m in methods:
                output.append({
                    'id': m.id,
                    'type': m.method_type,
                    'title': m.title,
                    'details': m.details, # خودکار دیکشنری است
                    'is_active': m.is_active
                })
            return output

    async def delete_payment_method(self, method_id: int):
        """حذف کامل یک روش پرداخت"""
        async with self.get_session() as session:
            await session.execute(delete(PaymentMethod).where(PaymentMethod.id == method_id))
            await session.commit()

    async def toggle_payment_method(self, method_id: int):
        """فعال/غیرفعال کردن یک روش پرداخت بدون حذف"""
        async with self.get_session() as session:
            method = await session.get(PaymentMethod, method_id)
            if method:
                method.is_active = not method.is_active
                await session.commit()
                return method.is_active
            return None