# bot/db/support.py

import logging
from typing import Any, Dict, Optional
from sqlalchemy import select, update, and_

# وارد کردن مدل‌ها از فایل base
from .base import SupportTicket

logger = logging.getLogger(__name__)

class SupportDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به تیکت‌های پشتیبانی.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    async def create_support_ticket(self, user_id: int, initial_admin_message_id: int) -> int:
        """
        یک تیکت پشتیبانی جدید ایجاد می‌کند و شناسه آن را برمی‌گرداند.
        """
        async with self.get_session() as session:
            ticket = SupportTicket(
                user_id=user_id,
                initial_admin_message_id=initial_admin_message_id,
                status='open'
            )
            session.add(ticket)
            await session.commit()
            # رفرش برای دریافت ID تولید شده
            await session.refresh(ticket)
            return ticket.id

    async def get_ticket_by_admin_message_id(self, admin_message_id: int) -> Optional[Dict[str, Any]]:
        """
        یک تیکت باز را بر اساس شناسه پیامی که برای ادمین ارسال شده، پیدا می‌کند.
        """
        async with self.get_session() as session:
            stmt = select(SupportTicket).where(
                and_(
                    SupportTicket.initial_admin_message_id == admin_message_id,
                    SupportTicket.status == 'open'
                )
            )
            result = await session.execute(stmt)
            ticket = result.scalar_one_or_none()
            
            if ticket:
                return {
                    "id": ticket.id,
                    "user_id": ticket.user_id,
                    "status": ticket.status,
                    "initial_admin_message_id": ticket.initial_admin_message_id,
                    "created_at": ticket.created_at
                }
            return None

    async def close_ticket(self, ticket_id: int) -> bool:
        """
        وضعیت یک تیکت را به 'closed' تغییر می‌دهد.
        """
        async with self.get_session() as session:
            stmt = (
                update(SupportTicket)
                .where(SupportTicket.id == ticket_id)
                .values(status='closed')
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0