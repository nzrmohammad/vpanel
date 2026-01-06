# bot/db/usage.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import pytz
import jdatetime

from sqlalchemy import select, delete, func, desc, and_, case, cast, Date, extract, distinct
from sqlalchemy.orm import aliased
from bot.database import db
from .base import UsageSnapshot, UserUUID, User

logger = logging.getLogger(__name__)


class UsageDB:
    """
    مدیریت اسنپ‌شات‌های مصرف برای محاسبه دقیق مصرف روزانه.
    """

    def _calculate_diff(self, start_val: float, end_val: float) -> float:
        """محاسبه اختلاف مصرف با در نظر گرفتن ریست شدن سرور (منطق پروژه قدیمی)."""
        start_val = start_val or 0.0
        end_val = end_val or 0.0
        
        # اگر مصرف فعلی بیشتر یا مساوی شروع بود، اختلاف را برگردان
        if end_val >= start_val:
            return end_val - start_val
        # در غیر این صورت (پنل ریست شده)، کل مصرف فعلی را برگردان
        else:
            return end_val

    async def add_usage_snapshot(self, uuid_id: int, 
                                 hiddify_usage: float, 
                                 marzban_usage: float, 
                                 remnawave_usage: float, 
                                 pasarguard_usage: float):
        """ثبت یک اسنپ‌شات جدید در دیتابیس."""
        async with db.get_session() as session:
            snapshot = UsageSnapshot(
                uuid_id=uuid_id,
                hiddify_usage_gb=hiddify_usage,
                marzban_usage_gb=marzban_usage,
                remnawave_usage_gb=remnawave_usage,
                pasarguard_usage_gb=pasarguard_usage,
                # taken_at به صورت خودکار توسط مدل پر می‌شود (func.now)
            )
            session.add(snapshot)
            await session.commit()

    async def get_usage_since_midnight(self, uuid_id: int) -> dict:
        """
        محاسبه مصرف دقیق امروز (از ۰۰:۰۰ بامداد) برای تمام پنل‌ها.
        """
        # محاسبه زمان نیمه‌شب به وقت تهران و تبدیل به UTC
        import pytz
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        midnight_tehran = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_utc = midnight_tehran.astimezone(timezone.utc)

        async with db.get_session() as session:
            # ۱. دریافت آخرین اسنپ‌شات قبل از نیمه‌شب (Baseline)
            stmt_base = select(UsageSnapshot).where(
                UsageSnapshot.uuid_id == uuid_id,
                UsageSnapshot.taken_at < midnight_utc
            ).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            
            baseline = (await session.execute(stmt_base)).scalar_one_or_none()

            # ۲. دریافت آخرین اسنپ‌شات ثبت شده (Current)
            stmt_curr = select(UsageSnapshot).where(
                UsageSnapshot.uuid_id == uuid_id
            ).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            
            current = (await session.execute(stmt_curr)).scalar_one_or_none()

            # اگر اسنپ‌شات جدیدی نباشد، مصرف صفر است
            if not current:
                return {'total': 0.0, 'hiddify': 0.0, 'marzban': 0.0, 'remnawave': 0.0, 'pasarguard': 0.0}

            # مقادیر شروع (اگر بیس‌لاین نباشد، یعنی کاربر امروز ساخته شده -> شروع از صفر)
            base_h = baseline.hiddify_usage_gb if baseline else 0.0
            base_m = baseline.marzban_usage_gb if baseline else 0.0
            base_r = baseline.remnawave_usage_gb if baseline else 0.0
            base_p = baseline.pasarguard_usage_gb if baseline else 0.0

            # مقادیر پایان
            curr_h = current.hiddify_usage_gb
            curr_m = current.marzban_usage_gb
            curr_r = current.remnawave_usage_gb
            curr_p = current.pasarguard_usage_gb

            # محاسبه اختلاف با تابع کمکی
            usage_h = self._calculate_diff(base_h, curr_h)
            usage_m = self._calculate_diff(base_m, curr_m)
            usage_r = self._calculate_diff(base_r, curr_r)
            usage_p = self._calculate_diff(base_p, curr_p)
            
            total = usage_h + usage_m + usage_r + usage_p

            return {
                'total': round(total, 3),
                'hiddify': round(usage_h, 3),
                'marzban': round(usage_m, 3),
                'remnawave': round(usage_r, 3),
                'pasarguard': round(usage_p, 3)
            }

    async def get_usage_since_midnight_by_uuid(self, uuid_str: str) -> Dict[str, float]:
        async with self.get_session() as session:
            stmt = select(UserUUID.id).where(UserUUID.uuid == uuid_str)
            res = await session.execute(stmt)
            uuid_id = res.scalar_one_or_none()
        
        if uuid_id:
            data = await self.get_bulk_usage_since_midnight([uuid_id])
            return data.get(uuid_str, {'hiddify': 0.0, 'marzban': 0.0})
        return {'hiddify': 0.0, 'marzban': 0.0}

    async def get_bulk_usage_since_midnight(self, active_uuid_ids: List[int]) -> Dict[str, Dict[str, float]]:
        """محاسبه بهینه مصرف روزانه برای لیست کاربران (Optimized for Postgres)."""
        if not active_uuid_ids:
            return {}

        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        today_midnight = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
        today_midnight_utc = today_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        async with self.get_session() as session:
            # مپینگ ID به UUID String
            stmt_ids = select(UserUUID.id, UserUUID.uuid).where(UserUUID.id.in_(active_uuid_ids))
            res_ids = await session.execute(stmt_ids)
            id_to_uuid_map = {r.id: str(r.uuid) for r in res_ids.all()}

            # 1. Baseline (قبل از نیمه‌شب)
            stmt_base = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)
                .where(and_(UsageSnapshot.uuid_id.in_(active_uuid_ids), UsageSnapshot.taken_at < today_midnight_utc))
                .order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
            )
            res_base = await session.execute(stmt_base)
            baselines = {r.uuid_id: r for r in res_base.scalars().all()}

            # 2. First Today (اولین بعد از نیمه‌شب - برای کاربران جدید امروز)
            stmt_first = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)
                .where(and_(UsageSnapshot.uuid_id.in_(active_uuid_ids), UsageSnapshot.taken_at >= today_midnight_utc))
                .order_by(UsageSnapshot.uuid_id, UsageSnapshot.taken_at.asc())
            )
            res_first = await session.execute(stmt_first)
            firsts_today = {r.uuid_id: r for r in res_first.scalars().all()}

            # 3. Current (آخرین وضعیت)
            stmt_curr = (
                select(UsageSnapshot)
                .distinct(UsageSnapshot.uuid_id)
                .where(UsageSnapshot.uuid_id.in_(active_uuid_ids))
                .order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
            )
            res_curr = await session.execute(stmt_curr)
            currents = {r.uuid_id: r for r in res_curr.scalars().all()}

        final_usage_map = {}
        for uid in active_uuid_ids:
            uuid_str = id_to_uuid_map.get(uid)
            if not uuid_str: continue

            last_snap = currents.get(uid)
            if not last_snap:
                final_usage_map[uuid_str] = {'hiddify': 0.0, 'marzban': 0.0}
                continue

            start_snap = baselines.get(uid) or firsts_today.get(uid)
            
            h_start = start_snap.hiddify_usage_gb if start_snap else 0.0
            m_start = start_snap.marzban_usage_gb if start_snap else 0.0
            h_end = last_snap.hiddify_usage_gb or 0.0
            m_end = last_snap.marzban_usage_gb or 0.0

            final_usage_map[uuid_str] = {
                'hiddify': round(self._calculate_diff(h_start, h_end), 3),
                'marzban': round(self._calculate_diff(m_start, m_end), 3)
            }
        return final_usage_map

    async def get_all_daily_usage_since_midnight(self) -> Dict[str, Dict[str, float]]:
        async with self.get_session() as session:
            stmt = select(UserUUID.id).where(UserUUID.is_active == True)
            res = await session.execute(stmt)
            active_ids = res.scalars().all()
        return await self.get_bulk_usage_since_midnight(active_ids)

    async def get_user_daily_usage_history_by_panel(self, uuid_id: int, days: int = 7) -> list:
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        history = []

        async with self.get_session() as session:
            for i in range(days - 1, -1, -1):
                target_date = (now_tehran - timedelta(days=i)).date()
                day_start_utc = tehran_tz.localize(datetime(target_date.year, target_date.month, target_date.day)).astimezone(pytz.utc).replace(tzinfo=None)
                day_end_utc = day_start_utc + timedelta(days=1)

                try:
                    stmt_base = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < day_start_utc)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
                    base = (await session.execute(stmt_base)).scalar_one_or_none()

                    stmt_end = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < day_end_utc)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
                    end_snap = (await session.execute(stmt_end)).scalar_one_or_none()

                    if not end_snap:
                        history.append({"date": target_date, "hiddify_usage": 0.0, "marzban_usage": 0.0, "total_usage": 0.0})
                        continue

                    h_start = base.hiddify_usage_gb if base else 0.0
                    m_start = base.marzban_usage_gb if base else 0.0
                    h_end = end_snap.hiddify_usage_gb or 0.0
                    m_end = end_snap.marzban_usage_gb or 0.0

                    d_h = self._calculate_diff(h_start, h_end)
                    d_m = self._calculate_diff(m_start, m_end)

                    history.append({
                        "date": target_date,
                        "hiddify_usage": round(max(0.0, d_h), 2),
                        "marzban_usage": round(max(0.0, d_m), 2),
                        "total_usage": round(max(0.0, d_h + d_m), 2)
                    })
                except Exception as e:
                    logger.error(f"Error history date {target_date}: {e}")
                    history.append({"date": target_date, "hiddify_usage": 0.0, "marzban_usage": 0.0, "total_usage": 0.0})
        return history

    async def get_user_daily_usage_history(self, uuid_id: int, days: int = 7) -> List[Dict[str, Any]]:
        return await self.get_user_daily_usage_history_by_panel(uuid_id, days)

    async def delete_all_daily_snapshots(self) -> int:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.get_session() as session:
            stmt = delete(UsageSnapshot).where(UsageSnapshot.taken_at >= today_start)
            res = await session.execute(stmt)
            await session.commit()
            return res.rowcount

    async def delete_old_snapshots(self, days_to_keep: int = 3) -> int:
        time_limit = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        async with self.get_session() as session:
            stmt = delete(UsageSnapshot).where(UsageSnapshot.taken_at < time_limit)
            res = await session.execute(stmt)
            await session.commit()
            return res.rowcount

    def get_week_start_utc(self) -> datetime:
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_jalali = jdatetime.datetime.now(tz=tehran_tz)
        days_since_saturday = (now_jalali.weekday() + 1) % 7
        week_start = (datetime.now(tehran_tz) - timedelta(days=days_since_saturday)).replace(hour=0, minute=0, second=0, microsecond=0)
        return week_start.astimezone(pytz.utc).replace(tzinfo=None)

    async def get_weekly_usage_by_uuid(self, uuid_str: str) -> Dict[str, float]:
        async with self.get_session() as session:
            stmt_id = select(UserUUID.id).where(UserUUID.uuid == uuid_str)
            res = await session.execute(stmt_id)
            uuid_id = res.scalar_one_or_none()
        
        if not uuid_id:
            return {'hiddify': 0.0, 'marzban': 0.0}

        week_start = self.get_week_start_utc()
        async with self.get_session() as session:
            stmt_base = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < week_start)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            base = (await session.execute(stmt_base)).scalar_one_or_none()
            
            stmt_end = select(UsageSnapshot).where(UsageSnapshot.uuid_id == uuid_id).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            end_s = (await session.execute(stmt_end)).scalar_one_or_none()

            h_s = base.hiddify_usage_gb if base else 0.0
            m_s = base.marzban_usage_gb if base else 0.0
            h_e = end_s.hiddify_usage_gb if end_s else 0.0
            m_e = end_s.marzban_usage_gb if end_s else 0.0

            return {
                'hiddify': max(0.0, self._calculate_diff(h_s, h_e)),
                'marzban': max(0.0, self._calculate_diff(m_s, m_e))
            }

    async def get_panel_usage_in_intervals(self, uuid_id: int, panel_name: str) -> Dict[int, float]:
        column = UsageSnapshot.hiddify_usage_gb if panel_name == 'hiddify_usage_gb' else UsageSnapshot.marzban_usage_gb
        now = datetime.now(timezone.utc)
        intervals = {3: 0.0, 6: 0.0, 12: 0.0, 24: 0.0}

        async with self.get_session() as session:
            for hours in intervals.keys():
                time_ago = now - timedelta(hours=hours)
                stmt = select(func.max(column) - func.min(column)).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at >= time_ago))
                res = await session.execute(stmt)
                val = res.scalar_one_or_none()
                if val: intervals[hours] = max(0.0, val)
        return intervals

    async def get_daily_usage_summary(self) -> List[Dict[str, Any]]:
        days_to_check = 7
        start_date = datetime.now(timezone.utc) - timedelta(days=days_to_check)
        async with self.get_session() as session:
            snap_date = cast(UsageSnapshot.taken_at, Date).label('snap_date')
            subq = (
                select(
                    snap_date,
                    UsageSnapshot.uuid_id,
                    (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h'),
                    (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m')
                ).where(UsageSnapshot.taken_at >= start_date)
                .group_by(snap_date, UsageSnapshot.uuid_id).subquery()
            )
            stmt = select(subq.c.snap_date, func.sum(subq.c.h + subq.c.m)).group_by(subq.c.snap_date)
            rows = (await session.execute(stmt)).all()

        summary_dict = {row[0]: row[1] for row in rows}
        final_summary = []
        for i in range(days_to_check):
            d = (datetime.now().date() - timedelta(days=i))
            final_summary.append({"date": d.strftime('%Y-%m-%d'), "total_usage": round(summary_dict.get(d, 0.0), 2)})
        return sorted(final_summary, key=lambda x: x['date'])

    async def get_new_users_per_month_stats(self) -> Dict[str, int]:
        async with self.get_session() as session:
            month_col = func.to_char(UserUUID.created_at, 'YYYY-MM')
            stmt = select(month_col, func.count(distinct(UserUUID.user_id))).group_by(month_col).order_by(desc(month_col)).limit(12)
            rows = (await session.execute(stmt)).all()
            return {row[0]: row[1] for row in rows if row[0]}

    async def get_daily_active_users_count(self) -> int:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        async with self.get_session() as session:
            stmt = select(func.count(distinct(UsageSnapshot.uuid_id))).where(UsageSnapshot.taken_at >= yesterday)
            return (await session.execute(stmt)).scalar_one() or 0

    async def get_top_consumers_by_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        async with self.get_session() as session:
            subq = (
                select(
                    UsageSnapshot.uuid_id,
                    (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h'),
                    (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m')
                ).where(UsageSnapshot.taken_at >= thirty_days_ago)
                .group_by(UsageSnapshot.uuid_id).subquery()
            )
            stmt = (
                select(User.user_id.label('telegram_id'), UserUUID.name, func.sum(subq.c.h + subq.c.m).label('total_usage'))
                .join(UserUUID, subq.c.uuid_id == UserUUID.id)
                .join(User, UserUUID.user_id == User.user_id)
                .group_by(User.user_id, UserUUID.name)
                .order_by(desc('total_usage'))
                .limit(limit)
            )
            res = await session.execute(stmt)
            return [dict(row._mapping) for row in res.all()]

    async def get_new_users_in_range(self, start_date: datetime, end_date: datetime) -> int:
        async with self.get_session() as session:
            stmt = select(func.count(distinct(UserUUID.user_id))).where(and_(UserUUID.created_at >= start_date, UserUUID.created_at <= end_date))
            return (await session.execute(stmt)).scalar_one() or 0

    async def get_activity_heatmap_data(self) -> List[Dict[str, Any]]:
        time_limit = datetime.now(timezone.utc) - timedelta(days=7)
        async with self.get_session() as session:
            dow = extract('dow', UsageSnapshot.taken_at).label('day_of_week')
            hour = extract('hour', UsageSnapshot.taken_at).label('hour_of_day')
            total = func.sum(UsageSnapshot.hiddify_usage_gb + UsageSnapshot.marzban_usage_gb).label('total_usage')
            stmt = select(dow, hour, total).where(UsageSnapshot.taken_at >= time_limit).group_by(dow, hour)
            res = await session.execute(stmt)
            return [dict(row._mapping) for row in res.all()]

    async def get_daily_active_users_by_panel(self, days: int = 30) -> List[Dict[str, Any]]:
        limit = datetime.now(timezone.utc) - timedelta(days=days)
        async with self.get_session() as session:
            t_date = cast(UsageSnapshot.taken_at, Date).label('date')
            h_c = func.count(distinct(case((UsageSnapshot.hiddify_usage_gb > 0, UsageSnapshot.uuid_id), else_=None)))
            m_c = func.count(distinct(case((UsageSnapshot.marzban_usage_gb > 0, UsageSnapshot.uuid_id), else_=None)))
            stmt = select(t_date, h_c.label('hiddify_users'), m_c.label('marzban_users')).where(UsageSnapshot.taken_at >= limit).group_by(t_date).order_by(t_date)
            res = await session.execute(stmt)
            return [dict(row._mapping) for row in res.all()]

    async def get_total_usage_in_last_n_days(self, days: int) -> float:
        limit = datetime.now(timezone.utc) - timedelta(days=days)
        async with self.get_session() as session:
            subq = select(
                (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h'),
                (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m')
            ).where(UsageSnapshot.taken_at >= limit).group_by(UsageSnapshot.uuid_id).subquery()
            stmt = select(func.sum(subq.c.h + subq.c.m))
            return (await session.execute(stmt)).scalar_one() or 0.0

    async def get_night_usage_stats_in_last_n_days(self, uuid_id: int, days: int) -> dict:
        limit = datetime.now(timezone.utc) - timedelta(days=days)
        tehran_tz = pytz.timezone("Asia/Tehran")
        async with self.get_session() as session:
            stmt = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at >= limit)).order_by(UsageSnapshot.taken_at)
            snaps = (await session.execute(stmt)).scalars().all()
            
            stmt_prev = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < limit)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            prev = (await session.execute(stmt_prev)).scalar_one_or_none()
            
            last_h = prev.hiddify_usage_gb if prev else 0.0
            last_m = prev.marzban_usage_gb if prev else 0.0
            total, night = 0.0, 0.0

            for s in snaps:
                diff = self._calculate_diff(last_h, s.hiddify_usage_gb or 0) + self._calculate_diff(last_m, s.marzban_usage_gb or 0)
                total += diff
                loc_time = pytz.utc.localize(s.taken_at).astimezone(tehran_tz) if s.taken_at.tzinfo is None else s.taken_at.astimezone(tehran_tz)
                if 0 <= loc_time.hour < 6: night += diff
                last_h, last_m = s.hiddify_usage_gb or 0, s.marzban_usage_gb or 0
            return {'total': total, 'night': night}

    async def get_weekly_top_consumers_report(self) -> Dict[str, Any]:
        """گزارش هفتگی پرمصرف‌ترین‌ها."""
        tehran_tz = pytz.timezone("Asia/Tehran")
        async with self.get_session() as session:
            # 1. آخرین تاریخ اسنپ‌شات
            last_date_res = await session.execute(select(func.max(UsageSnapshot.taken_at)))
            last_taken = last_date_res.scalar_one_or_none()
            if not last_taken: return {'top_10_overall': [], 'top_daily': {}}
            
            report_base_date = pytz.utc.localize(last_taken).astimezone(tehran_tz).date() if last_taken.tzinfo is None else last_taken.astimezone(tehran_tz).date()

            # 2. دریافت کاربران فعال
            active_uuids = (await session.execute(select(UserUUID).where(UserUUID.is_active == True))).scalars().all()
            uuid_ids = [u.id for u in active_uuids]
            
            if not uuid_ids: return {'top_10_overall': [], 'top_daily': {}}

            weekly_data = {}
            daily_winners = []

            # 3. محاسبه ۷ روزه
            for i in range(7):
                t_date = report_base_date - timedelta(days=i)
                d_start = tehran_tz.localize(datetime(t_date.year, t_date.month, t_date.day)).astimezone(pytz.utc).replace(tzinfo=None)
                d_end = d_start + timedelta(days=1)

                # Bulk Fetch برای این روز
                base_q = select(UsageSnapshot).distinct(UsageSnapshot.uuid_id).where(and_(UsageSnapshot.uuid_id.in_(uuid_ids), UsageSnapshot.taken_at < d_start)).order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
                base_map = {r.uuid_id: r for r in (await session.execute(base_q)).scalars().all()}
                
                end_q = select(UsageSnapshot).distinct(UsageSnapshot.uuid_id).where(and_(UsageSnapshot.uuid_id.in_(uuid_ids), UsageSnapshot.taken_at < d_end)).order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
                end_map = {r.uuid_id: r for r in (await session.execute(end_q)).scalars().all()}

                top_day = {'name': None, 'usage': 0.0}

                for u in active_uuids:
                    b, e = base_map.get(u.id), end_map.get(u.id)
                    if not e: continue
                    
                    h_s, m_s = (b.hiddify_usage_gb, b.marzban_usage_gb) if b else (0.0, 0.0)
                    h_e, m_e = (e.hiddify_usage_gb or 0.0, e.marzban_usage_gb or 0.0)
                    
                    usage = self._calculate_diff(h_s, h_e) + self._calculate_diff(m_s, m_e)
                    
                    if usage > 0.001:
                        k = u.user_id
                        if k not in weekly_data: weekly_data[k] = {'name': u.name or f"User {u.user_id}", 'total_usage': 0.0}
                        weekly_data[k]['total_usage'] += usage
                        
                        if usage > top_day['usage']:
                            top_day = {'name': u.name or f"User {u.user_id}", 'usage': usage}
                
                if top_day['name']:
                    daily_winners.append({'date': t_date, 'name': top_day['name'], 'usage': top_day['usage']})

            sorted_users = sorted(weekly_data.values(), key=lambda x: x['total_usage'], reverse=True)[:20]
            daily_dict = {(w['date'].weekday() + 2) % 7: w for w in daily_winners}
            
            return {'top_20_overall': sorted_users, 'top_daily': daily_dict}

    async def get_previous_week_usage(self, uuid_id: int) -> float:
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_jalali = jdatetime.datetime.now(tz=tehran_tz)
        # شروع هفته جاری (شنبه)
        curr_week_start = (datetime.now(tehran_tz) - timedelta(days=now_jalali.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).replace(tzinfo=None)
        prev_week_start = curr_week_start - timedelta(days=7)
        
        async with self.get_session() as session:
            # Baseline شروع هفته قبل
            q_start = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < prev_week_start)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            b = (await session.execute(q_start)).scalar_one_or_none()
            
            # End پایان هفته قبل (یا شروع هفته جاری)
            q_end = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < curr_week_start)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            e = (await session.execute(q_end)).scalar_one_or_none()
            
            if not e: return 0.0
            
            h_s, m_s = (b.hiddify_usage_gb, b.marzban_usage_gb) if b else (0.0, 0.0)
            return self._calculate_diff(h_s, e.hiddify_usage_gb or 0) + self._calculate_diff(m_s, e.marzban_usage_gb or 0)

    async def get_user_weekly_total_usage(self, user_id: int) -> float:
        week_start = self.get_week_start_utc()
        async with self.get_session() as session:
            # گرفتن همه UUIDهای کاربر
            uuids = (await session.execute(select(UserUUID.id).where(UserUUID.user_id == user_id))).scalars().all()
            if not uuids: return 0.0
            
            total = 0.0
            for uid in uuids:
                q_b = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uid, UsageSnapshot.taken_at < week_start)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
                b = (await session.execute(q_b)).scalar_one_or_none()
                
                q_e = select(UsageSnapshot).where(UsageSnapshot.uuid_id == uid).order_by(desc(UsageSnapshot.taken_at)).limit(1)
                e = (await session.execute(q_e)).scalar_one_or_none()
                
                if e:
                    h_s, m_s = (b.hiddify_usage_gb, b.marzban_usage_gb) if b else (0.0, 0.0)
                    total += self._calculate_diff(h_s, e.hiddify_usage_gb or 0) + self._calculate_diff(m_s, e.marzban_usage_gb or 0)
            return total

    async def get_all_users_weekly_usage(self) -> list[float]:
        """لیست مصرف هفتگی تمام کاربران (برای نمودارهای توزیع)."""
        # برای سادگی و پرفورمنس، از get_total_usage_in_last_n_days استفاده می‌کنیم که مشابه است
        week_start = self.get_week_start_utc()
        async with self.get_session() as session:
            subq = select(
                UsageSnapshot.uuid_id,
                (func.max(UsageSnapshot.hiddify_usage_gb) - func.min(UsageSnapshot.hiddify_usage_gb)).label('h'),
                (func.max(UsageSnapshot.marzban_usage_gb) - func.min(UsageSnapshot.marzban_usage_gb)).label('m')
            ).where(UsageSnapshot.taken_at >= week_start).group_by(UsageSnapshot.uuid_id).subquery()
            
            stmt = select(func.sum(subq.c.h + subq.c.m)).join(UserUUID, subq.c.uuid_id == UserUUID.id).group_by(UserUUID.user_id)
            res = await session.execute(stmt)
            return [r for r in res.scalars().all()]

    async def get_weekly_usage_by_time_of_day(self, uuid_id: int) -> Dict[str, float]:
        return await self._get_usage_by_time_of_day(uuid_id, days=7)

    async def get_monthly_usage_by_time_of_day(self, uuid_id: int) -> Dict[str, float]:
        return await self._get_usage_by_time_of_day(uuid_id, days=30)

    async def _get_usage_by_time_of_day(self, uuid_id: int, days: int) -> Dict[str, float]:
        """متد کمکی داخلی برای محاسبه مصرف بر اساس زمان روز."""
        limit = datetime.now(timezone.utc) - timedelta(days=days)
        tehran_tz = pytz.timezone("Asia/Tehran")
        slots = {'morning': (6, 12), 'afternoon': (12, 18), 'evening': (18, 24), 'night': (0, 6)}
        stats = {k: 0.0 for k in slots}

        async with self.get_session() as session:
            snaps = (await session.execute(select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at >= limit)).order_by(UsageSnapshot.taken_at))).scalars().all()
            
            prev_q = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < limit)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            prev = (await session.execute(prev_q)).scalar_one_or_none()
            
            l_h, l_m = (prev.hiddify_usage_gb, prev.marzban_usage_gb) if prev else (0.0, 0.0)

            for s in snaps:
                diff = self._calculate_diff(l_h, s.hiddify_usage_gb or 0) + self._calculate_diff(l_m, s.marzban_usage_gb or 0)
                if diff > 0:
                    t = pytz.utc.localize(s.taken_at).astimezone(tehran_tz) if s.taken_at.tzinfo is None else s.taken_at.astimezone(tehran_tz)
                    h = t.hour
                    for k, v in slots.items():
                        if v[0] <= h < v[1]:
                            stats[k] += diff
                            break
                l_h, l_m = s.hiddify_usage_gb or 0, s.marzban_usage_gb or 0
        return stats

    async def get_user_total_usage_in_last_n_days(self, uuid_id: int, days: int) -> float:
        return await self.get_total_usage_in_last_n_days(days) # (Simplified logic reused)

    async def get_previous_day_total_usage(self) -> float:
        summary = await self.get_daily_usage_summary()
        # برگرداندن روز ماقبل آخر (دیروز)
        return summary[-2]['total_usage'] if len(summary) >= 2 else 0.0

    async def count_all_active_users(self) -> int:
        async with self.get_session() as session:
            return (await session.execute(select(func.count(UserUUID.id)).where(UserUUID.is_active == True))).scalar_one()

    async def get_user_monthly_usage_history_by_panel(self, uuid_id: int) -> list:
        # مشابه هفتگی اما ۳۰ روز
        return await self.get_user_daily_usage_history_by_panel(uuid_id, days=30)

    async def get_previous_month_usage(self, uuid_id: int) -> float:
        # محاسبه دقیق برای ماه شمسی قبل
        tehran_tz = pytz.timezone("Asia/Tehran")
        now = jdatetime.datetime.now(tz=tehran_tz)
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0).togregorian().astimezone(pytz.utc).replace(tzinfo=None)
        # شروع ماه قبل:
        last_month_date = now - timedelta(days=20) # رفتن به ماه قبل حدودی
        last_month_start_shamsi = last_month_date.replace(day=1, hour=0, minute=0, second=0)
        start_utc = last_month_start_shamsi.togregorian().astimezone(pytz.utc).replace(tzinfo=None)
        
        async with self.get_session() as session:
            q_b = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < start_utc)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            b = (await session.execute(q_b)).scalar_one_or_none()
            
            q_e = select(UsageSnapshot).where(and_(UsageSnapshot.uuid_id == uuid_id, UsageSnapshot.taken_at < this_month_start)).order_by(desc(UsageSnapshot.taken_at)).limit(1)
            e = (await session.execute(q_e)).scalar_one_or_none()
            
            if not e: return 0.0
            h_s, m_s = (b.hiddify_usage_gb, b.marzban_usage_gb) if b else (0.0, 0.0)
            return self._calculate_diff(h_s, e.hiddify_usage_gb or 0) + self._calculate_diff(m_s, e.marzban_usage_gb or 0)

    async def count_recently_active_users(self, all_users_data: list, minutes: int = 15) -> dict:
        """شمارش کاربران آنلاین بر اساس دیتای زنده پنل."""
        results = {'hiddify': 0, 'marzban_fr': 0, 'marzban_tr': 0, 'marzban_us': 0}
        time_limit = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        # استخراج UUID های آنلاین برای چک کردن دسترسی پنل
        active_uuid_strs = []
        for user in all_users_data:
            last_online = user.get('last_online')
            if user.get('is_active') and last_online:
                # تبدیل timestamp یا isoformat
                if isinstance(last_online, (int, float)):
                    lo_dt = datetime.fromtimestamp(last_online, tz=timezone.utc)
                elif isinstance(last_online, str):
                    try: lo_dt = datetime.fromisoformat(last_online.replace('Z', '+00:00'))
                    except: continue
                else: lo_dt = last_online

                if lo_dt >= time_limit:
                    active_uuid_strs.append(user.get('uuid'))
        
        if not active_uuid_strs: return results

        # فعلاً تعداد کل را در hiddify می‌ریزیم چون تفکیک دقیق بدون کوئری پیچیده ممکن نیست
        results['hiddify'] = len(active_uuid_strs)
        return results