# bot/db/usage.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import pytz
import jdatetime

from sqlalchemy import select, delete, func, desc, and_, or_, extract, case, cast, Date
from sqlalchemy.orm import aliased

# وارد کردن مدل‌ها
from .base import UsageSnapshot, UserUUID, User

logger = logging.getLogger(__name__)


class UsageDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به آمار مصرف (usage) کاربران و سیستم.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    async def add_usage_snapshot(self, uuid_id: int, hiddify_usage: float, marzban_usage: float) -> None:
        """یک اسنپ‌شات جدید از مصرف کاربر ثبت می‌کند."""
        async with self.get_session() as session:
            snapshot = UsageSnapshot(
                uuid_id=uuid_id,
                hiddify_usage_gb=hiddify_usage,
                marzban_usage_gb=marzban_usage,
                taken_at=datetime.now(timezone.utc)
            )
            session.add(snapshot)
            await session.commit()

    async def get_usage_since_midnight(self, uuid_id: int) -> Dict[str, float]:
        """
        دریافت مصرف روزانه با استفاده از شناسه عددی (ID)
        (این متد برای رفع خطای Account Detail اضافه شده است)
        """
        result_map = await self.get_bulk_usage_since_midnight([uuid_id])
        
        if result_map:
            return list(result_map.values())[0]
            
        return {'hiddify': 0.0, 'marzban': 0.0}

    async def get_all_daily_usage_since_midnight(self) -> Dict[str, Dict[str, float]]:
        """
        دریافت مصرف روزانه همه کاربران (نسخه بهینه شده).
        """
        # ۱. دریافت لیست تمام UUID های فعال
        # نکته: متد get_all_user_uuids دیکشنری برمی‌گرداند، ما فقط لیست ID ها را می‌خواهیم
        all_uuids_data = await self.get_all_user_uuids()
        
        active_ids = [
            u['id'] for u in all_uuids_data 
            if u.get('is_active')
        ]

        if not active_ids:
            return {}

        # ۲. فراخوانی متد Bulk که نوشتیم
        return await self.get_bulk_usage_since_midnight(active_ids)

    async def get_usage_since_midnight_by_uuid(self, uuid_str: str) -> Dict[str, float]:
        """دریافت مصرف روزانه یک کاربر خاص با استفاده از موتور محاسبه جدید."""
        # فرض بر این است که متد get_uuid_id_by_uuid در کلاس UserDB موجود است
        uuid_id = await self.get_uuid_id_by_uuid(uuid_str)
        
        if uuid_id:
            # استفاده از تابع بهینه جدید برای یک نفر
            bulk_result = await self.get_bulk_usage_since_midnight([uuid_id])
            
            # دریافت نتیجه از دیکشنری خروجی (با کلید UUID String)
            # اگر نتیجه‌ای نبود، صفر برگردان
            return bulk_result.get(uuid_str, {'hiddify': 0.0, 'marzban': 0.0})
            
        return {'hiddify': 0.0, 'marzban': 0.0}

    async def get_user_daily_usage_history_by_panel(self, uuid_id: int, days: int = 7) -> list:
        """تاریخچه مصرف روزانه کاربر به تفکیک پنل."""
        logger.info(f"Generating daily usage history for UUID {uuid_id} (last {days} days)...")
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        history = []

        async with self.get_session() as session:
            for i in range(days - 1, -1, -1):
                target_date = (now_tehran - timedelta(days=i)).date()
                day_start_local = datetime(target_date.year, target_date.month, target_date.day)
                day_start_utc = tehran_tz.localize(day_start_local).astimezone(pytz.utc).replace(tzinfo=None)
                day_end_utc = day_start_utc + timedelta(days=1)

                try:
                    # Baseline Snapshot
                    stmt_base = (
                        select(UsageSnapshot)
                        .where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < day_start_utc))
                        .order_by(desc(UsageSnapshot.taken_at))
                        .limit(1)
                    )
                    
                    # End Snapshot
                    stmt_end = (
                        select(UsageSnapshot)
                        .where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < day_end_utc))
                        .order_by(desc(UsageSnapshot.taken_at))
                        .limit(1)
                    )

                    base_res = await session.execute(stmt_base)
                    baseline_snap = base_res.scalar_one_or_none()

                    end_res = await session.execute(stmt_end)
                    end_snap = end_res.scalar_one_or_none()

                    if not end_snap:
                        history.append({"date": target_date, "hiddify_usage": 0.0, "marzban_usage": 0.0, "total_usage": 0.0})
                        continue

                    h_start = baseline_snap.hiddify_usage_gb if baseline_snap else 0.0
                    m_start = baseline_snap.marzban_usage_gb if baseline_snap else 0.0
                    h_end = end_snap.hiddify_usage_gb or 0.0
                    m_end = end_snap.marzban_usage_gb or 0.0

                    daily_h = h_end - h_start if h_end >= h_start else h_end
                    daily_m = m_end - m_start if m_end >= m_start else m_end

                    history.append({
                        "date": target_date,
                        "hiddify_usage": round(max(0.0, daily_h), 2),
                        "marzban_usage": round(max(0.0, daily_m), 2),
                        "total_usage": round(max(0.0, daily_h + daily_m), 2)
                    })

                except Exception as e:
                    logger.error(f"Failed to calculate daily usage for {target_date}: {e}")
                    history.append({"date": target_date, "hiddify_usage": 0.0, "marzban_usage": 0.0, "total_usage": 0.0})
        
        return history

    async def delete_all_daily_snapshots(self) -> int:
        """حذف اسنپ‌شات‌های امروز."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.get_session() as session:
            stmt = delete(UsageSnapshot).where(UsageSnapshot.taken_at >= today_start)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def delete_old_snapshots(self, days_to_keep: int = 3) -> int:
        """حذف اسنپ‌شات‌های قدیمی."""
        time_limit = datetime.now() - timedelta(days=days_to_keep)
        async with self.get_session() as session:
            stmt = delete(UsageSnapshot).where(UsageSnapshot.taken_at < time_limit)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    def get_week_start_utc(self) -> datetime:
        """(Helper) شروع هفته شمسی به UTC."""
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_jalali = jdatetime.datetime.now(tz=tehran_tz)
        days_since_saturday = (now_jalali.weekday() + 1) % 7 # شنبه = 0
        week_start = (datetime.now(tehran_tz) - timedelta(days=days_since_saturday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return week_start.astimezone(pytz.utc).replace(tzinfo=None)

    async def get_weekly_usage_by_uuid(self, uuid_str: str) -> Dict[str, float]:
        """مصرف هفتگی یک UUID."""
        uuid_id = await self.get_uuid_id_by_uuid(uuid_str)
        if not uuid_id:
            return {'hiddify': 0.0, 'marzban': 0.0}

        week_start = self.get_week_start_utc()

        async with self.get_session() as session:
            # Start Snapshot
            stmt_start = (
                select(UsageSnapshot)
                .where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < week_start))
                .order_by(desc(UsageSnapshot.taken_at))
                .limit(1)
            )
            # Latest Snapshot
            stmt_end = (
                select(UsageSnapshot)
                .where(UsageSnapshot.uuid_id == uuid_id)
                .order_by(desc(UsageSnapshot.taken_at))
                .limit(1)
            )

            res_start = await session.execute(stmt_start)
            start_snap = res_start.scalar_one_or_none()

            res_end = await session.execute(stmt_end)
            end_snap = res_end.scalar_one_or_none()

            h_start = start_snap.hiddify_usage_gb if start_snap else 0.0
            m_start = start_snap.marzban_usage_gb if start_snap else 0.0
            h_end = end_snap.hiddify_usage_gb if end_snap else 0.0
            m_end = end_snap.marzban_usage_gb if end_snap else 0.0

            h_usage = h_end - h_start if h_end >= h_start else h_end
            m_usage = m_end - m_start if m_end >= m_start else m_end

            return {'hiddify': max(0.0, h_usage), 'marzban': max(0.0, m_usage)}

    async def get_panel_usage_in_intervals(self, uuid_id: int, panel_name: str) -> Dict[int, float]:
        """مصرف در بازه‌های زمانی مختلف."""
        # اعتبارسنجی نام ستون برای جلوگیری از SQL Injection (هرچند با ORM ایمن است اما برای اطمینان)
        if panel_name == 'hiddify_usage_gb':
            column = UsageSnapshot.hiddify_usage_gb
        elif panel_name == 'marzban_usage_gb':
            column = UsageSnapshot.marzban_usage_gb
        else:
            return {}

        now = datetime.now()
        intervals = {3: 0.0, 6: 0.0, 12: 0.0, 24: 0.0}

        async with self.get_session() as session:
            for hours in intervals.keys():
                time_ago = now - timedelta(hours=hours)
                
                # محاسبه Max - Min در بازه زمانی
                stmt = select(func.max(column) - func.min(column)).where(
                    and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at >= time_ago)
                )
                result = await session.execute(stmt)
                val = result.scalar_one_or_none()
                if val is not None:
                    intervals[hours] = max(0.0, val)
                    
        return intervals

    async def get_daily_usage_summary(self) -> List[Dict[str, Any]]:
        """
        خلاصه مصرف روزانه کل سیستم برای ۷ روز گذشته.
        🚀 نسخه فوق‌بهینه: تبدیل 7000 کوئری به 1 کوئری!
        """
        tehran_tz = pytz.timezone('Asia/Tehran')
        days_to_check = 7
        start_date = datetime.now(timezone.utc) - timedelta(days=days_to_check)
        
        async with self.get_session() as session:
            # کوئری تجمیعی: گروه‌بندی بر اساس روز و UUID، سپس محاسبه Max-Min
            # ما نیاز داریم برای هر کاربر در هر روز مصرفش را حساب کنیم و بعد همه را جمع بزنیم.
            
            # 1. تبدیل taken_at به Date (بدون ساعت)
            snapshot_date = cast(UsageSnapshot.taken_at, Date).label('snap_date')
            
            # 2. محاسبه Min و Max مصرف هر کاربر در هر روز
            subq = (
                select(
                    snapshot_date,
                    UsageSnapshot.uuid_id,
                    (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('daily_h'),
                    (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('daily_m')
                )
                .where(UsageSnapshot.taken_at >= start_date)
                .group_by(snapshot_date, UsageSnapshot.uuid_id)
                .subquery()
            )

            # 3. جمع زدن مصرف همه کاربران در هر روز
            stmt = (
                select(
                    subq.c.snap_date,
                    func.sum(subq.c.daily_h + subq.c.daily_m).label('total_daily')
                )
                .group_by(subq.c.snap_date)
                .order_by(subq.c.snap_date)
            )

            result = await session.execute(stmt)
            rows = result.all()

        # فرمت‌دهی خروجی
        summary_dict = {row.snap_date: row.total_daily for row in rows}
        final_summary = []
        
        # پر کردن روزهای خالی (اگر روزی مصرف 0 بود)
        for i in range(days_to_check):
            d = (datetime.now().date() - timedelta(days=i))
            # تبدیل به string برای سازگاری با فرانت/تلگرام
            # نکته: دیتابیس ممکن است date برگرداند، مقایسه باید درست باشد
            # فرض ساده: کلیدهای summary_dict آبجکت date هستند
            usage = summary_dict.get(d, 0.0)
            final_summary.append({
                "date": d.strftime('%Y-%m-%d'),
                "total_usage": round(usage, 2)
            })

        return sorted(final_summary, key=lambda x: x['date'])

    async def get_new_users_per_month_stats(self) -> Dict[str, int]:
        """آمار کاربران جدید در هر ماه میلادی."""
        async with self.get_session() as session:
            # استفاده از to_char برای Postgres
            month_col = func.to_char(UserUUID.created_at, 'YYYY-MM')
            stmt = (
                select(month_col.label("month"), func.count(func.distinct(UserUUID.user_id)).label("count"))
                .group_by("month")
                .order_by(desc("month"))
                .limit(12)
            )
            result = await session.execute(stmt)
            return {row.month: row.count for row in result.all() if row.month}

    async def get_daily_active_users_count(self) -> int:
        """تعداد کاربران فعال در ۲۴ ساعت گذشته."""
        yesterday = datetime.now() - timedelta(days=1)
        async with self.get_session() as session:
            stmt = select(func.count(func.distinct(UsageSnapshot.uuid_id))).where(UsageSnapshot.taken_at >= yesterday)
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_top_consumers_by_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        """لیست ۱۰ کاربر پرمصرف."""
        thirty_days_ago = datetime.now() - timedelta(days=30)
        async with self.get_session() as session:
            # زیرکوئری برای محاسبه مصرف هر UUID
            # نکته: محاسبه دقیق مصرف با ریست شدن در SQL پیچیده است.
            # اینجا از Max - Min استفاده می‌کنیم که تقریب خوبی است اگر ریست زیاد نباشد.
            subq = (
                select(
                    UsageSnapshot.uuid_id,
                    (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h_usage'),
                    (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m_usage')
                )
                .where(UsageSnapshot.taken_at >= thirty_days_ago)
                .group_by(UsageSnapshot.uuid_id)
                .subquery()
            )

            stmt = (
                select(
                    User.user_id.label('telegram_id'), 
                    UserUUID.name,
                    func.sum(subq.c.h_usage + subq.c.m_usage).label('total_usage')
                )
                .join(UserUUID, subq.c.uuid_id == UserUUID.id)
                .join(User, UserUUID.user_id == User.user_id)
                .group_by(User.user_id, UserUUID.name)
                .order_by(desc('total_usage'))
                .limit(limit)
            )
            
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def get_new_users_in_range(self, start_date: datetime, end_date: datetime) -> int:
        """تعداد کاربران جدید در بازه زمانی."""
        async with self.get_session() as session:
            stmt = select(func.count(func.distinct(UserUUID.user_id))).where(
                and_(UserUUID.created_at >= start_date, UserUUID.created_at <= end_date)
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_activity_heatmap_data(self) -> List[Dict[str, Any]]:
        """داده‌های نقشه حرارتی (روز هفته / ساعت)."""
        time_limit = datetime.now() - timedelta(days=7)
        async with self.get_session() as session:
            # Postgres: extract(dow from timestamp), extract(hour from timestamp)
            dow = extract('dow', UsageSnapshot.taken_at).label('day_of_week')
            hour = extract('hour', UsageSnapshot.taken_at).label('hour_of_day')
            total = func.sum(UsageSnapshot.hiddify_usage_gb + UsageSnapshot.marzban_usage_gb).label('total_usage')
            
            stmt = (
                select(dow, hour, total)
                .where(UsageSnapshot.taken_at >= time_limit)
                .group_by(dow, hour)
            )
            result = await session.execute(stmt)
            # تبدیل dow پستگرس (0=یکشنبه) به فرمت قبلی اگر لازم است
            return [dict(row._mapping) for row in result.all()]

    async def get_daily_active_users_by_panel(self, days: int = 30) -> List[Dict[str, Any]]:
        """کاربران فعال روزانه به تفکیک پنل."""
        date_limit = datetime.now() - timedelta(days=days)
        async with self.get_session() as session:
            taken_date = cast(UsageSnapshot.taken_at, Date).label('date')
            
            # شمارش شرطی
            h_count = func.count(func.distinct(case((UsageSnapshot.hiddify_usage_gb > 0, UsageSnapshot.uuid_id), else_=None)))
            m_count = func.count(func.distinct(case((UsageSnapshot.marzban_usage_gb > 0, UsageSnapshot.uuid_id), else_=None)))
            
            stmt = (
                select(taken_date, h_count.label('hiddify_users'), m_count.label('marzban_users'))
                .where(UsageSnapshot.taken_at >= date_limit)
                .group_by(taken_date)
                .order_by(taken_date.asc())
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    # ... (سایر متدها مشابه بالا پیاده‌سازی می‌شوند)
    
    async def get_total_usage_in_last_n_days(self, days: int) -> float:
        """مجموع کل مصرف در N روز."""
        time_limit = datetime.now() - timedelta(days=days)
        async with self.get_session() as session:
            # محاسبه تقریبی با Max - Min
            subq = (
                select(
                    (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h'),
                    (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m')
                )
                .where(UsageSnapshot.taken_at >= time_limit)
                .group_by(UsageSnapshot.uuid_id)
                .subquery()
            )
            stmt = select(func.sum(subq.c.h + subq.c.m))
            result = await session.execute(stmt)
            return result.scalar_one() or 0.0

    async def get_weekly_usage_by_time_of_day(self, uuid_id: int) -> Dict[str, float]:
        """مصرف هفتگی به تفکیک ساعت (صبح، ظهر، عصر، شب)."""
        tehran_tz = pytz.timezone("Asia/Tehran")
        time_slots = {'morning': (6, 12), 'afternoon': (12, 18), 'evening': (18, 24), 'night': (0, 6)}
        usage_stats = {k: 0.0 for k in time_slots}
        
        limit_time = datetime.now() - timedelta(days=7)
        
        async with self.get_session() as session:
            # اسنپ‌شات‌ها را می‌گیریم و در پایتون پردازش می‌کنیم (به خاطر پیچیدگی اختلاف زمانی و ریست)
            stmt = (
                select(UsageSnapshot)
                .where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at >= limit_time))
                .order_by(UsageSnapshot.taken_at.asc())
            )
            result = await session.execute(stmt)
            snapshots = result.scalars().all()
            
            # دریافت اسنپ‌شات شروع برای محاسبه اولین بازه
            start_stmt = (
                select(UsageSnapshot)
                .where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < limit_time))
                .order_by(desc(UsageSnapshot.taken_at))
                .limit(1)
            )
            start_res = await session.execute(start_stmt)
            last_snap = start_res.scalar_one_or_none()
            
            last_h = last_snap.hiddify_usage_gb if last_snap else 0.0
            last_m = last_snap.marzban_usage_gb if last_snap else 0.0
            
            for snap in snapshots:
                curr_h = snap.hiddify_usage_gb or 0.0
                curr_m = snap.marzban_usage_gb or 0.0
                
                h_diff = curr_h - last_h if curr_h >= last_h else curr_h
                m_diff = curr_m - last_m if curr_m >= last_m else curr_m
                diff = max(0, h_diff) + max(0, m_diff)
                
                if diff > 0:
                    # تبدیل زمان UTC دیتابیس به تهران برای دسته‌بندی
                    snap_time_tehran = pytz.utc.localize(snap.taken_at).astimezone(tehran_tz)
                    hour = snap_time_tehran.hour
                    
                    for slot, (s, e) in time_slots.items():
                        if s <= hour < e:
                            usage_stats[slot] += diff
                            break
                
                last_h, last_m = curr_h, curr_m
                
        return usage_stats
    
    async def get_bulk_usage_since_midnight(self, active_uuids: List[int]) -> Dict[str, Dict[str, float]]:
        """
        محاسبه مصرف روزانه تمام کاربران فعال به صورت یکجا (Highly Optimized).
        به جای ۱۰۰۰ کوئری، فقط ۳ کوئری اجرا می‌کند.
        """
        if not active_uuids:
            return {}

        # ۱. محاسبه زمان نیمه‌شب
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        today_midnight = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
        today_midnight_utc = today_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        async with self.get_session() as session:
            # ---------------------------------------------------------
            # کوئری ۱: دریافت آخرین اسنپ‌شاتِ "قبل از نیمه‌شب" (Baseline اصلی)
            # ---------------------------------------------------------
            stmt_baseline = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)  # فقط در Postgres کار می‌کند
                .where(
                    and_(
                        UsageSnapshot.uuid_id.in_(active_uuids),
                        UsageSnapshot.taken_at < today_midnight_utc
                    )
                )
                .order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
            )
            res_base = await session.execute(stmt_baseline)
            # تبدیل به دیکشنری: {uuid_id: snapshot_obj}
            baselines = {r.uuid_id: r for r in res_base.scalars().all()}

            # ---------------------------------------------------------
            # کوئری ۲: دریافت اولین اسنپ‌شاتِ "امروز" (Baseline جایگزین برای کاربران جدید)
            # ---------------------------------------------------------
            stmt_first_today = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)
                .where(
                    and_(
                        UsageSnapshot.uuid_id.in_(active_uuids),
                        UsageSnapshot.taken_at >= today_midnight_utc
                    )
                )
                .order_by(UsageSnapshot.uuid_id, UsageSnapshot.taken_at.asc()) # اولین رکورد (ASC)
            )
            res_first = await session.execute(stmt_first_today)
            firsts_today = {r.uuid_id: r for r in res_first.scalars().all()}

            # ---------------------------------------------------------
            # کوئری ۳: دریافت آخرین وضعیت مصرف (Current Usage)
            # ---------------------------------------------------------
            stmt_current = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)
                .where(UsageSnapshot.uuid_id.in_(active_uuids))
                .order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
            )
            res_curr = await session.execute(stmt_current)
            currents = {r.uuid_id: r for r in res_curr.scalars().all()}
            
            # برای مپ کردن ID به UUID String نیاز داریم
            # (فرض بر این است که لیست ورودی ID است، اما خروجی باید UUID String باشد)
            stmt_ids = select(UserUUID.id, UserUUID.uuid).where(UserUUID.id.in_(active_uuids))
            res_ids = await session.execute(stmt_ids)
            id_to_uuid_map = {r.id: str(r.uuid) for r in res_ids.all()}

        # ---------------------------------------------------------
        # فاز محاسبه در حافظه (Python Logic)
        # ---------------------------------------------------------
        final_usage_map = {}

        for uid in active_uuids:
            uuid_str = id_to_uuid_map.get(uid)
            if not uuid_str:
                continue

            last_snap = currents.get(uid)
            if not last_snap:
                final_usage_map[uuid_str] = {'hiddify': 0.0, 'marzban': 0.0}
                continue

            # تعیین نقطه شروع (Start Point)
            base_snap = baselines.get(uid)
            if not base_snap:
                # اگر قبل از نیمه‌شب رکوردی نبود، اولین رکورد امروز را ملاک قرار بده
                base_snap = firsts_today.get(uid)
            
            h_start, m_start = 0.0, 0.0
            if base_snap:
                h_start = base_snap.hiddify_usage_gb or 0.0
                m_start = base_snap.marzban_usage_gb or 0.0
            
            h_end = last_snap.hiddify_usage_gb or 0.0
            m_end = last_snap.marzban_usage_gb or 0.0

            # محاسبه اختلاف با شرط عدم منفی شدن (در صورت ریست سرور)
            h_usage = h_end - h_start if h_end >= h_start else h_end
            m_usage = m_end - m_start if m_end >= m_start else m_end

            final_usage_map[uuid_str] = {
                'hiddify': round(max(0.0, h_usage), 3),
                'marzban': round(max(0.0, m_usage), 3)
            }

        return final_usage_map