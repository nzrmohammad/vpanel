# bot/db/queries.py

from sqlalchemy import select, func, or_, and_, String
from datetime import datetime, timedelta
from async_lru import alru_cache

# ایمپورت مدل‌ها
from bot.db.base import User, UserUUID, UsageSnapshot, Plan, ServerCategory, SystemConfig
# ایمپورت نمونه دیتابیس برای اجرای کوئری‌ها
from bot.database import db

# ---------------------------------------------------------
# 1. Query Builders (کوئری‌سازها)
# این توابع فقط شیء کوئری را می‌سازند و اجرا نمی‌کنند
# ---------------------------------------------------------

def get_base_panel_query(panel_id: int):
    """کوئری پایه برای کاربرانی که به یک پنل دسترسی دارند."""
    return select(User).join(UserUUID).join(UserUUID.allowed_panels).where(UserUUID.allowed_panels.any(id=panel_id))

def get_online_users_query(panel_id: int, online_identifiers: list):
    """جستجوی کاربران بر اساس لیست شناسه‌های آنلاین."""
    ids = [str(i) for i in online_identifiers]
    return select(User).distinct().join(UserUUID).where(
        and_(
            UserUUID.allowed_panels.any(id=panel_id),
            or_(
                UserUUID.uuid.cast(String).in_(ids),
                User.username.in_(ids)
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

# ---------------------------------------------------------
# 2. Cached Data Fetchers (دریافت داده با کش)
# استفاده از async-lru برای کاهش فشار روی دیتابیس
# ---------------------------------------------------------

@alru_cache(maxsize=1000, ttl=300)  # کش تا ۵ دقیقه، حداکثر ۱۰۰۰ رکورد
async def get_user_cached(user_id: int):
    """
    دریافت اطلاعات کاربر به صورت کش شده.
    مناسب برای چک کردن وضعیت کاربر در میدل‌ورها یا هندلرها.
    """
    async with db.get_session() as session:
        # نکته: چون سشن بسته می‌شود، باید مطمئن باشید که ریلیشن‌های مورد نیاز
        # در مدل User به صورت lazy='selectin' تعریف شده باشند (که در کد شما هستند).
        user = await session.get(User, user_id)
        return user

@alru_cache(maxsize=50, ttl=3600)  # کش تا ۱ ساعت
async def get_plan_cached(plan_id: int):
    """دریافت اطلاعات یک پلن خاص با کش طولانی."""
    async with db.get_session() as session:
        return await session.get(Plan, plan_id)

@alru_cache(maxsize=1, ttl=600)  # کش تا ۱۰ دقیقه
async def get_system_config_cached(key: str):
    """دریافت یک تنظیم سیستم با کش."""
    async with db.get_session() as session:
        config = await session.get(SystemConfig, key)
        return config.value if config else None

# تابع کمکی برای پاک کردن کش یک کاربر خاص (مثلاً وقتی خرید می‌کند)
def invalidate_user_cache(user_id: int):
    """
    این تابع را باید در جاهایی که کاربر تغییر می‌کند (مثل تمدید سرویس) صدا بزنید.
    """
    # در نسخه‌های جدید async-lru امکان پاک کردن یک کلید خاص وجود دارد
    # اگر ارور داد، می‌توانید کل کش را با get_user_cached.cache_clear() پاک کنید
    try:
        get_user_cached.cache_invalidate(user_id)
    except AttributeError:
        # Fallback برای نسخه‌های قدیمی
        get_user_cached.cache_clear()