from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.date_helpers import to_shamsi
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

@admin_only
async def handle_payment_history(call, params):
    target_id = int(params[0])
    history = await admin_user_service.get_wallet_history(target_id)
    text = f"📜 تاریخچه پرداخت ({len(history)} مورد):\n\n"
    for h in history: text += f"💰 {int(h['amount']):,} | 📅 {to_shamsi(h['transaction_date'])}\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

@admin_only
async def handle_log_payment(call, params):
    target_id = int(params[0])
    if await admin_user_service.add_manual_payment(target_id):
        await bot.answer_callback_query(call.id, "✅ پرداخت ثبت شد.")
        await show_user_summary(call.from_user.id, call.message.message_id, target_id)
    else:
        await bot.answer_callback_query(call.id, "❌ خطا.")

@admin_only
async def handle_ask_for_note(call, params):
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'save_note', 'msg_id': msg_id, 'target_id': target_id, 'next_handler': process_save_note}
    await _safe_edit(uid, msg_id, "📝 یادداشت خود را بنویسید (برای حذف، 'پاک' بفرستید):", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

@admin_only
async def process_save_note(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    note = None if text == 'پاک' else text
    await admin_user_service.update_user_note(data['target_id'], note)
    await show_user_summary(uid, data['msg_id'], data['target_id'], extra_message="✅ یادداشت ذخیره شد.")

@admin_only
async def handle_renew_subscription_menu(call, params):
    target_id = params[0]
    plans = await db.get_all_plans()
    markup = await admin_menu.select_plan_for_renew_menu(target_id, "", plans)
    await _safe_edit(call.from_user.id, call.message.message_id, "🔄 پلن تمدید را انتخاب کنید:", reply_markup=markup)

@admin_only
async def handle_renew_apply_plan(call, params):
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    await _safe_edit(uid, msg_id, "⏳ در حال تمدید...", reply_markup=None)
    success = await admin_user_service.renew_user(target_id, plan_id)
    msg = "✅ سرویس تمدید شد." if success else "❌ خطا در تمدید."
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, msg, reply_markup=kb)