# bot/scheduler_jobs/reports.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
import pytz
import jdatetime
from telebot import apihelper, types

from bot import combined_handler
from bot.database import db
from bot.utils import escape_markdown
# تغییر مهم: استفاده از کلاس AdminFormatter به جای توابع تکی
from bot.formatters.admin import AdminFormatter
from bot.formatters.user import fmt_user_report
from bot.formatters.user import fmt_user_weekly_report
from bot.keyboards.user.main import UserMainMenu
from bot.config import ADMIN_IDS
from bot.language import get_string

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. NIGHTLY REPORT (گزارش شبانه)
# ---------------------------------------------------------
async def nightly_report(bot, target_user_id: int = None) -> None:
    """
    نسخه Async: گزارش شبانه را برای کاربران ارسال کرده و گزارش جامع را برای ادمین‌ها می‌فرستد.
    """
    tehran_tz = pytz.timezone("Asia/Tehran")
    now_gregorian = datetime.now(tehran_tz)
    loop = asyncio.get_running_loop()

    is_friday = jdatetime.datetime.fromgregorian(datetime=now_gregorian).weekday() == 6
    now_str = jdatetime.datetime.fromgregorian(datetime=now_gregorian).strftime("%Y/%m/%d - %H:%M")
    
    logger.info(f"SCHEDULER (Async): ----- Running nightly report at {now_str} -----")

    try:
        # دریافت اطلاعات از پنل‌ها (I/O سنگین - اجرا در ترد جداگانه)
        all_users_info_from_api = await loop.run_in_executor(None, combined_handler.get_all_users_combined)
        
        if not all_users_info_from_api:
            logger.warning("SCHEDULER: Could not fetch API user info. JOB STOPPED.")
            return

        user_info_map = {user['uuid']: user for user in all_users_info_from_api}
        
        # --- بخش ۱: گزارش جامع ادمین ---
        if not target_user_id:
            try:
                main_group_id = int(await loop.run_in_executor(None, db.get_setting, 'main_group_id', 0))
                topic_id_log = int(await loop.run_in_executor(None, db.get_setting, 'topic_id_log', 0))

                if main_group_id != 0:
                    admin_header = f"👑 *گزارش جامع* {escape_markdown('-')} {escape_markdown(now_str)}\n" + '─' * 18 + '\n'
                    
                    # اصلاح: فراخوانی متد جدید از کلاس AdminFormatter
                    admin_report_text = await loop.run_in_executor(
                        None, 
                        AdminFormatter.daily_server_report, 
                        all_users_info_from_api, 
                        db
                    )
                    
                    admin_full_message = admin_header + admin_report_text
                    
                    thread_id = topic_id_log if topic_id_log != 0 else None

                    if len(admin_full_message) > 4096:
                        chunks = [admin_full_message[i:i + 4090] for i in range(0, len(admin_full_message), 4090)]
                        for i, chunk in enumerate(chunks):
                            if i > 0: chunk = f"*{escape_markdown('(ادامه گزارش جامع)')}*\n\n" + chunk
                            await bot.send_message(chat_id=main_group_id, text=chunk, parse_mode="MarkdownV2", message_thread_id=thread_id)
                            await asyncio.sleep(0.5)
                    else:
                        await bot.send_message(chat_id=main_group_id, text=admin_full_message, parse_mode="MarkdownV2", message_thread_id=thread_id)
                    
                    logger.info("SCHEDULER: Admin comprehensive report sent to supergroup.")

            except Exception as e:
                logger.error(f"SCHEDULER: Failed to send admin report to group: {e}", exc_info=True)

        # --- بخش ۲: گزارش کاربران ---
        user_ids_to_process = [target_user_id] if target_user_id else list(await loop.run_in_executor(None, db.get_all_user_ids))
        separator = '\n' + '─' * 18 + '\n'

        for user_id in user_ids_to_process:
            try:
                # جمعه‌ها گزارش شبانه نمی‌رود (مگر تست دستی)
                if is_friday and user_id not in ADMIN_IDS and not target_user_id:
                    continue

                user_settings = await loop.run_in_executor(None, db.get_user_settings, user_id)
                if not user_settings.get('daily_reports', True) and not target_user_id:
                    continue

                user_uuids_from_db = await loop.run_in_executor(None, db.uuids, user_id)
                user_infos_for_report = []
                
                for u_row in user_uuids_from_db:
                    if u_row['uuid'] in user_info_map:
                        user_data = user_info_map[u_row['uuid']]
                        user_data['db_id'] = u_row['id'] 
                        user_infos_for_report.append(user_data)
                
                if user_infos_for_report:
                    user_header = f"🌙 *گزارش شبانه* {escape_markdown('-')} {escape_markdown(now_str)}{separator}"
                    lang_code = await loop.run_in_executor(None, db.get_user_language, user_id)
                    user_report_text = await loop.run_in_executor(None, fmt_user_report, user_infos_for_report, lang_code)
                    user_full_message = user_header + user_report_text
                    
                    sent_message = await bot.send_message(user_id, user_full_message, parse_mode="MarkdownV2")
                    
                    if sent_message:
                        await loop.run_in_executor(None, db.add_sent_report, user_id, sent_message.message_id)
                
                await asyncio.sleep(0.05) # Rate limit

            except apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in e.description:
                    user_uuids = await loop.run_in_executor(None, db.uuids, user_id)
                    for u in user_uuids:
                        await loop.run_in_executor(None, db.deactivate_uuid, u['id'])
                else:
                    logger.error(f"SCHEDULER: API error for user {user_id}: {e}")
            except Exception as e:
                logger.error(f"SCHEDULER: CRITICAL FAILURE for user {user_id}: {e}", exc_info=True)

        logger.info("SCHEDULER (Async): ----- Finished nightly report job -----")
    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in nightly_report: {e}", exc_info=True)


# ---------------------------------------------------------
# 2. WEEKLY REPORT (گزارش هفتگی)
# ---------------------------------------------------------
async def weekly_report(bot, target_user_id: int = None) -> None:
    """
    نسخه Async: گزارش هفتگی مصرف را برای کاربران ارسال می‌کند.
    """
    logger.info("SCHEDULER (Async): Starting weekly report job.")
    loop = asyncio.get_running_loop()
    
    try:
        now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        
        all_users_info = await loop.run_in_executor(None, combined_handler.get_all_users_combined)
        if not all_users_info:
            return
        
        user_info_map = {u['uuid']: u for u in all_users_info}
        user_ids_to_process = [target_user_id] if target_user_id else list(await loop.run_in_executor(None, db.get_all_user_ids))
        separator = '\n' + '─' * 18 + '\n'

        for user_id in user_ids_to_process:
            try:
                user_settings = await loop.run_in_executor(None, db.get_user_settings, user_id)
                if not user_settings.get('weekly_reports', True) and not target_user_id:
                    continue

                user_uuids = await loop.run_in_executor(None, db.uuids, user_id)
                user_infos = [user_info_map[u['uuid']] for u in user_uuids if u['uuid'] in user_info_map]
                
                if user_infos:
                    header = f"📊 *گزارش هفتگی* {escape_markdown('-')} {escape_markdown(now_str)}{separator}"
                    lang_code = await loop.run_in_executor(None, db.get_user_language, user_id)
                    report_text = await loop.run_in_executor(None, fmt_user_weekly_report, user_infos, lang_code)
                    
                    final_message = header + report_text
                    
                    sent_message = await bot.send_message(user_id, final_message, parse_mode="MarkdownV2")
                    if sent_message:
                        await loop.run_in_executor(None, db.add_sent_report, user_id, sent_message.message_id)
                
                await asyncio.sleep(0.05)

            except apihelper.ApiTelegramException as e:
                if "bot was blocked by the user" in e.description:
                    user_uuids = await loop.run_in_executor(None, db.uuids, user_id)
                    for u in user_uuids:
                        await loop.run_in_executor(None, db.deactivate_uuid, u['id'])
                else:
                    logger.error(f"SCHEDULER (Weekly): API error for user {user_id}: {e}")
            except Exception as e:
                logger.error(f"SCHEDULER (Weekly): Failure for user {user_id}: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in weekly_report: {e}", exc_info=True)


# ---------------------------------------------------------
# 3. WEEKLY ADMIN SUMMARY (خلاصه هفتگی ادمین)
# ---------------------------------------------------------

async def send_weekly_admin_summary(bot) -> None:
    """
    نسخه Async: گزارش هفتگی را برای ادمین می‌فرستد و به ۲۰ کاربر برتر پیام تبریک (طبق کلیدهای فایل زبان) می‌دهد.
    """
    from .warnings import send_warning_message

    logger.info("SCHEDULER (Async): Sending weekly admin summary (Custom Rank Messages).")
    loop = asyncio.get_running_loop()

    try:
        report_data = await loop.run_in_executor(None, db.get_weekly_top_consumers_report)
        
        # اصلاح: فراخوانی متد جدید از کلاس AdminFormatter
        report_text = await loop.run_in_executor(
            None, 
            AdminFormatter.weekly_top_consumers_report, 
            report_data
        )

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, report_text, parse_mode="MarkdownV2")
            except Exception as e:
                logger.error(f"Failed to send weekly admin summary to {admin_id}: {e}")

        top_users = report_data.get('top_20_overall', [])
        if top_users:
            all_bot_users_with_uuids = await loop.run_in_executor(None, db.get_all_bot_users_with_uuids)
            
            user_map = {}
            for user in all_bot_users_with_uuids:
                name = user.get('config_name')
                if name and name not in user_map:
                    user_map[name] = user['user_id']

            for i, user in enumerate(top_users):
                try:
                    rank = i + 1
                    user_name = user.get('name')
                    usage_raw = user.get('total_usage', 0)
                    formatted_usage = escape_markdown(f"{usage_raw:.2f} GB")
                    
                    user_id = user_map.get(user_name)

                    if user_id:
                        lang_code = await loop.run_in_executor(None, db.get_user_language, user_id)
                        
                        if rank == 1: key = "weekly_top_user_rank_1"
                        elif rank == 2: key = "weekly_top_user_rank_2"
                        elif rank == 3: key = "weekly_top_user_rank_3"
                        elif rank == 4: key = "weekly_top_user_rank_4"
                        elif rank == 5: key = "weekly_top_user_rank_5"
                        else: key = "weekly_top_user_rank_6_to_20"
                        
                        template = get_string(key, lang_code)
                        format_args = {"usage": formatted_usage, "rank": rank}
                        final_msg = template.format(**format_args)
                        
                        # فرض بر این است که send_warning_message ناهمگام (async) است
                        await send_warning_message(bot, user_id, final_msg, name=user_name)
                        
                        await asyncio.sleep(0.5)

                except KeyError as e:
                     logger.error(f"Missing key in language file for rank {rank}: {e}")
                except Exception as e:
                    logger.error(f"Failed to send weekly top user notification for rank {rank}: {e}")

    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in weekly_admin_summary: {e}", exc_info=True)

# ---------------------------------------------------------
# 4. MONTHLY SATISFACTION SURVEY (نظرسنجی ماهانه)
# ---------------------------------------------------------
async def send_monthly_satisfaction_survey(bot) -> None:
    """
    نسخه Async: در آخرین جمعه هر ماه شمسی، پیام نظرسنجی رضایت را ارسال می‌کند.
    """
    logger.info("SCHEDULER (Async): Checking for monthly satisfaction survey...")
    loop = asyncio.get_running_loop()

    try:
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_gregorian = datetime.now(tehran_tz)
        now_shamsi = jdatetime.datetime.fromgregorian(datetime=now_gregorian)
        
        next_week_gregorian = now_gregorian + timedelta(days=7)
        next_week_shamsi = jdatetime.datetime.fromgregorian(datetime=next_week_gregorian)
        is_last_shamsi_friday = (now_shamsi.month != next_week_shamsi.month)
        
        if not is_last_shamsi_friday:
            logger.info("SCHEDULER: Not the last Shamsi Friday. Skipping.")
            return

        logger.info("SCHEDULER: It's the last Shamsi Friday! Sending survey.")
        
        user_ids = list(await loop.run_in_executor(None, db.get_all_user_ids))
        
        menu = UserMainMenu()
        kb = await menu.feedback_rating_menu() 

        prompt = "🗓 *گزارش ماهانه*\n\nچقدر از عملکرد و پایداری سرویس ما در این ماه راضی بودید؟\n\nلطفاً با انتخاب ستاره‌ها، به ما امتیاز دهید:"
        
        for uid in user_ids:
            try:
                await bot.send_message(uid, prompt, reply_markup=kb, parse_mode="Markdown")
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning(f"Failed to send feedback poll to user {uid}: {e}")

    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in satisfaction_survey: {e}", exc_info=True)