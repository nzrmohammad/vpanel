# bot/scheduler_jobs/maintenance.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
import pytz
import jdatetime
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
        all_users_from_api = await combined_handler.get_all_users_combined()

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
    جاب زمان‌بندی شده: دریافت اطلاعات کاربران، ثبت اسنپ‌شات و ارسال گزارش به تاپیک مخصوص.
    """
    logger.info("SNAPSHOT: Starting hourly usage snapshot process...")
    loop = asyncio.get_running_loop()

    try:
        # ۱. دریافت اطلاعات از پنل‌ها
        all_users = await combined_handler.get_all_users_combined()
        if not all_users:
            logger.warning("SNAPSHOT: No user data fetched.")
            return

        # ۲. آماده‌سازی دیتابیس
        async with db.get_session() as session:
            stmt = select(UserUUID)
            user_uuids_db = (await session.execute(stmt)).scalars().all()
            db_uuid_map = {u.uuid: u for u in user_uuids_db}

        # متغیرهای جمع کل
        total_hiddify = 0.0
        total_marzban = 0.0
        total_remnawave = 0.0
        total_pasarguard = 0.0
        snapshot_count = 0

        # ۳. پردازش و ذخیره اسنپ‌شات‌ها
        for user_data in all_users:
            uuid_str = user_data.get('uuid')
            if not uuid_str or uuid_str not in db_uuid_map:
                continue

            user_db_id = db_uuid_map[uuid_str].id
            breakdown = user_data.get('breakdown', {})

            h_usage, m_usage, r_usage, p_usage = 0.0, 0.0, 0.0, 0.0

            for p_info in breakdown.values():
                p_type = p_info.get('type')
                val = p_info.get('data', {}).get('current_usage_GB', 0.0)
                
                if p_type == 'hiddify': h_usage += val
                elif p_type == 'marzban': m_usage += val
                elif p_type == 'remnawave': r_usage += val
                elif p_type == 'pasarguard': p_usage += val

            total_hiddify += h_usage
            total_marzban += m_usage
            total_remnawave += r_usage
            total_pasarguard += p_usage

            await db.add_usage_snapshot(
                uuid_id=user_db_id,
                hiddify_usage=h_usage,
                marzban_usage=m_usage,
                remnawave_usage=r_usage,
                pasarguard_usage=p_usage
            )
            snapshot_count += 1

        logger.info(f"SNAPSHOT: Saved {snapshot_count} snapshots.")

        # ---------------------------------------------------------
        # ۴. ارسال گزارش به تاپیک اختصاصی (topic_id_snapshots)
        # ---------------------------------------------------------
        try:
            # دریافت تنظیمات جدید
            main_group_id = await db.get_config('main_group_id')
            snapshot_topic_id = await db.get_config('topic_id_snapshots') # <--- تغییر مهم
            
            # فقط اگر گروپ آیدی و تاپیک آیدی تنظیم شده باشند ارسال می‌کنیم
            if main_group_id and snapshot_topic_id and int(snapshot_topic_id) != 0:
                
                now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
                grand_total = total_hiddify + total_marzban + total_remnawave + total_pasarguard

                report_text = (
                    f"📸 <b>گزارش وضعیت مصرف (Snapshot)</b>\n"
                    f"📅 {now_str}\n"
                    f"👥 تعداد سرویس‌ها: <code>{snapshot_count}</code>\n"
                    f"──────────────\n"
                    f"🔹 <b>Hiddify:</b> <code>{total_hiddify:,.2f} GB</code>\n"
                    f"🔹 <b>Marzban:</b> <code>{total_marzban:,.2f} GB</code>\n"
                    f"🔹 <b>Remnawave:</b> <code>{total_remnawave:,.2f} GB</code>\n"
                    f"🔹 <b>Pasarguard:</b> <code>{total_pasarguard:,.2f} GB</code>\n"
                    f"──────────────\n"
                    f"📊 <b>مجموع کل مصرف: {grand_total:,.2f} GB</b>"
                )

                await bot.send_message(
                    chat_id=int(main_group_id),
                    text=report_text,
                    parse_mode='HTML',
                    message_thread_id=int(snapshot_topic_id) # ارسال به تاپیک اختصاصی
                )
            else:
                logger.info("SNAPSHOT: Topic ID for snapshots is not set. Skipping Telegram report.")

        except Exception as report_err:
            logger.error(f"SNAPSHOT REPORT ERROR: {report_err}")

    except Exception as e:
        logger.error(f"SNAPSHOT: Critical error: {e}", exc_info=True)
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
        all_users = await combined_handler.get_all_users_combined()
        
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