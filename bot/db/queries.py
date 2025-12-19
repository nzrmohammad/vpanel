# bot/db/queries.py
from sqlalchemy import select, func, or_, and_, String
from datetime import datetime, timedelta
from bot.db.base import User, UserUUID, UsageSnapshot

def get_base_panel_query(panel_id: int):
    """کوئری پایه برای کاربرانی که به یک پنل دسترسی دارند."""
    return select(User).join(UserUUID).join(UserUUID.allowed_panels).where(UserUUID.allowed_panels.any(id=panel_id))


def get_online_users_query(panel_id: int, online_identifiers: list):
    """جستجوی کاربران بر اساس لیست شناسه‌های آنلاین."""
    # تبدیل شناسه‌ها به رشته برای اطمینان از مطابقت
    ids = [str(i) for i in online_identifiers]
    
    return select(User).distinct().join(UserUUID).where(
        and_(
            UserUUID.allowed_panels.any(id=panel_id),
            or_(
                UserUUID.uuid.cast(String).in_(ids), # چک کردن UUID
                User.username.in_(ids)               # چک کردن Username
            )
        )
    )

def get_active_users_query(panel_id: int):
    """کوئری کاربران فعال در ۲۴ ساعت گذشته."""
    yesterday = datetime.now() - timedelta(days=1)
    query = get_base_panel_query(panel_id)
    return query.where(UserUUID.snapshots.any(UsageSnapshot.taken_at >= yesterday)).distinct()

def get_inactive_users_query(panel_id: int):
    """کوئری کاربران غیرفعال (بیش از ۷ روز)."""
    week_ago = datetime.now() - timedelta(days=7)
    query = get_base_panel_query(panel_id)
    return query.where(or_(UserUUID.updated_at < week_ago, UserUUID.updated_at.is_(None))).distinct()

def get_never_connected_query(panel_id: int):
    """کوئری کاربرانی که هرگز متصل نشده‌اند."""
    query = get_base_panel_query(panel_id)
    return query.where(UserUUID.first_connection_time.is_(None)).distinct()

def get_users_by_plan_query(plan_id: int = None):
    """کوئری فیلتر بر اساس پلن یا بدون پلن."""
    if plan_id == 0 or plan_id is None:
        return select(User).where(User.plan_id.is_(None))
    return select(User).where(User.plan_id == plan_id)