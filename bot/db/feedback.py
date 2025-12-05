# bot/db/feedback.py

import logging
from typing import Any, Dict, List
from sqlalchemy import select, update, func, desc

# وارد کردن مدل‌ها از فایل base
from .base import UserFeedback, User

logger = logging.getLogger(__name__)

class FeedbackDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به بازخورد کاربران.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    async def add_feedback_rating(self, user_id: int, rating: int) -> int:
        """
        امتیاز اولیه کاربر را ثبت می‌کند و شناسه رکورد را برمی‌گرداند.
        """
        async with self.get_session() as session:
            feedback = UserFeedback(user_id=user_id, rating=rating)
            session.add(feedback)
            await session.commit()
            # برای دریافت ID تولید شده (Auto Increment) باید آبجکت را رفرش کنیم
            await session.refresh(feedback)
            return feedback.id

    async def update_feedback_comment(self, feedback_id: int, comment: str):
        """
        نظر متنی کاربر را به رکورد بازخورد اضافه می‌کند.
        """
        async with self.get_session() as session:
            stmt = (
                update(UserFeedback)
                .where(UserFeedback.id == feedback_id)
                .values(comment=comment)
            )
            await session.execute(stmt)
            await session.commit()

    async def get_paginated_feedback(self, page: int, page_size: int = 10) -> List[Dict[str, Any]]:
        """
        بازخوردها را برای پنل ادمین به صورت صفحه‌بندی شده واکشی می‌کند.
        """
        offset = page * page_size
        
        async with self.get_session() as session:
            # کوئری Join بین جدول بازخورد و کاربران
            stmt = (
                select(UserFeedback, User)
                .outerjoin(User, UserFeedback.user_id == User.user_id)
                .order_by(desc(UserFeedback.created_at))
                .limit(page_size)
                .offset(offset)
            )
            result = await session.execute(stmt)
            
            feedback_list = []
            for feedback, user in result:
                # تبدیل نتیجه ORM به دیکشنری ساده برای استفاده در تمپلیت‌ها
                feedback_data = {
                    "id": feedback.id,
                    "rating": feedback.rating,
                    "comment": feedback.comment,
                    "created_at": feedback.created_at,
                    # هندل کردن حالتی که کاربر حذف شده باشد (Left Join)
                    "user_id": user.user_id if user else None,
                    "first_name": user.first_name if user else "Unknown User"
                }
                feedback_list.append(feedback_data)
                
            return feedback_list

    async def get_feedback_count(self) -> int:
        """
        تعداد کل بازخوردهای ثبت شده را برمی‌گرداند.
        """
        async with self.get_session() as session:
            stmt = select(func.count(UserFeedback.id))
            result = await session.execute(stmt)
            # متد scalar_one مقدار تکی (تعداد) را برمی‌گرداند
            return result.scalar_one() or 0