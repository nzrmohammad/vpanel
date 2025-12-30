# bot/admin_handlers/user_management/finance.py

import logging
from telebot import types

from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.date_helpers import to_shamsi
from bot.keyboards.admin import admin_keyboard as admin_menu

# ایمپورت‌های ماژولار
from bot.bot_instance import bot
from bot.admin_handlers.user_management.profile import show_user_summary

logger = logging.getLogger(__name__)

async def handle_payment_history(call, params):
    """نمایش تاریخچه پرداخت‌ها"""
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    user_info = await db.user(target_id)
    user_name = user_info.get('first_name', str(target_id)) if user_info else str(target_id)
    safe_name = escape_markdown(user_name)
    
    history = await db.get_wallet_history(target_id, limit=20)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    if not history:
        text = f"سابقه پرداخت‌های کاربر: {safe_name}\n\nهیچ پرداخت ثبت‌شده‌ای برای این کاربر یافت نشد\\."
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")
        return
    
    lines = [f"📜 *تاریخچه تراکنش‌های {safe_name}*", "──────────────────"]
    
    for t in history:
        amount = t.get('amount', 0)
        desc = t.get('description') or t.get('type', '')
        dt_str = to_shamsi(t.get('transaction_date'), include_time=True)
        
        icon = "🟢" if amount > 0 else "🔴"
        amt_str = f"{int(abs(amount)):,} تومان"
        
        block = (
            f"{icon} *{escape_markdown(amt_str)}*\n"
            f"📅 {escape_markdown(dt_str)}\n"
            f"📝 {escape_markdown(desc)}\n"
            "──────────────────"
        )
        lines.append(block)
        
    final_text = "\n".join(lines)
    await _safe_edit(uid, msg_id, final_text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_log_payment(call, params):
    """ثبت دستی پرداخت"""
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    
    if uuids:
        await db.add_payment_record(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ پرداخت ثبت شد.")
        
        try:
            await bot.send_message(target_id, "✅ اشتراک شما توسط مدیریت تمدید شد.\nبا تشکر از پرداخت شما.")
        except Exception as e:
            logger.warning(f"Could not send msg to {target_id}: {e}")

        await show_user_summary(call.from_user.id, call.message.message_id, target_id)
    else:
        await bot.answer_callback_query(call.id, "سرویسی وجود ندارد.", show_alert=True)

async def handle_reset_payment_history_confirm(call, params):
    """تاییدیه حذف تاریخچه"""
    uuid_id, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    text = "⚠️ آیا مطمئن هستید که می‌خواهید تاریخچه پرداخت‌ها را پاک کنید؟"
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("بله، پاک کن", callback_data=f"admin:do_reset_phist:{uuid_id}:{target_id}"),
        types.InlineKeyboardButton("خیر", callback_data=f"admin:us_phist:{target_id}:0")
    )
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_reset_payment_history_action(call, params):
    """اجرای حذف تاریخچه"""
    uuid_id, target_id = int(params[0]), params[1]
    await db.delete_user_payment_history(uuid_id)
    await bot.answer_callback_query(call.id, "🗑 تاریخچه پاک شد.")
    # فراخوانی مجدد پروفایل یا تاریخچه
    await show_user_summary(call.from_user.id, call.message.message_id, int(target_id))