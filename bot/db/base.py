# bot/db/base.py

import logging
import os
import uuid as uuid_lib
from typing import Optional, List, AsyncGenerator
from datetime import datetime, date

from sqlalchemy import (
    BigInteger, String, Boolean, Float, Date, DateTime, 
    ForeignKey, Integer, Text, func, JSON, select, delete, Index, inspect
)
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker, AsyncAttrs
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy.dialects.postgresql import JSONB, UUID
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class Base(AsyncAttrs, DeclarativeBase):
    pass

# ---------------------------------------------------------
# 1. جداول اصلی کاربر و سرویس
# ---------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(128))
    first_name: Mapped[Optional[str]] = mapped_column(String(128))
    last_name: Mapped[Optional[str]] = mapped_column(String(128))
    birthday: Mapped[Optional[date]] = mapped_column(Date)
    settings: Mapped[dict] = mapped_column(JSONB, default={})
    admin_note: Mapped[Optional[str]] = mapped_column(Text)
    lang_code: Mapped[Optional[str]] = mapped_column(String(10), default='fa')
    last_checkin: Mapped[Optional[date]] = mapped_column(Date)
    streak_count: Mapped[int] = mapped_column(Integer, default=0)
    referral_code: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    referred_by_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    referral_reward_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    achievement_points: Mapped[int] = mapped_column(Integer, default=0)
    wallet_balance: Mapped[float] = mapped_column(Float, default=0.0)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("plans.id", ondelete="SET NULL"))
    uuids: Mapped[List["UserUUID"]] = relationship("UserUUID", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    transactions: Mapped[List["WalletTransaction"]] = relationship("WalletTransaction", back_populates="user")


class UserUUID(Base):
    __tablename__ = "user_uuids"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    uuid: Mapped[uuid_lib.UUID] = mapped_column(UUID(as_uuid=True), default=uuid_lib.uuid4)
    name: Mapped[Optional[str]] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    first_connection_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    welcome_message_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_panels: Mapped[List["Panel"]] = relationship(
        "Panel", secondary="uuid_panel_access", back_populates="allowed_uuids", lazy="selectin"
    )
    user: Mapped["User"] = relationship("User", back_populates="uuids", lazy="selectin")
    snapshots: Mapped[List["UsageSnapshot"]] = relationship("UsageSnapshot", back_populates="uuid_rel", cascade="all, delete-orphan")
    __table_args__ = (
        Index('idx_uuid_active', 'uuid', 'is_active'),
    )

class Panel(Base):
    __tablename__ = "panels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    panel_type: Mapped[str] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("server_categories.code", ondelete="SET NULL"))
    api_url: Mapped[str] = mapped_column(String(255))
    api_token1: Mapped[Optional[str]] = mapped_column(String(255))
    api_token2: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    allowed_uuids: Mapped[List["UserUUID"]] = relationship("UserUUID", secondary="uuid_panel_access", back_populates="allowed_panels")


class UUIDPanelAccess(Base):
    __tablename__ = "uuid_panel_access"
    uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"), primary_key=True)
    panel_id: Mapped[int] = mapped_column(Integer, ForeignKey("panels.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------
# 2. جداول مدیریت سیستم (داینامیک)
# ---------------------------------------------------------

class ServerCategory(Base):
    """دسته‌بندی‌های سرور (آلمان، فرانسه، ...)"""
    __tablename__ = "server_categories"
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    emoji: Mapped[str] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Plan(Base):
    """پلن‌های فروش"""
    __tablename__ = "plans"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float)
    volume_gb: Mapped[float] = mapped_column(Float)
    days: Mapped[int] = mapped_column(Integer)
    allowed_categories: Mapped[List[str]] = mapped_column(JSONB, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Addon(Base):
    """افزودنی‌های حجم و زمان"""
    __tablename__ = "addons"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Float)
    extra_gb: Mapped[float] = mapped_column(Float, default=0.0)
    extra_days: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Badge(Base):
    """🔥 جدید: مدیریت نشان‌ها و دستاوردها"""
    __tablename__ = "badges"
    
    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(20)) # 🎖️
    description: Mapped[Optional[str]] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=0)
    condition_type: Mapped[Optional[str]] = mapped_column(String(50))
    condition_value: Mapped[Optional[float]] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PaymentMethod(Base):
    """🔥 جدید: روش‌های پرداخت (کارت به کارت، کریپتو)"""
    __tablename__ = "payment_methods"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Tutorial(Base):
    """🔥 جدید: مدیریت آموزش‌ها"""
    __tablename__ = "tutorials"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    os_type: Mapped[str] = mapped_column(String(50))
    app_name: Mapped[str] = mapped_column(String(100))
    link: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ConfigTemplate(Base):
    __tablename__ = "config_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_str: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_special: Mapped[bool] = mapped_column(Boolean, default=False)
    is_random_pool: Mapped[bool] = mapped_column(Boolean, default=False)
    server_category_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("server_categories.code", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---------------------------------------------------------
# 3. جداول عملیاتی (لاگ‌ها و تراکنش‌ها)
# ---------------------------------------------------------

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"))
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    __table_args__ = (
        Index('idx_wallet_user_type', 'user_id', 'type'),
    )    

class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"))
    hiddify_usage_gb: Mapped[float] = mapped_column(Float, default=0.0)
    marzban_usage_gb: Mapped[float] = mapped_column(Float, default=0.0)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uuid_rel: Mapped["UserUUID"] = relationship("UserUUID", back_populates="snapshots")
    __table_args__ = (
            Index('idx_usage_uuid_time', 'uuid_id', 'taken_at'),
        )

class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(50))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class WarningLog(Base):
    __tablename__ = "warning_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid_id: Mapped[int] = mapped_column(Integer)
    warning_type: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Payment(Base):
    __tablename__ = "payments"
    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="SET NULL"))
    payment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
            Index('idx_payment_date', 'payment_date'),
        )    

class UserGeneratedConfig(Base):
    __tablename__ = "user_generated_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"))
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("config_templates.id", ondelete="CASCADE"))
    generated_uuid: Mapped[str] = mapped_column(String(64), unique=True)

class MarzbanMapping(Base):
    __tablename__ = "marzban_mapping"
    hiddify_uuid: Mapped[uuid_lib.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    marzban_username: Mapped[str] = mapped_column(String(64), unique=True)

class LoginToken(Base):
    __tablename__ = "login_tokens"
    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    uuid: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SentReport(Base):
    __tablename__ = "sent_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ClientUserAgent(Base):
    __tablename__ = "client_user_agents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"))
    user_agent: Mapped[str] = mapped_column(String(255))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class TrafficTransfer(Base):
    __tablename__ = "traffic_transfers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"))
    receiver_uuid_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_uuids.id", ondelete="CASCADE"))
    panel_type: Mapped[str] = mapped_column(String(20))
    amount_gb: Mapped[float] = mapped_column(Float)
    transferred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserAchievement(Base):
    __tablename__ = "user_achievements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    badge_code: Mapped[str] = mapped_column(String(50))
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AchievementShopLog(Base):
    __tablename__ = "achievement_shop_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    item_key: Mapped[str] = mapped_column(String(50))
    cost: Mapped[int] = mapped_column(Integer)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BirthdayGiftLog(Base):
    __tablename__ = "birthday_gift_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    gift_year: Mapped[int] = mapped_column(Integer)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AnniversaryGiftLog(Base):
    __tablename__ = "anniversary_gift_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    gift_year: Mapped[int] = mapped_column(Integer)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ChargeRequest(Base):
    __tablename__ = "charge_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float)
    message_id: Mapped[int] = mapped_column(Integer)
    request_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_pending: Mapped[bool] = mapped_column(Boolean, default=True)

class WalletTransfer(Base):
    __tablename__ = "wallet_transfers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_user_id: Mapped[int] = mapped_column(BigInteger)
    receiver_user_id: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[float] = mapped_column(Float)
    transferred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AutoRenewalLog(Base):
    __tablename__ = "auto_renewal_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    uuid_id: Mapped[int] = mapped_column(Integer)
    plan_price: Mapped[float] = mapped_column(Float)
    renewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class LotteryTicket(Base):
    __tablename__ = "lottery_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default='info')
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index('idx_notif_user_unread', 'user_id', 'is_read'),
    )

class WeeklyChampionLog(Base):
    __tablename__ = "weekly_champion_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    win_date: Mapped[date] = mapped_column(Date)

class AchievementRequest(Base):
    __tablename__ = "achievement_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    badge_code: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

class MonthlyCost(Base):
    __tablename__ = "monthly_costs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    cost: Mapped[float] = mapped_column(Float)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserFeedback(Base):
    __tablename__ = "user_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default='open')
    initial_admin_message_id: Mapped[Optional[int]] = mapped_column(Integer)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AdminLog(Base):
    __tablename__ = "admin_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    target_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BroadcastTask(Base):
    __tablename__ = "broadcast_tasks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    target_type: Mapped[str] = mapped_column(String(50))
    message_id: Mapped[int] = mapped_column(Integer)
    from_chat_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    total_users: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

# ---------------------------------------------------------
# 4. مدیریت دیتابیس
# ---------------------------------------------------------

class DatabaseManager:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is not set!")
        
        if self.db_url.startswith("postgresql://"):
            self.db_url = self.db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        self.engine = create_async_engine(
            self.db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=10
        )

        self.session_maker = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        self._user_cache = {}

    @property
    def session(self) -> AsyncGenerator[AsyncSession, None]:
        return self.get_session()
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}", exc_info=True)
                raise

    async def init_db(self):
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
            async with self.get_session() as session:
                pass
            logger.info("✅ Database tables created successfully (Dynamic Schema).")
        except Exception as e:
            logger.error(f"❌ Error initializing database: {e}")
            raise

    async def check_connection(self) -> bool:
        try:
            async with self.session_maker() as session:
                await session.execute(expression.text("SELECT 1"))
            return True
        except Exception:
            return False

    async def close(self):
        await self.engine.dispose()

    async def get_by_id(self, model, item_id: int, session: AsyncSession = None):
        """
        دریافت رکورد با ID.
        اگر سشن پاس داده شود از آن استفاده می‌کند (برای جلوگیری از بسته شدن سشن و مشکل ریلیشن‌ها).
        """
        if session:
            return await session.get(model, item_id)
        
        # اگر سشن نبود، یکی موقت می‌سازد
        async with self.get_session() as temp_session:
            return await temp_session.get(model, item_id)

    async def delete_by_id(self, model, item_id: int, session: AsyncSession = None) -> bool:
        """
        حذف رکورد با ID (شناسایی خودکار نام ستون کلید اصلی).
        """
        pk_column = inspect(model).primary_key[0]
        stmt = delete(model).where(pk_column == item_id)
        
        if session:
            result = await session.execute(stmt)
            return result.rowcount > 0

        async with self.get_session() as temp_session:
            result = await temp_session.execute(stmt)
            return result.rowcount > 0

    async def get_all(self, model, active_only: bool = False, session: AsyncSession = None) -> list:
        """
        دریافت تمام رکوردهای یک جدول.
        امکان پاس دادن سشن برای جلوگیری از خطای Lazy Loading.
        """
        stmt = select(model)
        if active_only and hasattr(model, 'is_active'):
            stmt = stmt.where(model.is_active == True)
        
        if hasattr(model, 'id'):
            stmt = stmt.order_by(model.id.desc())

        # سناریوی ۱: سشن پاس داده شده (امن برای ریلیشن‌ها)
        if session:
            result = await session.execute(stmt)
            return result.scalars().all()

        # سناریوی ۲: سشن موقت (خطرناک برای ریلیشن‌های Lazy اگر بعداً دسترسی بخواهید)
        async with self.get_session() as temp_session:
            result = await temp_session.execute(stmt)
            return result.scalars().all()

    def clear_user_cache(self, user_id: int):
        if user_id in self._user_cache:
            del self._user_cache[user_id]