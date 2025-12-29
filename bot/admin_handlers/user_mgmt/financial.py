# bot/admin_handlers/user_mgmt/financial.py

import time
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.date_helpers import to_shamsi
from bot.utils.formatters import escape_markdown
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.database import db
from .search import show_user_summary

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. مالی (Payments)
# ==============================================================================

@admin_only
async def handle_payment_history(call: types.CallbackQuery, params: list):
    """نمایش تاریخچه پرداخت"""
    target_id = int(params[0])
    history = await admin_user_service.get_wallet_history(target_id)
    
    text = f"📜 *تاریخچه پرداخت ({len(history)} مورد):*\n──────────────────\n"
    for h in history:
        date_str = to_shamsi(h['transaction_date'], include_time=True)
        text += f"💰 {int(h['amount']):,} | 📅 {escape_markdown(date_str)}\n"
        
    kb = types.InlineKeyboardMarkup()
    # دکمه برای حذف تاریخچه
    kb.add(types.InlineKeyboardButton("🗑 پاکسازی تاریخچه", callback_data=f"admin:reset_phist_conf:{0}:{target_id}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_log_payment(call: types.CallbackQuery, params: list):
    """ثبت پرداخت دستی (تمدید دستی)"""
    target_id = int(params[0])
    if await admin_user_service.add_manual_payment(target_id):
        await bot.answer_callback_query(call.id, "✅ پرداخت ثبت شد.")
        await show_user_summary(call.from_user.id, call.message.message_id, target_id)
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در ثبت.")

@admin_only
async def handle_reset_payment_history_confirm(call: types.CallbackQuery, params: list):
    """تایید حذف تاریخچه پرداخت"""
    target_id = params[1]
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("بله، پاک کن", callback_data=f"admin:do_reset_phist:0:{target_id}"),
        types.InlineKeyboardButton("خیر", callback_data=f"admin:us_phist:{target_id}:0")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ آیا تاریخچه پرداخت‌ها پاک شود؟", reply_markup=kb)

@admin_only
async def handle_reset_payment_history_action(call: types.CallbackQuery, params: list):
    """اجرای حذف تاریخچه"""
    target_id = int(params[1])
    uuids = await db.uuids(target_id)
    if uuids:
        await admin_user_service.delete_payment_history(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "🗑 تاریخچه پاک شد.")
    await show_user_summary(call.from_user.id, call.message.message_id, target_id)

# ==============================================================================
# 2. یادداشت (Notes)
# ==============================================================================

@admin_only
async def handle_ask_for_note(call: types.CallbackQuery, params: list):
    """درخواست متن یادداشت"""
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'save_note', 
        'msg_id': msg_id, 
        'target_id': target_id, 
        'next_handler': process_save_note
    }
    
    await _safe_edit(uid, msg_id, "📝 یادداشت خود را بنویسید (برای حذف، 'پاک' بفرستید):", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

@admin_only
async def process_save_note(message: types.Message):
    """ذخیره یادداشت"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    note = None if text == 'پاک' else text
    await admin_user_service.update_user_note(data['target_id'], note)
    
    await show_user_summary(uid, data['msg_id'], data['target_id'], extra_message="✅ یادداشت ذخیره شد.")

# ==============================================================================
# 3. تمدید (Renew)
# ==============================================================================

@admin_only
async def handle_renew_subscription_menu(call: types.CallbackQuery, params: list):
    """منوی انتخاب پلن برای تمدید"""
    target_id = params[0]
    plans = await db.get_all_plans()
    if not plans:
        await bot.answer_callback_query(call.id, "هیچ پلنی یافت نشد.", show_alert=True)
        return
        
    markup = await admin_menu.select_plan_for_renew_menu(target_id, "", plans)
    await _safe_edit(call.from_user.id, call.message.message_id, "🔄 پلن تمدید را انتخاب کنید:", reply_markup=markup)

@admin_only
async def handle_renew_apply_plan(call: types.CallbackQuery, params: list):
    """اجرای تمدید"""
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    await _safe_edit(uid, msg_id, "⏳ در حال تمدید...", reply_markup=None)
    success = await admin_user_service.renew_user(target_id, plan_id)
    
    msg = "✅ سرویس تمدید شد." if success else "❌ خطا در تمدید."
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, msg, reply_markup=kb)

# ==============================================================================
# 4. نشان‌ها (Badges/Achievements)
# ==============================================================================

@admin_only
async def handle_award_badge_menu(call: types.CallbackQuery, params: list):
    target_id = params[0]
    markup = await admin_menu.award_badge_menu(target_id, "")
    await _safe_edit(call.from_user.id, call.message.message_id, "🏅 انتخاب نشان:", reply_markup=markup)

@admin_only
async def handle_award_badge(call: types.CallbackQuery, params: list):
    badge_code, target_id = params[0], int(params[1])
    await db.add_achievement(target_id, badge_code)
    await bot.answer_callback_query(call.id, "✅ اهدا شد.")
    await handle_award_badge_menu(call, [str(target_id)])

@admin_only
async def handle_achievement_request_callback(call: types.CallbackQuery, params: list):
    """تایید یا رد درخواست نشان"""
    req_id = int(params[0])
    action = call.data.split(':')[1]
    status = 'approved' if 'approve' in action else 'rejected'
    
    await db.update_achievement_request_status(req_id, status, call.from_user.id)
    
    if status == 'approved':
        req = await db.get_achievement_request(req_id)
        if req:
            await db.add_achievement(req['user_id'], req['badge_code'])
            try: await bot.send_message(req['user_id'], "✅ درخواست نشان شما تایید شد!")
            except: pass
            
    await bot.edit_message_caption(f"{call.message.caption}\n\nوضعیت: {status}", call.from_user.id, call.message.message_id)