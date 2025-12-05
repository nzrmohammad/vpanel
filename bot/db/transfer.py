# bot/db/transfer.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, delete, desc, and_

# وارد کردن مدل‌ها از فایل base
from .base import TrafficTransfer

logger = logging.getLogger(__name__)

class TransferDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به انتقال ترافیک بین کاربران.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """
    async def log_traffic_transfer(self, sender_uuid_id: int, receiver_uuid_id: int, panel_type: str, amount_gb: float):
        """یک رکورد جدید برای انتقال ترافیک ثبت می‌کند."""
        async with self.get_session() as session:
            transfer = TrafficTransfer(
                sender_uuid_id=sender_uuid_id,
                receiver_uuid_id=receiver_uuid_id,
                panel_type=panel_type,
                amount_gb=amount_gb,
                transferred_at=datetime.now(timezone.utc)
            )
            session.add(transfer)
            await session.commit()

    async def has_transferred_in_last_30_days(self, sender_uuid_id: int) -> bool:
        """بررسی می‌کند آیا کاربر در ۳۰ روز گذشته انتقالی داشته است یا خیر."""
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        async with self.get_session() as session:
            stmt = select(TrafficTransfer).where(
                and_(
                    TrafficTransfer.sender_uuid_id == sender_uuid_id,
                    TrafficTransfer.transferred_at >= thirty_days_ago
                )
            ).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_last_transfer_timestamp(self, sender_uuid_id: int) -> Optional[datetime]:
        """آخرین زمان انتقال ترافیک توسط یک کاربر را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = (
                select(TrafficTransfer.transferred_at)
                .where(TrafficTransfer.sender_uuid_id == sender_uuid_id)
                .order_by(desc(TrafficTransfer.transferred_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete_transfer_history(self, sender_uuid_id: int) -> int:
        """تمام تاریخچه انتقال یک کاربر خاص را برای ریست کردن محدودیت حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(TrafficTransfer).where(TrafficTransfer.sender_uuid_id == sender_uuid_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount