# bot/admin_handlers/user_management/profile.py

from telebot import types
from sqlalchemy import select

from bot.admin_handlers.user_management.state import bot
from bot.database import db
from bot.db.base import User
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.date_helpers import to_shamsi
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot import combined_handler
from bot.formatters import user_formatter

async def handle_show_user_summary(call: types.CallbackQuery, params: list):
    """هندلر دکمه نمایش خلاصه کاربر"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    real_user_id = None
    if str(target_id).isdigit():
        real_user_id = int(target_id)
    else:
        # اگر UUID ارسال شده بود، آیدی عددی را پیدا کن
        real_user_id = await db.get_user_id_by_uuid(target_id)
    
    if not real_user_id:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
        return

    # پارامتر context برای دکمه بازگشت (مثلاً s یعنی از جستجو آمده)
    context = params[1] if len(params) > 1 else None
    await show_user_summary(uid, msg_id, real_user_id, context)


async def show_user_summary(admin_id, msg_id, target_user_id, context=None, extra_message=None):
    """تابع اصلی ساخت و نمایش پروفایل کاربر"""
    async with db.get_session() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await _safe_edit(admin_id, msg_id, escape_markdown("❌ کاربر در دیتابیس یافت نشد."), reply_markup=await admin_menu.main(), parse_mode="MarkdownV2")
            return
            
        uuids = await db.uuids(target_user_id)
        active_uuids = [u for u in uuids if u['is_active']]
        
        safe_name = escape_markdown(user.first_name or 'Unknown')
        
        if active_uuids:
            # دریافت اطلاعات ترکیبی از سرورها
            main_uuid = active_uuids[0]['uuid']
            info = await combined_handler.get_combined_user_info(str(main_uuid))
            
            if info:
                info['db_id'] = active_uuids[0]['id']
                history = await db.get_user_payment_history(active_uuids[0]['id'])
                payment_count = len(history)
                
                formatted_body = await user_formatter.profile_info(info, 'fa')
                lines = formatted_body.split('\n')
                
                is_active = info.get('is_active')
                status_emoji = "✅" if is_active else "❌"
                status_text = "فعال" if is_active else "غیرفعال"
                
                new_header = f"👤 نام : {safe_name} \({status_emoji} {status_text} \| {payment_count} پرداخت\)"
                lines[0] = f"*{new_header}*"
                
                admin_lines = ["──────────────────"]
                
                if user.admin_note:
                    safe_note = escape_markdown(user.admin_note)
                    admin_lines.append(f"📝 یادداشت: {safe_note}")
                
                admin_lines.append(f"🆔 آیدی عددی: `{target_user_id}`")
                wallet_balance = int(user.wallet_balance or 0)
                admin_lines.append(f"💰 کیف پول: `{wallet_balance:,}` تومان")
                
                text = "\n".join(lines) + "\n" + "\n".join(admin_lines)
            else:
                text = escape_markdown("❌ خطا در دریافت اطلاعات از سرور.")
        else:
            text = f"👤 کاربر: {safe_name}\n🔴 وضعیت: غیرفعال \(بدون سرویس فعال\)\n🆔 `{target_user_id}`"

    if extra_message:
        text += f"\n\n{extra_message}"

    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    panel_type = 'hiddify' # پیش‌فرض، یا می‌توان داینامیک کرد
    
    markup = await admin_menu.user_interactive_menu(str(user.user_id), bool(active_uuids), panel_type, back_callback=back_cb)
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

# --- این بخش را به انتهای فایل profile.py اضافه کنید ---

async def handle_user_interactive_menu(call: types.CallbackQuery, params: list):
    """
    این تابع برای دکمه‌های اینتراکتیو (مثل رفرش) استفاده می‌شود.
    فقط درخواست را دوباره به نمایش پروفایل هدایت می‌کند.
    """
    await handle_show_user_summary(call, params)