# bot/db/financials.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from sqlalchemy import select, delete, func, desc, and_, cast, String, Date
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

# وارد کردن مدل‌ها
from .base import (
    Payment, UserUUID, User, MonthlyCost, WalletTransaction, Plan
)

# تلاش برای ایمپورت ماژول‌های کمکی (برای دریافت حجم مصرفی لایو)
try:
    from ..combined_handler import get_combined_user_info
    from ..utils import parse_volume_string
except ImportError:
    # توابع ساختگی برای جلوگیری از خطا در زمان تست دیتابیس
    def get_combined_user_info(uuid): return {}
    def parse_volume_string(v): return 0

logger = logging.getLogger(__name__)

class FinancialsDB:
    """
    مدیریت امور مالی، پرداخت‌ها، هزینه‌ها و گزارش‌ها.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    # --- بخش پرداخت‌ها (Payments) ---

    async def add_payment_record(self, uuid_id: int) -> int:
        """یک رکورد پرداخت (تمدید) ثبت می‌کند."""
        async with self.get_session() as session:
            new_payment = Payment(uuid_id=uuid_id, payment_date=datetime.now(timezone.utc))
            session.add(new_payment)
            await session.commit()
            await session.refresh(new_payment)
            return new_payment.payment_id

    async def get_payment_counts(self) -> Dict[str, int]:
        """تعداد پرداخت‌ها به تفکیک نام کانفیگ."""
        async with self.get_session() as session:
            stmt = (
                select(UserUUID.name, func.count(Payment.payment_id))
                .outerjoin(Payment, UserUUID.id == Payment.uuid_id)
                .where(UserUUID.is_active == True)
                .group_by(UserUUID.name)
            )
            result = await session.execute(stmt)
            return {row[0]: row[1] for row in result.all() if row[0]}

    async def get_user_latest_plan_price(self, uuid_id: int) -> Optional[int]:
        """تخمین قیمت پلن کاربر با جستجوی مستقیم در دیتابیس."""
        
        # 1. دریافت UUID و حجم مصرفی
        # (فرض: تابع کمکی get_combined_user_info را دارید)
        try:
            from ..combined_handler import get_combined_user_info
        except ImportError:
            return None

        async with self.get_session() as session:
            uuid_record = await session.get(UserUUID, uuid_id)
            if not uuid_record: return None
            uuid_str = uuid_record.uuid

        user_info = get_combined_user_info(uuid_str)
        if not user_info: return None

        # حجم کل کاربر (لیمیت)
        current_limit_gb = float(user_info.get('usage_limit_GB', 0))

        async with self.get_session() as session:
            # 🔥 بهینه‌سازی: جستجو در SQL به جای پایتون
            # پیدا کردن اولین پلن فعالی که حجمش تقریبا برابر حجم کاربر است
            stmt = (
                select(Plan.price)
                .where(
                    and_(
                        Plan.is_active == True,
                        # تلورانس 0.1 گیگ برای خطاهای گرد کردن اعشار
                        Plan.volume_gb >= current_limit_gb - 0.1,
                        Plan.volume_gb <= current_limit_gb + 0.1
                    )
                )
                .limit(1)
            )
            
            result = await session.execute(stmt)
            price = result.scalar_one_or_none()
            
            return int(price) if price is not None else None

    async def get_revenue_by_month(self, months: int = 6) -> List[Dict[str, Any]]:
        """درآمد ماهانه (تعداد پرداخت‌ها) برای نمودار."""
        async with self.get_session() as session:
            # استفاده از to_char برای فرمت تاریخ در Postgres
            month_str = func.to_char(Payment.payment_date, 'YYYY-MM')
            
            stmt = (
                select(month_str.label("month"), func.count(Payment.payment_id).label("revenue_unit"))
                .group_by("month")
                .order_by(desc("month"))
                .limit(months)
            )
            result = await session.execute(stmt)
            return [{"month": row.month, "revenue_unit": row.revenue_unit} for row in result.all()]

    async def get_daily_payment_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """آمار پرداخت‌های روزانه."""
        date_limit = datetime.now(timezone.utc) - timedelta(days=days)
        async with self.get_session() as session:
            date_cast = cast(Payment.payment_date, Date)
            stmt = (
                select(date_cast.label("date"), func.count(Payment.payment_id).label("count"))
                .where(Payment.payment_date >= date_limit)
                .group_by(date_cast)
                .order_by(date_cast.asc())
            )
            result = await session.execute(stmt)
            return [{"date": row.date, "count": row.count} for row in result.all()]

    async def get_payment_history(self) -> List[Dict[str, Any]]:
        """لیست آخرین پرداخت هر کاربر."""
        async with self.get_session() as session:
            # Subquery برای پیدا کردن آخرین تاریخ پرداخت
            subq = (
                select(func.max(Payment.payment_date))
                .where(Payment.uuid_id == UserUUID.id)
                .scalar_subquery()
            )
            stmt = (
                select(UserUUID.name, Payment.payment_date)
                .join(UserUUID, Payment.uuid_id == UserUUID.id)
                .where(
                    and_(
                        Payment.payment_date == subq, 
                        UserUUID.is_active == True
                    )
                )
                .order_by(desc(Payment.payment_date))
            )
            result = await session.execute(stmt)
            return [{"name": row.name, "payment_date": row.payment_date} for row in result.all()]

    async def get_user_payment_history(self, uuid_id: int) -> List[Dict[str, Any]]:
        """تاریخچه پرداخت‌های یک کاربر خاص."""
        async with self.get_session() as session:
            stmt = (
                select(Payment.payment_date)
                .where(Payment.uuid_id == uuid_id)
                .order_by(desc(Payment.payment_date))
            )
            result = await session.execute(stmt)
            return [{"payment_date": row} for row in result.scalars().all()]

    async def get_all_payments_with_user_info(self) -> List[Dict[str, Any]]:
        """گزارش کامل پرداخت‌ها با جزئیات کاربر."""
        async with self.get_session() as session:
            stmt = (
                select(
                    Payment.payment_id, Payment.payment_date,
                    UserUUID.name.label("config_name"), UserUUID.uuid,
                    User.user_id, User.first_name, User.username
                )
                .join(UserUUID, Payment.uuid_id == UserUUID.id)
                .outerjoin(User, UserUUID.user_id == User.user_id)
                .order_by(desc(Payment.payment_date))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def delete_user_payment_history(self, uuid_id: int) -> int:
        """حذف تاریخچه پرداخت کاربر."""
        async with self.get_session() as session:
            stmt = delete(Payment).where(Payment.uuid_id == uuid_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    # --- بخش هزینه‌ها (Monthly Costs) ---

    async def add_monthly_cost(self, year: int, month: int, cost: float, description: str) -> bool:
        """ثبت هزینه ماهانه سرور."""
        async with self.get_session() as session:
            try:
                new_cost = MonthlyCost(year=year, month=month, cost=cost, description=description)
                session.add(new_cost)
                await session.commit()
                return True
            except IntegrityError:
                return False

    async def get_all_monthly_costs(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(MonthlyCost).order_by(desc(MonthlyCost.year), desc(MonthlyCost.month))
            result = await session.execute(stmt)
            return [dict(r._mapping) for r in result.scalars().all()]

    async def delete_monthly_cost(self, cost_id: int) -> bool:
        async with self.get_session() as session:
            stmt = delete(MonthlyCost).where(MonthlyCost.id == cost_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    # --- گزارش‌های مالی جامع (Financial Reports) ---

    async def get_monthly_financials(self) -> Dict[str, Any]:
        """
        محاسبه سود و زیان ماهانه بر اساس تراکنش‌های کیف پول و هزینه‌های ثبت شده.
        """
        async with self.get_session() as session:
            # 1. محاسبه درآمد (Revenue) از WalletTransaction
            # فرمت ماه: YYYY-MM
            revenue_month_str = func.to_char(WalletTransaction.transaction_date, 'YYYY-MM')
            
            stmt_rev = (
                select(
                    revenue_month_str.label("month"), 
                    func.sum(WalletTransaction.amount).label("total_revenue")
                )
                .where(
                    WalletTransaction.type.in_(['purchase', 'addon_purchase', 'gift_purchase'])
                )
                .group_by("month")
            )
            res_rev = await session.execute(stmt_rev)
            # مقدار amount در خریدها منفی است، پس abs می‌گیریم تا مثبت شود
            revenues = {row.month: abs(row.total_revenue or 0) for row in res_rev.all()}

            # 2. محاسبه هزینه‌ها (Costs) از MonthlyCost
            # ساخت رشته تاریخ YYYY-MM از ستون‌های جداگانه
            cost_month_str = func.concat(
                cast(MonthlyCost.year, String), '-', func.lpad(cast(MonthlyCost.month, String), 2, '0')
            )
            
            stmt_cost = (
                select(cost_month_str.label("month"), func.sum(MonthlyCost.cost).label("total_cost"))
                .group_by("month")
            )
            res_cost = await session.execute(stmt_cost)
            costs = {row.month: (row.total_cost or 0) for row in res_cost.all()}

            # 3. ترکیب و محاسبه سود
            all_months = sorted(list(set(revenues.keys()) | set(costs.keys())), reverse=True)
            monthly_breakdown = []
            total_revenue, total_cost = 0, 0

            for month in all_months:
                rev = revenues.get(month, 0)
                cst = costs.get(month, 0)
                monthly_breakdown.append({
                    'month': month, 
                    'revenue': rev, 
                    'cost': cst, 
                    'profit': rev - cst
                })
                total_revenue += rev
                total_cost += cst
            
            all_records = await self.get_all_monthly_costs()
            
            return {
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_revenue - total_cost,
                'monthly_breakdown': monthly_breakdown,
                'all_records': all_records
            }

    async def get_transactions_for_month(self, year: int, month: int) -> List[Dict[str, Any]]:
        """لیست تراکنش‌های یک ماه خاص."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        async with self.get_session() as session:
            stmt = (
                select(
                    WalletTransaction.id,
                    WalletTransaction.amount,
                    WalletTransaction.description,
                    WalletTransaction.transaction_date,
                    User.user_id,
                    User.first_name
                )
                .join(User, WalletTransaction.user_id == User.user_id)
                .where(
                    and_(
                        WalletTransaction.transaction_date >= start_date,
                        WalletTransaction.transaction_date < end_date,
                        WalletTransaction.amount < 0 # فقط برداشت‌ها
                    )
                )
                .order_by(desc(WalletTransaction.transaction_date))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def get_all_transactions_for_report(self) -> list:
        async with self.get_session() as session:
            stmt = select(WalletTransaction.amount, WalletTransaction.type, WalletTransaction.transaction_date).order_by(WalletTransaction.transaction_date)
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def delete_transaction(self, transaction_id: int) -> bool:
        async with self.get_session() as session:
            stmt = delete(WalletTransaction).where(WalletTransaction.id == transaction_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
            
    async def get_total_payments_in_range(self, start_date: datetime, end_date: datetime) -> int:
        async with self.get_session() as session:
            stmt = select(func.count(Payment.payment_id)).where(
                and_(Payment.payment_date >= start_date, Payment.payment_date < end_date)
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0
    
    async def check_recent_successful_payment(self, uuid_id: int, hours: int) -> bool:
        """بررسی پرداخت موفق اخیر برای جلوگیری از پرداخت تکراری."""
        threshold_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with self.get_session() as session:
            # اتصال جدول‌ها برای پیدا کردن تراکنش‌های مربوط به این UUID (از طریق User)
            stmt = (
                select(WalletTransaction.id)
                .join(User, WalletTransaction.user_id == User.user_id)
                .join(UserUUID, User.user_id == UserUUID.user_id)
                .where(
                    and_(
                        UserUUID.id == uuid_id,
                        WalletTransaction.transaction_date >= threshold_time,
                        WalletTransaction.type.in_(['purchase', 'addon_purchase', 'gift_purchase', 'charge'])
                    )
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None