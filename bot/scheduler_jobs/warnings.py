# bot/scheduler_jobs/warnings.py

import logging
import asyncio
from datetime import datetime, timedelta
import pytz
from telebot import types, apihelper

from bot.database import db
from bot.utils import escape_markdown, bytes_to_gb
# تغییر مهم: استفاده از combined_handler به جای user_aggregator
from bot import combined_handler 
from bot.services import user_modifier 
from bot.keyboards.user import wallet as wallet_kb 

logger = logging.getLogger(__name__)

# --- شروع کدهای اضافه شده ---
COUNTRY_TO_EMOJI = {
    'ir': '🇮🇷', 'fr': '🇫🇷', 'de': '🇩🇪', 'tr': '🇹🇷',
    'us': '🇺🇸', 'gb': '🇬🇧', 'nl': '🇳🇱', 'fi': '🇫🇮',
    'ro': '🇷🇴', 'ru': '🇷🇺', 'ua': '🇺🇦', 'ae': '🇦🇪',
    'pl': '🇵🇱', 'ca': '🇨🇦', 'es': '🇪🇸', 'ch': '🇨🇭',
    'se': '🇸🇪', 'no': '🇳🇴', 'it': '🇮🇹', 'in': '🇮🇳'
}

def get_dynamic_flags_for_user(user_db_record, panel_type: str) -> str:
    """نسخه داخلی تابع دریافت پرچم"""
    if not user_db_record: return '🌐'
    unique_countries = set()
    
    # پشتیبانی از دیکشنری یا آبجکت
    panels = user_db_record.get('allowed_panels', []) if isinstance(user_db_record, dict) else getattr(user_db_record, 'allowed_panels', [])
    
    if panels:
        for panel in panels:
            # دریافت مقادیر به صورت ایمن (هم آبجکت هم دیکشنری)
            p_type = getattr(panel, 'type', None) if not isinstance(panel, dict) else panel.get('type')
            if p_type and panel_type and str(p_type).lower() != str(panel_type).lower():
                continue
            
            code = getattr(panel, 'country', None) if not isinstance(panel, dict) else panel.get('country')
            if not code:
                code = getattr(panel, 'category', None) if not isinstance(panel, dict) else panel.get('category')
            
            if code: unique_countries.add(code)
            
    if not unique_countries: return '🏳️'
    return "".join([COUNTRY_TO_EMOJI.get(str(c).lower(), '🌐') for c in sorted(unique_countries)])
# --- پایان کدهای اضافه شده ---

async def send_warning_message(bot, user_id: int, message: str, reply_markup=None):
    """تابع کمکی برای ارسال پیام امن"""
    try:
        await bot.send_message(user_id, message, parse_mode="MarkdownV2", reply_markup=reply_markup)
        return True
    except apihelper.ApiTelegramException as e:
        if "blocked" in str(e) or "user is deactivated" in str(e):
            logger.warning(f"User {user_id} blocked the bot.")
        else:
            logger.error(f"Failed to send warning to {user_id}: {e}")
        return False

async def check_and_send_warnings(bot):
    """
    تسک اصلی اسکجولر: بررسی و ارسال هشدارها با تنظیمات داینامیک از دیتابیس
    """
    logger.info("Starting warnings check job...")
    
    try:
        # اصلاح شده: استفاده از get_config به جای get_setting
        WARNING_DAYS = int(await db.get_config('warning_days_before_expiry', 3))
        INACTIVE_DAYS = int(await db.get_config('inactive_days_threshold', 7))
        EMERGENCY_GB = float(await db.get_config('emergency_volume_gb', 1.0))
    except Exception as e:
        logger.error(f"Error fetching settings, using defaults: {e}")
        WARNING_DAYS = 3
        INACTIVE_DAYS = 7
        EMERGENCY_GB = 1.0

    # 2. اصلاح شده: دریافت اطلاعات کاربران از combined_handler
    all_users = await combined_handler.get_all_users_combined()
    
    if not all_users:
        logger.info("No users found in cache/combined handler.")
        return

    for user in all_users:
        try:
            uuid = user.get('uuid')
            if not uuid: continue

            db_user = await db.get_bot_user_by_uuid(uuid)
            if not db_user or not db_user.get('user_id'):
                continue 

            telegram_id = db_user['user_id']
            uuid_id_in_db = await db.get_uuid_id_by_uuid(uuid)
            
            user_settings = await db.get_user_settings(telegram_id)
            if not user_settings.get('expiry_warnings', True):
                continue

            # دریافت پرچم و نام سرور
            flags = get_dynamic_flags_for_user(await db.get_user_uuid_record(uuid), None)
            server_display_name = f"سرور {flags}"

            # محاسبات حجم و زمان
            remaining_bytes = (user.get('usage_limit_GB', 0) * 1024**3) - (user.get('current_usage_GB', 0) * 1024**3)
            remaining_gb = bytes_to_gb(remaining_bytes)
            
            expire_ts = float(user.get('expire') or 0)
            days_left = -999
            if expire_ts > 0:
                days_left = (datetime.fromtimestamp(expire_ts) - datetime.now()).days

            # ====================================================
            # 4. هشدار اتمام حجم + هدیه اضطراری
            # ====================================================
            if 0 < remaining_gb < 0.2 and user.get('enable'):
                if not await db.has_recent_warning(uuid_id_in_db, 'volume_depleted', hours=72):
                    
                    add_success = await user_modifier.add_traffic(uuid, EMERGENCY_GB)
                    
                    if add_success:
                        msg = (
                            f"🔴 *اتمام حجم*\n\n"
                            f"حجم سرویس شما در *{escape_markdown(server_display_name)}* به پایان رسیده بود\\.\n\n"
                            f"🎁 *{EMERGENCY_GB} گیگابایت* حجم اضطراری برای شما فعال شد تا بتوانید به راحتی سرویس خود را تمدید کنید\\."
                        )
                        kb = types.InlineKeyboardMarkup()
                        kb.add(types.InlineKeyboardButton("🔄 تمدید سرویس", callback_data=f"wallet:renew:{uuid}"))
                        
                        if await send_warning_message(bot, telegram_id, msg, kb):
                            await db.log_warning(uuid_id_in_db, 'volume_depleted')
                            logger.info(f"Emergency volume ({EMERGENCY_GB}GB) given to {uuid}")
                    continue

            # ====================================================
            # 3.5. هشدار منقضی شده
            # ====================================================
            if days_left <= 0 and expire_ts > 0:
                if not await db.has_recent_warning(uuid_id_in_db, 'expired', hours=120):
                    msg = (
                        f"❌ *سرویس منقضی شد*\n\n"
                        f"مشترک گرامی، مهلت سرویس *{escape_markdown(server_display_name)}* شما به پایان رسیده است\\.\n"
                        f"جهت جلوگیری از حذف سرویس، لطفا نسبت به تمدید اقدام کنید\\."
                    )
                    kb = types.InlineKeyboardMarkup()
                    kb.add(types.InlineKeyboardButton("🔄 تمدید فوری", callback_data=f"wallet:renew:{uuid}"))
                    
                    if await send_warning_message(bot, telegram_id, msg, kb):
                        await db.log_warning(uuid_id_in_db, 'expired')
                continue

            # ====================================================
            # 3. هشدار انقضای نزدیک
            # ====================================================
            if 0 <= days_left <= WARNING_DAYS:
                if not await db.has_recent_warning(uuid_id_in_db, f'expiry_{days_left}d', hours=20):
                    
                    status_color = "🟠" if days_left > 1 else "🔴"
                    msg = (
                        f"{status_color} *یادآوری تمدید*\n\n"
                        f"تنها *{days_left} روز* از اعتبار سرویس *{escape_markdown(server_display_name)}* باقی مانده است\\.\n"
                        f"پیشنهاد می‌کنیم پیش از قطعی، سرویس خود را تمدید کنید\\."
                    )
                    kb = types.InlineKeyboardMarkup()
                    kb.add(types.InlineKeyboardButton("💳 تمدید آنلاین", callback_data=f"wallet:renew:{uuid}"))
                    
                    if await send_warning_message(bot, telegram_id, msg, kb):
                        await db.log_warning(uuid_id_in_db, f'expiry_{days_left}d')
                continue

            # ====================================================
            # 5. پیام عدم فعالیت
            # ====================================================
            last_seen_str = user.get('last_online')
            if last_seen_str and remaining_gb > 1:
                try:
                    if 'T' in str(last_seen_str):
                        last_seen_dt = datetime.fromisoformat(str(last_seen_str).replace('Z', ''))
                    else:
                        last_seen_dt = datetime.utcfromtimestamp(float(last_seen_str))
                    
                    days_inactive = (datetime.utcnow() - last_seen_dt).days
                    
                    if days_inactive >= INACTIVE_DAYS:
                        if not await db.has_recent_warning(uuid_id_in_db, 'inactive_reminder', hours=168):
                            msg = (
                                f"👋 *دلمون برات تنگ شده\\!*\n\n"
                                f"چند وقته از سرویس *{escape_markdown(server_display_name)}* استفاده نکردی\\.\n"
                                f"همه چیز مرتبه؟ اگر مشکلی در اتصال داری، به پشتیبانی پیام بده\\."
                            )
                            kb = types.InlineKeyboardMarkup()
                            kb.add(types.InlineKeyboardButton("🚑 پشتیبانی", callback_data="main:support"))
                            kb.add(types.InlineKeyboardButton("آموزش اتصال", callback_data="main:tutorials"))

                            if await send_warning_message(bot, telegram_id, msg, kb):
                                await db.log_warning(uuid_id_in_db, 'inactive_reminder')

                except Exception as e:
                    logger.debug(f"Date error inactive check: {e}")

        except Exception as e:
            logger.error(f"Error processing user {user.get('name')}: {e}")

    logger.info("Warnings check job finished.")