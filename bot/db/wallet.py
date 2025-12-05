# bot/db/wallet.py

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, delete, insert, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

# وارد کردن مدل‌ها
from .base import (
    User, WalletTransaction, ChargeRequest, DatabaseManager
)

logger = logging.getLogger(__name__)

class WalletDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به کیف پول و تراکنش‌ها.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    async def update_wallet_balance(self, user_id: int, amount: float, trans_type: str, description: str, session: AsyncSession = None) -> bool:
        """
        آپدیت موجودی (با قابلیت شرکت در تراکنش خارجی).
        اگر session داده شود، کامیت نمی‌کند (وظیفه فراخواننده است).
        """
        # تابع داخلی برای انجام عملیات
        async def _do_update(sess):
            stmt = select(User).where(User.user_id == user_id).with_for_update()
            result = await sess.execute(stmt)
            user = result.scalar_one_or_none()

            if not user: return False

            current_balance = user.wallet_balance or 0.0
            if amount < 0 and trans_type in ['purchase', 'gift_purchase', 'addon_purchase', 'transfer_out']:
                if current_balance < abs(amount): return False

            user.wallet_balance = current_balance + amount
            
            tx = WalletTransaction(
                user_id=user_id, amount=amount, type=trans_type,
                description=description, transaction_date=datetime.now(timezone.utc)
            )
            sess.add(tx)
            return True

        if session:
            # استفاده از سشن موجود (بدون کامیت)
            return await _do_update(session)
        else:
            # ساخت سشن جدید (با کامیت)
            async with self.get_session() as new_sess:
                if await _do_update(new_sess):
                    await new_sess.commit()
                    return True
                return False

    async def set_wallet_balance(self, user_id: int, new_balance: float, trans_type: str, description: str) -> bool:
        """
        موجودی کیف پول کاربر را به یک مقدار مشخص تغییر داده و تراکنش اصلاحی را ثبت می‌کند.
        """
        async with self.get_session() as session:
            try:
                user = await session.get(User, user_id)
                if not user:
                    return False

                current_balance = user.wallet_balance or 0.0
                amount_changed = new_balance - current_balance

                # آپدیت موجودی
                user.wallet_balance = new_balance
                
                # ثبت تراکنش اصلاحی
                transaction = WalletTransaction(
                    user_id=user_id,
                    amount=amount_changed,
                    type=trans_type,
                    description=description,
                    transaction_date=datetime.now(timezone.utc)
                )
                session.add(transaction)
                
                await session.commit()
                
                if hasattr(self, 'clear_user_cache'):
                    self.clear_user_cache(user_id)
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Error setting wallet balance for user {user_id}: {e}", exc_info=True)
                return False

    async def get_wallet_history(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """تاریخچه تراکنش‌های کیف پول یک کاربر را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = (
                select(WalletTransaction)
                .where(WalletTransaction.user_id == user_id)
                .order_by(desc(WalletTransaction.transaction_date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                {
                    "id": r.id, "amount": r.amount, "type": r.type,
                    "description": r.description, "transaction_date": r.transaction_date
                } 
                for r in result.scalars().all()
            ]

    async def create_charge_request(self, user_id: int, amount: float, message_id: int) -> int:
        """یک درخواست شارژ جدید ثبت کرده و شناسه آن را برمی‌گرداند."""
        async with self.get_session() as session:
            request = ChargeRequest(
                user_id=user_id,
                amount=amount,
                message_id=message_id,
                request_date=datetime.now(timezone.utc),
                is_pending=True
            )
            session.add(request)
            await session.commit()
            # رفرش برای دریافت ID
            await session.refresh(request)
            return request.id

    async def get_pending_charge_request(self, user_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """یک درخواست شارژ در حال انتظار را پیدا می‌کند."""
        async with self.get_session() as session:
            stmt = select(ChargeRequest).where(
                and_(
                    ChargeRequest.user_id == user_id,
                    ChargeRequest.message_id == message_id,
                    ChargeRequest.is_pending == True
                )
            ).order_by(desc(ChargeRequest.request_date)).limit(1)
            
            result = await session.execute(stmt)
            req = result.scalar_one_or_none()
            if req:
                return {
                    "id": req.id, "user_id": req.user_id, "amount": req.amount,
                    "message_id": req.message_id, "is_pending": req.is_pending
                }
            return None

    async def get_charge_request_by_id(self, request_id: int) -> Optional[Dict[str, Any]]:
        """یک درخواست شارژ را با شناسه یکتای آن بازیابی می‌کند."""
        async with self.get_session() as session:
            req = await session.get(ChargeRequest, request_id)
            if req:
                return {
                    "id": req.id, "user_id": req.user_id, "amount": req.amount,
                    "message_id": req.message_id, "is_pending": req.is_pending
                }
            return None

    async def update_charge_request_status(self, request_id: int, is_pending: bool):
        """وضعیت یک درخواست شارژ را به‌روزرسانی می‌کند."""
        async with self.get_session() as session:
            stmt = (
                update(ChargeRequest)
                .where(ChargeRequest.id == request_id)
                .values(is_pending=is_pending)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_all_users_with_balance(self) -> List[Dict[str, Any]]:
        """تمام کاربرانی که موجودی کیف پول دارند را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name, User.wallet_balance)
                .where(User.wallet_balance > 0)
                .order_by(desc(User.wallet_balance))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def reset_all_wallet_balances(self) -> int:
        """موجودی کیف پول تمام کاربران را صفر کرده و تمام تاریخچه تراکنش‌ها را پاک می‌کند."""
        async with self.get_session() as session:
            # حذف تاریخچه
            await session.execute(delete(WalletTransaction))
            await session.execute(delete(ChargeRequest))
            
            # صفر کردن موجودی‌ها
            stmt = update(User).values(wallet_balance=0.0)
            result = await session.execute(stmt)
            
            await session.commit()
            
            if hasattr(self, '_user_cache'):
                self._user_cache.clear()
                
            return result.rowcount
            
    async def get_wallet_transactions_paginated(self, user_id: int, page: int = 1, per_page: int = 10) -> List[Dict[str, Any]]:
        """لیست تراکنش‌های کیف پول یک کاربر به صورت صفحه‌بندی شده."""
        offset = (page - 1) * per_page
        async with self.get_session() as session:
            stmt = (
                select(WalletTransaction)
                .where(WalletTransaction.user_id == user_id)
                .order_by(desc(WalletTransaction.transaction_date))
                .limit(per_page)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return [
                {
                    "amount": r.amount, "type": r.type, 
                    "description": r.description, "transaction_date": r.transaction_date
                }
                for r in result.scalars().all()
            ]

    async def get_wallet_transactions_count(self, user_id: int) -> int:
        """تعداد کل تراکنش‌های کیف پول یک کاربر."""
        async with self.get_session() as session:
            stmt = select(func.count(WalletTransaction.id)).where(WalletTransaction.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def get_user_total_expenses(self, user_id: int) -> float:
        """مجموع کل هزینه‌های یک کاربر (خرید و انتقال)."""
        expense_types = ['purchase', 'addon_purchase', 'gift_purchase', 'transfer_out']
        async with self.get_session() as session:
            stmt = (
                select(func.sum(WalletTransaction.amount))
                .where(
                    and_(
                        WalletTransaction.user_id == user_id,
                        WalletTransaction.type.in_(expense_types)
                    )
                )
            )
            result = await session.execute(stmt)
            total = result.scalar_one()
            # چون هزینه‌ها منفی ذخیره می‌شوند، قدر مطلق می‌گیریم
            return abs(total) if total is not None else 0.0

    async def get_user_purchase_stats(self, user_id: int) -> dict:
        """آمار خریدهای یک کاربر."""
        async with self.get_session() as session:
            # تعداد کل خریدها
            stmt_total = select(func.count(WalletTransaction.id)).where(
                and_(
                    WalletTransaction.user_id == user_id,
                    WalletTransaction.type.in_(['purchase', 'addon_purchase', 'gift_purchase'])
                )
            )
            
            # تعداد خریدهای هدیه
            stmt_gift = select(func.count(WalletTransaction.id)).where(
                and_(
                    WalletTransaction.user_id == user_id,
                    WalletTransaction.type == 'gift_purchase'
                )
            )
            
            # اجرای همزمان (یا پشت سر هم)
            res_total = await session.execute(stmt_total)
            res_gift = await session.execute(stmt_gift)
            
            return {
                'total_purchases': res_total.scalar_one(),
                'gift_purchases': res_gift.scalar_one()
            }