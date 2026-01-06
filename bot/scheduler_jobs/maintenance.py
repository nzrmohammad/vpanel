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
    جاب زمان‌بندی شده: دریافت اطلاعات تمام کاربران و ثبت اسنپ‌شات مصرف.
    """
    logger.info("SNAPSHOT: Starting hourly usage snapshot process...")
    loop = asyncio.get_running_loop()

    try:
        # ۱. دریافت لیست تجمیعی کاربران (شامل breakdown پنل‌ها)
        # اجرای تابع سنگین در Executor برای جلوگیری از بلاک شدن ربات
        all_users = await loop.run_in_executor(None, combined_handler.get_all_users_combined)

        if not all_users:
            logger.warning("SNAPSHOT: No user data fetched from panels.")
            return

        snapshot_count = 0
        
        # ۲. دریافت مپ UUIDهای دیتابیس برای پیدا کردن ID عددی
        # (چون در جدول usage_snapshots باید ID عددی ذخیره کنیم نه رشته UUID)
        async with db.get_session() as session:
            # گرفتن همه UUIDهای فعال
            stmt = select(UserUUID)
            user_uuids_db = (await session.execute(stmt)).scalars().all()
            # مپ کردن رشته uuid به آبجکت دیتابیس: {'uuid-string': user_obj}
            db_uuid_map = {u.uuid: u for u in user_uuids_db}

        # ۳. پردازش لیست کاربران و استخراج مصرف هر پنل
        for user_data in all_users:
            uuid_str = user_data.get('uuid')
            
            # اگر کاربر در دیتابیس ما نباشد، اسنپ‌شات نمی‌گیریم
            if not uuid_str or uuid_str not in db_uuid_map:
                continue

            user_db_id = db_uuid_map[uuid_str].id
            breakdown = user_data.get('breakdown', {})

            # استخراج مصرف هر پنل از breakdown
            # نکته: combined_handler دیتا را با ساختار {'panel_name': {'type': 'hiddify', 'data': {...}}} می‌دهد
            
            h_usage = 0.0
            m_usage = 0.0
            r_usage = 0.0
            p_usage = 0.0

            for p_info in breakdown.values():
                p_type = p_info.get('type')
                # فرض بر این است که current_usage_GB در دیتا موجود است
                usage_val = p_info.get('data', {}).get('current_usage_GB', 0.0)

                if p_type == 'hiddify':
                    h_usage += usage_val
                elif p_type == 'marzban':
                    m_usage += usage_val
                elif p_type == 'remnawave':
                    r_usage += usage_val
                elif p_type == 'pasarguard':
                    p_usage += usage_val

            # ۴. ثبت در دیتابیس
            await db.add_usage_snapshot(
                uuid_id=user_db_id,
                hiddify_usage=h_usage,
                marzban_usage=m_usage,
                remnawave_usage=r_usage,
                pasarguard_usage=p_usage
            )
            snapshot_count += 1

        logger.info(f"SNAPSHOT: Successfully saved snapshots for {snapshot_count} users.")

    except Exception as e:
        logger.error(f"SNAPSHOT: Critical error in hourly snapshot job: {e}", exc_info=True)

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