# bot/db/achievement.py

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import pytz

from sqlalchemy import select, update, delete, func, desc, and_
from sqlalchemy.exc import IntegrityError

# مدل‌ها را از فایل base وارد می‌کنیم
from .base import (
    User, UserAchievement, AchievementShopLog, WeeklyChampionLog,
    UserUUID, UsageSnapshot,
    BirthdayGiftLog, AnniversaryGiftLog, DatabaseManager
)

logger = logging.getLogger(__name__)

class AchievementDB:
    """
    کلاسی برای مدیریت دستاوردها، امتیازات، سیستم معرفی و قرعه‌کشی.
    این کلاس به عنوان Mixin طراحی شده تا متدهای آن روی کلاس اصلی DatabaseManager سوار شوند.
    فرض بر این است که `self` دارای متد `get_session` است (که در DatabaseManager وجود دارد).
    """

    async def add_achievement(self, user_id: int, badge_code: str) -> bool:
        """یک دستاورد جدید برای کاربر ثبت می‌کند."""
        async with self.get_session() as session:
            try:
                new_achievement = UserAchievement(user_id=user_id, badge_code=badge_code)
                session.add(new_achievement)
                await session.commit()
                return True
            except IntegrityError:
                # اگر کاربر قبلاً این نشان را داشته باشد (UNIQUE constraint)
                logger.info(f"User {user_id} already has achievement {badge_code}.")
                return False

    async def get_user_achievements(self, user_id: int) -> List[str]:
        """لیست کدهای تمام نشان‌های یک کاربر را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(UserAchievement.badge_code).where(UserAchievement.user_id == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def add_achievement_points(self, user_id: int, points: int):
        """امتیاز به حساب دستاوردهای یک کاربر اضافه می‌کند."""
        async with self.get_session() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(achievement_points=User.achievement_points + points)
            )
            await session.execute(stmt)
        # پاک کردن کش (در صورت وجود متد در کلاس اصلی)
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def spend_achievement_points(self, user_id: int, points: int) -> bool:
        """امتیاز را از حساب کاربر کم می‌کند و موفقیت عملیات را برمی‌گرداند."""
        async with self.get_session() as session:
            # ابتدا موجودی را چک می‌کنیم
            stmt = select(User.achievement_points).where(User.user_id == user_id)
            result = await session.execute(stmt)
            current_points = result.scalar_one_or_none() or 0

            if current_points >= points:
                update_stmt = (
                    update(User)
                    .where(User.user_id == user_id)
                    .values(achievement_points=User.achievement_points - points)
                )
                await session.execute(update_stmt)
                
                if hasattr(self, 'clear_user_cache'):
                    self.clear_user_cache(user_id)
                return True
            return False

    async def log_shop_purchase(self, user_id: int, item_key: str, cost: int):
        """یک خرید از فروشگاه دستاوردها را ثبت می‌کند."""
        async with self.get_session() as session:
            log_entry = AchievementShopLog(user_id=user_id, item_key=item_key, cost=cost)
            session.add(log_entry)

    async def get_achievement_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """لیستی از کاربران برتر بر اساس امتیاز دستاوردها."""
        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name, User.achievement_points)
                .where(User.achievement_points > 0)
                .order_by(desc(User.achievement_points))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [
                {"user_id": r.user_id, "first_name": r.first_name, "achievement_points": r.achievement_points}
                for r in result.all()
            ]

    async def get_all_users_by_points(self) -> List[Dict[str, Any]]:
        """تمام کاربران امتیازدار به همراه لیست نشان‌هایشان."""
        async with self.get_session() as session:
            badges_agg = func.string_agg(UserAchievement.badge_code, ',').label('badges')
            
            stmt = (
                select(
                    User.user_id,
                    User.first_name,
                    User.achievement_points,
                    badges_agg
                )
                .outerjoin(UserAchievement, User.user_id == UserAchievement.user_id)
                .where(User.achievement_points > 0)
                .group_by(User.user_id)
                .order_by(desc(User.achievement_points))
            )
            
            result = await session.execute(stmt)
            return [
                {
                    "user_id": r.user_id,
                    "first_name": r.first_name,
                    "achievement_points": r.achievement_points,
                    "badges": r.badges
                }
                for r in result.all()
            ]

    async def reset_all_achievement_points(self) -> int:
        """امتیاز تمام کاربران را صفر می‌کند."""
        async with self.get_session() as session:
            stmt = update(User).values(achievement_points=0)
            result = await session.execute(stmt)
            
            if hasattr(self, '_user_cache'):
                self._user_cache.clear()
                
            return result.rowcount

    async def delete_all_achievements(self) -> int:
        """تمام رکوردهای دستاوردهای کسب شده را حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(UserAchievement)
            result = await session.execute(stmt)
            return result.rowcount

    async def get_user_achievements_in_range(self, user_id: int, start_date: datetime) -> List[Dict[str, Any]]:
        """دستاوردهای کاربر در یک بازه زمانی خاص."""
        async with self.get_session() as session:
            stmt = (
                select(UserAchievement.badge_code, UserAchievement.awarded_at)
                .where(
                    and_(
                        UserAchievement.user_id == user_id,
                        UserAchievement.awarded_at >= start_date
                    )
                )
                .order_by(desc(UserAchievement.awarded_at))
            )
            result = await session.execute(stmt)
            return [
                {"badge_code": r.badge_code, "awarded_at": r.awarded_at}
                for r in result.all()
            ]

    async def get_daily_achievements(self) -> List[Dict[str, Any]]:
        """کاربرانی که امروز دستاوردی کسب کرده‌اند."""
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_tehran = datetime.now(tehran_tz)
        today_midnight = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
        today_midnight_utc = today_midnight.astimezone(pytz.utc).replace(tzinfo=None)

        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name, UserAchievement.badge_code)
                .join(User, UserAchievement.user_id == User.user_id)
                .where(UserAchievement.awarded_at >= today_midnight_utc)
                .order_by(User.user_id)
            )
            result = await session.execute(stmt)
            return [
                {"user_id": r.user_id, "first_name": r.first_name, "badge_code": r.badge_code}
                for r in result.all()
            ]

    # --- توابع مربوط به قهرمانی هفتگی و قرعه‌کشی ---

    async def log_weekly_champion_win(self, user_id: int):
        """ثبت قهرمانی هفتگی."""
        async with self.get_session() as session:
            log = WeeklyChampionLog(user_id=user_id, win_date=datetime.now().date())
            session.add(log)

    async def count_consecutive_weekly_wins(self, user_id: int) -> int:
        """محاسبه تعداد بردهای متوالی هفتگی."""
        async with self.get_session() as session:
            stmt = (
                select(WeeklyChampionLog.win_date)
                .where(WeeklyChampionLog.user_id == user_id)
                .order_by(desc(WeeklyChampionLog.win_date))
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return 0

        consecutive_wins = 0
        last_win_date = None

        for win_date in rows:
            current_date = win_date
            
            if last_win_date is None:
                consecutive_wins = 1
            else:
                delta = (last_win_date - current_date).days
                if 6 <= delta <= 8:
                    consecutive_wins += 1
                else:
                    break
            last_win_date = current_date
            
        return consecutive_wins

    async def get_lottery_participants(self) -> List[int]:
        """لیست کاربرانی که در ۳۰ روز اخیر مصرف داشته‌اند (واجد شرایط قرعه‌کشی)."""
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        async with self.get_session() as session:
            stmt = (
                select(User.user_id)
                .join(UserUUID, User.user_id == UserUUID.user_id)
                .join(UsageSnapshot, UserUUID.id == UsageSnapshot.uuid_id)
                .where(UsageSnapshot.taken_at >= thirty_days_ago)
                .distinct()
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_lottery_participant_details(self) -> List[Dict[str, Any]]:
        """لیست کاربران دارای نشان 'خوش‌شانس'."""
        async with self.get_session() as session:
            stmt = (
                select(
                    User.user_id,
                    User.first_name,
                    func.count(UserAchievement.id).label('lucky_badge_count')
                )
                .join(UserAchievement, User.user_id == UserAchievement.user_id)
                .where(UserAchievement.badge_code == 'lucky_one')
                .group_by(User.user_id)
                .having(func.count(UserAchievement.id) > 0)
                .order_by(desc('lucky_badge_count'))
            )
            result = await session.execute(stmt)
            return [
                {
                    "user_id": r.user_id,
                    "first_name": r.first_name,
                    "lucky_badge_count": r.lucky_badge_count
                }
                for r in result.all()
            ]

    async def clear_lottery_tickets(self) -> int:
        """
        تمام بلیط‌های قرعه‌کشی را حذف می‌کند.
        خروجی: تعداد بلیط‌های حذف شده.
        """
        # نکته مهم: ابتدا مطمئن شوید LotteryTicket را در بالای فایل ایمپورت کرده‌اید
        # from .base import LotteryTicket
        
        async with self.get_session() as session:
            pass

    # --- توابع مربوط به درخواست نشان ---
    async def check_if_gift_given(self, user_id: int, gift_type: str, year: int) -> bool:
        """بررسی دریافت هدیه در سال جاری."""
        # نگاشت رشته به کلاس مدل
        model_map = {
            'birthday': BirthdayGiftLog,
            'anniversary_1': AnniversaryGiftLog,
            'anniversary_2': AnniversaryGiftLog, # فرض بر استفاده از جدول مشابه
            'anniversary_3': AnniversaryGiftLog,
        }
        
        ModelClass = model_map.get(gift_type)
        if not ModelClass:
            return False

        async with self.get_session() as session:
            stmt = select(ModelClass).where(
                and_(ModelClass.user_id == user_id, ModelClass.gift_year == year)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def log_gift_given(self, user_id: int, gift_type: str, year: int):
        """ثبت اهدای هدیه."""
        model_map = {
            'birthday': BirthdayGiftLog,
            'anniversary_1': AnniversaryGiftLog,
            'anniversary_2': AnniversaryGiftLog,
            'anniversary_3': AnniversaryGiftLog,
        }
        
        ModelClass = model_map.get(gift_type)
        if not ModelClass:
            return

        async with self.get_session() as session:
            # ابتدا چک می‌کنیم تکراری نباشد
            exists_stmt = select(ModelClass).where(
                and_(ModelClass.user_id == user_id, ModelClass.gift_year == year)
            )
            exists = await session.execute(exists_stmt)
            if not exists.scalar_one_or_none():
                new_log = ModelClass(user_id=user_id, gift_year=year)
                session.add(new_log)