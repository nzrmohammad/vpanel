# bot/scheduler_jobs/reports.py

import logging
import asyncio
from datetime import datetime, timedelta, timezone
import pytz
import jdatetime
from sqlalchemy import select
from telebot import apihelper

from bot import combined_handler
from bot.database import db
from bot.db.base import Panel
from bot.utils.formatters import escape_markdown

# ایمپورت‌های ضروری
from bot.formatters import admin_formatter, user_formatter
from bot.keyboards.user.main import UserMainMenu
from bot.config import ADMIN_IDS
from bot.language import get_string

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# توابع کمکی
# ---------------------------------------------------------

async def get_dynamic_type_flags() -> dict:
    """
    پرچم‌های سیستم را بر اساس پنل‌های فعال موجود در دیتابیس استخراج می‌کند.
    خروجی: {'hiddify': '🇩🇪', 'marzban': '🇫🇷🇮🇷', ...}
    """
    type_flags = {}
    try:
        async with db.get_session() as session:
            stmt = select(Panel).where(Panel.is_active == True)
            panels = (await session.execute(stmt)).scalars().all()
            
            temp_map = {}
            for p in panels:
                if not p.type: continue
                if p.type not in temp_map: temp_map[p.type] = set()
                if p.flag:
                    temp_map[p.type].add(p.flag)
            
            for p_type, flags_set in temp_map.items():
                sorted_flags = "".join(sorted(list(flags_set)))
                type_flags[p_type] = sorted_flags
                
    except Exception as e:
        logger.error(f"Error fetching dynamic flags: {e}")
    
    return type_flags

def _fmt_user_weekly_report(user_infos: list, lang_code: str) -> str:
    """تولید متن گزارش هفتگی (تابع کمکی)"""
    lines = []
    for info in user_infos:
        name = escape_markdown(info.get('name', 'Unknown'))
        usage = info.get('current_usage_GB', 0)
        lines.append(f"👤 *{name}* : `{usage:.2f} GB` (کل)")
    
    return "\n\n".join(lines)

# ---------------------------------------------------------
# 1. NIGHTLY REPORT (گزارش شبانه)
# ---------------------------------------------------------
async def nightly_report(bot, target_user_id: int = None) -> None:
    """
    گزارش شبانه: ارسال گزارش دقیق به کاربران و گزارش جامع به ادمین.
    """
    tehran_tz = pytz.timezone("Asia/Tehran")
    now_tehran = datetime.now(tehran_tz)
    now_utc = datetime.now(timezone.utc)
    
    start_of_day_tehran = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_tehran.astimezone(timezone.utc)

    is_friday = jdatetime.datetime.fromgregorian(datetime=now_tehran).weekday() == 6
    now_str = jdatetime.datetime.fromgregorian(datetime=now_tehran).strftime("%Y/%m/%d - %H:%M")
    
    logger.info(f"SCHEDULER (Async): ----- Running nightly report at {now_str} -----")

    try:
        # 1. دریافت پرچم‌ها از سیستم
        type_flags_map = await get_dynamic_type_flags()

        # 2. دریافت لیست کامل کاربران
        all_users_info_from_api = await combined_handler.get_all_users_combined()
        if not all_users_info_from_api:
            return

        user_info_map = {user['uuid']: user for user in all_users_info_from_api}
        
        # 3. دریافت مصرف امروز
        daily_usage_map = await db.get_all_daily_usage_since_midnight()

        # --- بخش ۱: گزارش جامع ادمین ---
        if not target_user_id:
            try:
                payments_today = await db.get_total_payments_in_range(start_of_day_utc, now_utc)
                new_users_today = await db.get_new_users_in_range(start_of_day_utc, now_utc)

                main_group_id_str = await db.get_config('main_group_id', 0)
                main_group_id = int(main_group_id_str) if main_group_id_str else 0
                topic_id_log_str = await db.get_config('topic_id_log', 0)
                topic_id_log = int(topic_id_log_str) if topic_id_log_str else 0

                if main_group_id != 0:
                    stats_data = {
                        'daily_usage_map': daily_usage_map,
                        'payments_today': payments_today,
                        'new_users_today': new_users_today,
                        'timestamp_str': now_str,
                        'type_flags_map': type_flags_map
                    }

                    admin_report_text = admin_formatter.reports.daily_server_stats(all_users_info_from_api, stats_data)
                    
                    thread_id = topic_id_log if topic_id_log != 0 else None

                    if len(admin_report_text) > 4096:
                        chunks = [admin_report_text[i:i + 4090] for i in range(0, len(admin_report_text), 4090)]
                        for i, chunk in enumerate(chunks):
                            if i > 0: chunk = f"*{escape_markdown('(ادامه...)')}*\n" + chunk
                            await bot.send_message(chat_id=main_group_id, text=chunk, parse_mode="MarkdownV2", message_thread_id=thread_id)
                            await asyncio.sleep(0.5)
                    else:
                        await bot.send_message(chat_id=main_group_id, text=admin_report_text, parse_mode="MarkdownV2", message_thread_id=thread_id)
                    
                    logger.info("SCHEDULER: Admin report sent.")

            except Exception as e:
                logger.error(f"SCHEDULER: Failed to send admin report: {e}", exc_info=True)

        # --- بخش ۲: گزارش کاربران ---
        if target_user_id:
            user_ids_to_process = [target_user_id]
        else:
            user_ids_to_process = [uid async for uid in db.get_all_user_ids()]
            
        separator = '\n' + '─' * 18 + '\n'

        for user_id in user_ids_to_process:
            try:
                if is_friday and user_id not in ADMIN_IDS and not target_user_id:
                    continue

                user_settings = await db.get_user_settings(user_id)
                if not user_settings.get('daily_reports', True) and not target_user_id:
                    continue

                user_uuids_from_db = await db.uuids(user_id)
                reports_content = []
                
                for u_row in user_uuids_from_db:
                    uuid_str = u_row['uuid']
                    if uuid_str in user_info_map:
                        user_data = user_info_map[uuid_str]
                        this_uuid_daily = daily_usage_map.get(uuid_str, {})
                        
                        # تولید گزارش کاربر
                        report_block = user_formatter.notification.nightly_report(
                            user_data, 
                            this_uuid_daily,
                            type_flags_map
                        )
                        reports_content.append(report_block)

                if reports_content:
                    header = f"🌙 *گزارش شبانه* {escape_markdown('-')} {escape_markdown(now_str)}{separator}"
                    full_body = ("\n" + separator + "\n").join(reports_content)
                    final_msg = header + full_body
                    
                    sent_message = await bot.send_message(user_id, final_msg, parse_mode="MarkdownV2")
                    
                    if sent_message and hasattr(db, 'add_sent_report'):
                        await db.add_sent_report(user_id, sent_message.message_id)
                
                await asyncio.sleep(0.05) 

            except apihelper.ApiTelegramException as e:
                if "bot was blocked" in e.description or "user is deactivated" in e.description:
                    user_uuids = await db.uuids(user_id)
                    for u in user_uuids:
                        await db.deactivate_uuid(u['id'])
                else:
                    logger.error(f"SCHEDULER: API error for user {user_id}: {e}")
            except Exception as e:
                logger.error(f"SCHEDULER: CRITICAL for user {user_id}: {e}", exc_info=True)

        logger.info("SCHEDULER (Async): ----- Finished nightly report job -----")
    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in nightly_report: {e}", exc_info=True)


# ---------------------------------------------------------
# 2. WEEKLY REPORT (گزارش هفتگی)
# ---------------------------------------------------------
async def weekly_report(bot, target_user_id: int = None) -> None:
    """نسخه Async: گزارش هفتگی مصرف را برای کاربران ارسال می‌کند."""
    logger.info("SCHEDULER (Async): Starting weekly report job.")
    try:
        now_str = jdatetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        all_users_info = await combined_handler.get_all_users_combined()
        if not all_users_info: return
        
        user_info_map = {u['uuid']: u for u in all_users_info}
        
        if target_user_id:
            user_ids_to_process = [target_user_id]
        else:
            user_ids_to_process = [uid async for uid in db.get_all_user_ids()]

        separator = '\n' + '─' * 18 + '\n'

        for user_id in user_ids_to_process:
            try:
                user_settings = await db.get_user_settings(user_id)
                if not user_settings.get('weekly_reports', True) and not target_user_id:
                    continue

                user_uuids = await db.uuids(user_id)
                user_infos = [user_info_map[u['uuid']] for u in user_uuids if u['uuid'] in user_info_map]
                
                if user_infos:
                    header = f"📊 *گزارش هفتگی* {escape_markdown('-')} {escape_markdown(now_str)}{separator}"
                    lang_code = await db.get_user_language(user_id)
                    
                    report_text = _fmt_user_weekly_report(user_infos, lang_code)
                    final_message = header + report_text
                    
                    sent_message = await bot.send_message(user_id, final_message, parse_mode="MarkdownV2")
                    if sent_message and hasattr(db, 'add_sent_report'):
                         await db.add_sent_report(user_id, sent_message.message_id)
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"SCHEDULER (Weekly): Failure for user {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in weekly_report: {e}", exc_info=True)


# ---------------------------------------------------------
# 3. WEEKLY ADMIN SUMMARY (خلاصه هفتگی ادمین)
# ---------------------------------------------------------
async def send_weekly_admin_summary(bot) -> None:
    """نسخه Async: گزارش هفتگی را برای ادمین می‌فرستد."""
    from .warnings import send_warning_message

    logger.info("SCHEDULER (Async): Sending weekly admin summary.")

    try:
        report_data = await db.get_weekly_top_consumers_report()
        top_list = report_data.get('top_20_overall', [])
        report_text = admin_formatter.reports.weekly_top_consumers(top_list)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, report_text, parse_mode="MarkdownV2")
            except Exception: pass

        # ارسال پیام تشویقی/هشدار به کاربران پرمصرف (Top Users)
        top_users = top_list
        if top_users:
            all_bot_users_with_uuids = await db.get_all_bot_users_with_uuids()
            
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
                        lang_code = await db.get_user_language(user_id)
                        
                        if rank == 1: key = "weekly_top_user_rank_1"
                        elif rank == 2: key = "weekly_top_user_rank_2"
                        elif rank == 3: key = "weekly_top_user_rank_3"
                        elif rank == 4: key = "weekly_top_user_rank_4"
                        elif rank == 5: key = "weekly_top_user_rank_5"
                        else: key = "weekly_top_user_rank_6_to_20"
                        
                        template = get_string(key, lang_code)
                        if template:
                            format_args = {"usage": formatted_usage, "rank": rank}
                            final_msg = template.format(**format_args)
                            await send_warning_message(bot, user_id, final_msg, name=user_name)
                            await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Failed to send weekly top user notification for rank {rank}: {e}")

    except Exception as e:
        logger.error(f"SCHEDULER (Async): Error in weekly_admin_summary: {e}", exc_info=True)


# ---------------------------------------------------------
# 4. MONTHLY SATISFACTION SURVEY (نظرسنجی ماهانه)
# ---------------------------------------------------------
async def send_monthly_satisfaction_survey(bot) -> None:
    """نسخه Async: در آخرین جمعه هر ماه شمسی، پیام نظرسنجی رضایت را ارسال می‌کند."""
    logger.info("SCHEDULER (Async): Checking for monthly satisfaction survey...")

    try:
        tehran_tz = pytz.timezone("Asia/Tehran")
        now_gregorian = datetime.now(tehran_tz)
        now_shamsi = jdatetime.datetime.fromgregorian(datetime=now_gregorian)
        
        next_week_gregorian = now_gregorian + timedelta(days=7)
        next_week_shamsi = jdatetime.datetime.fromgregorian(datetime=next_week_gregorian)
        is_last_shamsi_friday = (now_shamsi.month != next_week_shamsi.month)
        
        # فقط جمعه‌ها اجرا می‌شود (توسط Cron تنظیم شده)، پس شرط اضافی لازم نیست جز ماه
        if not is_last_shamsi_friday:
            logger.info("SCHEDULER: Not the last Shamsi Friday. Skipping.")
            return

        logger.info("SCHEDULER: It's the last Shamsi Friday! Sending survey.")
        
        user_ids = [uid async for uid in db.get_all_user_ids()]
        
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