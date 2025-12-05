# bot/db/notifications.py

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import pytz

from sqlalchemy import select, update, delete, and_, desc, func
from .base import (
    WarningLog, UserUUID, SentReport, User, Notification, ScheduledMessage
)

logger = logging.getLogger(__name__)

class NotificationsDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به اعلان‌ها، هشدارها و لاگ‌ها.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    # --- توابع مربوط به هشدارها (Warnings) ---

    async def log_warning(self, uuid_id: int, warning_type: str) -> None:
        """
        یک هشدار ارسال شده برای کاربر را ثبت یا به‌روزرسانی می‌کند.
        """
        async with self.get_session() as session:
            # ابتدا بررسی می‌کنیم آیا رکوردی وجود دارد یا خیر
            stmt = select(WarningLog).where(
                and_(WarningLog.uuid_id == uuid_id, WarningLog.warning_type == warning_type)
            )
            result = await session.execute(stmt)
            existing_log = result.scalar_one_or_none()

            if existing_log:
                # اگر وجود داشت، زمان آن را به‌روز می‌کنیم
                existing_log.sent_at = datetime.now(timezone.utc)
            else:
                # اگر وجود نداشت، رکورد جدید می‌سازیم
                new_log = WarningLog(uuid_id=uuid_id, warning_type=warning_type)
                session.add(new_log)
            
            await session.commit()

    async def has_recent_warning(self, uuid_id: int, warning_type: str, hours: int = 24) -> bool:
        """
        بررسی می‌کند که آیا در چند ساعت گذشته هشدار مشخصی برای کاربر ارسال شده است یا خیر.
        """
        # محاسبه زمان به صورت Naive UTC (چون دیتابیس بدون تایم‌زون است)
        time_ago = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        async with self.get_session() as session:
            stmt = select(WarningLog).where(
                and_(
                    WarningLog.uuid_id == uuid_id,
                    WarningLog.warning_type == warning_type,
                    WarningLog.sent_at >= time_ago
                )
            )
            result = await session.execute(stmt)
            return result.first() is not None

    async def get_sent_warnings_since_midnight(self) -> List[Dict[str, Any]]:
        """
        گزارشی از تمام هشدارهایی که از نیمه‌شب امروز (به وقت تهران) ارسال شده‌اند.
        """
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        today_midnight = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
        # تبدیل به UTC بدون اطلاعات تایم زون برای مقایسه با دیتابیس
        today_midnight_naive = today_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        async with self.get_session() as session:
            stmt = (
                select(UserUUID.name, UserUUID.uuid, WarningLog.warning_type)
                .join(UserUUID, WarningLog.uuid_id == UserUUID.id)
                .where(WarningLog.sent_at >= today_midnight_naive)
                .order_by(UserUUID.name)
            )
            result = await session.execute(stmt)
            return [
                {"name": r.name, "uuid": r.uuid, "warning_type": r.warning_type}
                for r in result.all()
            ]

    # --- توابع مربوط به گزارش‌های ارسال شده (Sent Reports) ---

    async def add_sent_report(self, user_id: int, message_id: int) -> None:
        """یک رکورد برای پیام گزارش ارسال شده ثبت می‌کند."""
        async with self.get_session() as session:
            report = SentReport(user_id=user_id, message_id=message_id)
            session.add(report)
            await session.commit()

    async def get_sent_reports(self, user_id: int) -> List[Dict[str, Any]]:
        """لیست تمام گزارش‌های ارسال شده قبلی برای یک کاربر."""
        async with self.get_session() as session:
            stmt = select(SentReport).where(SentReport.user_id == user_id)
            result = await session.execute(stmt)
            return [
                {"id": r.id, "message_id": r.message_id} 
                for r in result.scalars().all()
            ]

    async def get_old_reports_to_delete(self, hours: int = 12) -> List[Dict[str, Any]]:
        """پیام‌های گزارشی قدیمی که باید حذف شوند."""
        time_limit = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        async with self.get_session() as session:
            stmt = (
                select(SentReport.id, SentReport.user_id, SentReport.message_id)
                .join(User, SentReport.user_id == User.user_id)
                .where(
                    and_(
                        SentReport.sent_at < time_limit,
                        User.auto_delete_reports == True
                    )
                )
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def delete_sent_report_record(self, record_id: int) -> None:
        """یک رکورد را از جدول sent_reports حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(SentReport).where(SentReport.id == record_id)
            await session.execute(stmt)
            await session.commit()

    # --- توابع مربوط به اعلان‌های عمومی (Notifications) ---

    async def create_notification(self, user_id: int, title: str, message: str, category: str = 'info') -> None:
        """یک اعلان جدید ثبت می‌کند."""
        async with self.get_session() as session:
            notif = Notification(
                user_id=user_id, title=title, message=message, category=category
            )
            session.add(notif)
            await session.commit()
            logger.info(f"Created notification for user {user_id}, category: {category}")

    async def get_notifications_for_user(self, user_id: int, include_read: bool = False) -> List[Dict[str, Any]]:
        """لیست اعلان‌های یک کاربر را برمی‌گرداند."""
        async with self.get_session() as session:
            query = select(Notification).where(Notification.user_id == user_id)
            
            if not include_read:
                query = query.where(Notification.is_read == False)
            
            query = query.order_by(desc(Notification.created_at))
            
            result = await session.execute(query)
            notifications = result.scalars().all()
            
            # تبدیل به دیکشنری
            return [
                {
                    "id": n.id, "title": n.title, "message": n.message,
                    "category": n.category, "is_read": n.is_read,
                    "created_at": n.created_at
                }
                for n in notifications
            ]

    async def mark_notification_as_read(self, notification_id: int, user_id: int) -> bool:
        """یک اعلان خاص را خوانده شده می‌کند."""
        async with self.get_session() as session:
            stmt = (
                update(Notification)
                .where(and_(Notification.id == notification_id, Notification.user_id == user_id))
                .values(is_read=True)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def mark_all_notifications_as_read(self, user_id: int) -> int:
        """تمام اعلان‌های کاربر را خوانده شده می‌کند."""
        async with self.get_session() as session:
            stmt = (
                update(Notification)
                .where(and_(Notification.user_id == user_id, Notification.is_read == False))
                .values(is_read=True)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    # --- توابع مربوط به پیام‌های زمان‌بندی شده ---

    async def add_or_update_scheduled_message(self, job_type: str, chat_id: int, message_id: int):
        """یک پیام زمان‌بندی شده را ثبت یا آپدیت می‌کند."""
        async with self.get_session() as session:
            # جستجو برای رکورد تکراری
            stmt = select(ScheduledMessage).where(
                and_(ScheduledMessage.job_type == job_type, ScheduledMessage.chat_id == chat_id)
            )
            result = await session.execute(stmt)
            existing_msg = result.scalar_one_or_none()

            if existing_msg:
                existing_msg.message_id = message_id
                existing_msg.created_at = datetime.now(timezone.utc)
            else:
                new_msg = ScheduledMessage(
                    job_type=job_type, chat_id=chat_id, message_id=message_id
                )
                session.add(new_msg)
            
            await session.commit()

    async def get_scheduled_messages(self, job_type: str) -> List[Dict[str, Any]]:
        """دریافت پیام‌های زمان‌بندی شده بر اساس نوع."""
        async with self.get_session() as session:
            stmt = select(ScheduledMessage).where(ScheduledMessage.job_type == job_type)
            result = await session.execute(stmt)
            return [
                {"id": r.id, "chat_id": r.chat_id, "message_id": r.message_id}
                for r in result.scalars().all()
            ]

    async def delete_scheduled_message(self, job_id: int):
        """حذف یک پیام زمان‌بندی شده."""
        async with self.get_session() as session:
            stmt = delete(ScheduledMessage).where(ScheduledMessage.id == job_id)
            await session.execute(stmt)
            await session.commit()