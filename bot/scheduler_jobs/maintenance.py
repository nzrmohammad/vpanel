# bot/scheduler_jobs/maintenance.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
import pytz
from sqlalchemy import select, delete

# ایمپورت‌های پروژه
from bot import combined_handler
from bot.database import db
from bot.db.base import UserUUID, AdminLog, SentReport, UsageSnapshot
from bot.formatters import admin_formatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. همگام‌سازی کاربران (SYNC USERS)
# ---------------------------------------------------------
async def sync_users_with_panels(bot):
    """
    اطلاعات ترافیک و انقضای کاربران را از پنل‌ها گرفته و در دیتابیس لوکال ذخیره می‌کند.
    """
    start_time = time.time()
    logger.info("SYNCER: Starting panel data synchronization cycle.")
    loop = asyncio.get_running_loop()

    try:
        # 1. دریافت اطلاعات از API پنل‌ها (عملیات سنگین شبکه -> اجرا در Executor)
        # این کار باعث می‌شود هسته اصلی ربات بلاک نشود
        all_users_from_api = await loop.run_in_executor(None, combined_handler.get_all_users_combined)

        if not all_users_from_api:
            logger.warning("SYNCER: Fetched user list is empty. Skipping sync.")
            return

        # تبدیل لیست به دیکشنری برای جستجوی سریع
        api_users_map = {u.get('uuid'): u for u in all_users_from_api if u.get('uuid')}

        # 2. آپدیت دیتابیس
        async with db.get_session() as session:
            # دریافت تمام UUID های موجود در دیتابیس
            stmt = select(UserUUID)
            result = await session.execute(stmt)
            db_uuids = result.scalars().all()
            
            updates_count = 0
            
            for uuid_obj in db_uuids:
                api_data = api_users_map.get(str(uuid_obj.uuid))
                
                if api_data:
                    # بررسی تغییرات (برای کاهش تعداد رایدهای دیتابیس)
                    usage = api_data.get('current_usage_GB', 0)
                    limit = api_data.get('usage_limit_GB', 0)
                    
                    # آپدیت فیلدها
                    uuid_obj.traffic_used = usage
                    # اگر بخواهیم لیمیت را هم از پنل سینک کنیم:
                    # uuid_obj.traffic_limit = limit 
                    
                    # آپدیت وضعیت انقضا
                    # نکته: بسته به منطق شما ممکن است بخواهید expire_date را هم آپدیت کنید
                    
                    updates_count += 1
            
            if updates_count > 0:
                await session.commit()
                logger.info(f"SYNCER: Updated {updates_count} users in database.")
            else:
                logger.info("SYNCER: No changes detected.")

    except Exception as e:
        logger.error(f"SYNCER: Critical error during sync: {e}", exc_info=True)
    
    duration = time.time() - start_time
    logger.info(f"SYNCER: Finished in {duration:.2f} seconds.")


# ---------------------------------------------------------
# 2. پاکسازی لاگ‌های قدیمی (CLEANUP)
# ---------------------------------------------------------
async def cleanup_old_logs():
    """
    حذف لاگ‌های ادمین و گزارش‌های قدیمی برای جلوگیری از سنگین شدن دیتابیس
    """
    logger.info("MAINTENANCE: Cleaning up old logs...")
    try:
        # حذف لاگ‌های ادمین قدیمی‌تر از 30 روز
        async with db.get_session() as session:
            month_ago = datetime.now() - timedelta(days=30)
            stmt = delete(AdminLog).where(AdminLog.created_at < month_ago)
            res = await session.execute(stmt)
            deleted_rows = res.rowcount
            await session.commit()
            
            logger.info(f"MAINTENANCE: Deleted {deleted_rows} old admin logs.")

        # حذف گزارش‌های ارسالی قدیمی (اگر جدول SentReport دارید)
        # async with db.get_session() as session:
        #     stmt = delete(SentReport).where(SentReport.sent_at < month_ago)
        #     await session.execute(stmt)
        #     await session.commit()

    except Exception as e:
        logger.error(f"MAINTENANCE: Error in cleanup_old_logs: {e}")


# ---------------------------------------------------------
# 3. اسنپ‌شات ساعتی (SNAPSHOTS)
# ---------------------------------------------------------
async def hourly_snapshots(bot):
    """
    ذخیره وضعیت مصرف کل کاربران برای نمودارها
    """
    logger.info("SNAPSHOT: Taking hourly usage snapshot...")
    loop = asyncio.get_running_loop()
    
    try:
        # دریافت اطلاعات تازه
        all_users = await loop.run_in_executor(None, combined_handler.get_all_users_combined)
        if not all_users: return

        # جمع‌بندی مصرف‌ها بر اساس نوع پنل (اختیاری)
        # در اینجا ساده‌سازی شده و مصرف کل هر کاربر ذخیره می‌شود
        
        async with db.get_session() as session:
            # دریافت نگاشت UUID به ID جدول
            stmt = select(UserUUID.id, UserUUID.uuid)
            result = await session.execute(stmt)
            uuid_map = {str(row.uuid): row.id for row in result.all()}
            
            snapshots = []
            for u_data in all_users:
                uuid_str = u_data.get('uuid')
                db_id = uuid_map.get(uuid_str)
                
                if db_id:
                    # استخراج مصرف تفکیک شده (اگر در combined_handler موجود باشد)
                    # فرض بر این است که breakdown داریم، اگر نه کل مصرف را می‌گذاریم
                    h_usage = 0.0
                    m_usage = 0.0
                    
                    breakdown = u_data.get('breakdown', {})
                    if breakdown:
                        for p_name, p_info in breakdown.items():
                            p_type = p_info.get('type', 'unknown')
                            u_val = p_info.get('data', {}).get('current_usage_GB', 0)
                            
                            if 'hiddify' in p_type: h_usage += u_val
                            elif 'marzban' in p_type: m_usage += u_val
                            else: h_usage += u_val # پیش‌فرض
                    else:
                        # حالت ساده
                        h_usage = u_data.get('current_usage_GB', 0)

                    snapshots.append(UsageSnapshot(
                        user_uuid_id=db_id,
                        hiddify_usage=h_usage,
                        marzban_usage=m_usage,
                        created_at=datetime.now()
                    ))
            
            if snapshots:
                session.add_all(snapshots)
                await session.commit()
                logger.info(f"SNAPSHOT: Saved {len(snapshots)} usage snapshots.")

    except Exception as e:
        logger.error(f"SNAPSHOT: Error: {e}")

# ---------------------------------------------------------
# 4. آپدیت پیام آنلاین‌ها (LIVE ONLINE LIST)
# ---------------------------------------------------------
async def update_online_reports(bot):
    """
    آپدیت پیام لیست آنلاین‌ها در تلگرام
    """
    # این تابع نیاز دارد که جدول ScheduledMessage داشته باشید.
    # اگر ندارید، می‌توانید بدنه آن را pass کنید.
    try:
        # این متد فرضی است، باید در DatabaseManager پیاده‌سازی شود
        if not hasattr(db, 'get_scheduled_messages'):
            return

        messages = await db.get_scheduled_messages('online_users_report')
        if not messages: return

        loop = asyncio.get_running_loop()
        all_users = await loop.run_in_executor(None, combined_handler.get_all_users_combined)
        
        # فیلتر آنلاین‌ها (زیر ۳ دقیقه)
        now = datetime.now(pytz.utc)
        online_list = []
        for u in all_users:
            last_online = u.get('last_online') or u.get('online_at')
            if last_online:
                # تبدیل رشته به زمان اگر لازم باشد
                # ...
                # فرض بر این است که last_online شیء datetime است یا هندل شده
                pass
                # online_list.append(u) (لاجیک دقیق بسته به فرمت خروجی combined)

        # اگر لیست آنلاین‌ها را دارید:
        # text = admin_formatter.system.online_users_list(online_list)
        # await bot.edit_message_text(...)
        pass 

    except Exception as e:
        logger.error(f"ONLINE_REPORT: {e}")