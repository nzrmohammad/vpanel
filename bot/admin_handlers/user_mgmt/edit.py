from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.database import db
from .search import show_user_summary # استفاده مجدد از تابع نمایش

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

@admin_only
async def handle_edit_user_menu(call, params):
    target_id = params[0]
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
        return
    active_panels = await db.get_active_panels()
    user_panels = [{'name': 'همه پنل‌ها', 'id': 'all', 'flag': '🌐'}]
    for p in active_panels:
        user_panels.append({'name': p['name'], 'id': p['name'], 'flag': '🔹'})
    markup = await admin_menu.edit_user_panel_select_menu(target_id, user_panels)
    await _safe_edit(call.from_user.id, call.message.message_id, "🔧 پنل مورد نظر را انتخاب کنید:", 
                     reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_select_panel_for_edit(call, params):
    panel_target, identifier = params[0], params[1]
    markup = await admin_menu.edit_user_action_menu(identifier, panel_target)
    await _safe_edit(call.from_user.id, call.message.message_id, f"🔧 ویرایش روی: {panel_target}", 
                     reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_ask_edit_value(call, params):
    action, panel_target, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    admin_conversations[uid] = {
        'step': 'edit_value', 'msg_id': msg_id, 'action': action, 'scope': panel_target,
        'target_id': int(target_id), 'next_handler': process_edit_value
    }
    await _safe_edit(uid, msg_id, f"🔢 مقدار *{action_name}* را وارد کنید (مثبت برای افزودن، منفی برای کسر):", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

@admin_only
async def process_edit_value(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    try: value = float(text)
    except: return 
        
    await _safe_edit(uid, data['msg_id'], "⏳ اعمال تغییرات...", reply_markup=None)
    success = await admin_user_service.modify_user_resources(data['target_id'], data['scope'], data['action'], value)
    msg = f"✅ تغییرات اعمال شد: {value}" if success else "❌ خطا در اعمال تغییرات."
    markup = await admin_menu.edit_user_action_menu(str(data['target_id']), data['scope'])
    await _safe_edit(uid, data['msg_id'], msg, reply_markup=markup)

@admin_only
async def handle_toggle_status_action(call, params):
    action, target_id, scope = params[0], int(params[1]), params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    await _safe_edit(uid, msg_id, "⏳ در حال انجام...", reply_markup=None)
    res = await admin_user_service.toggle_user_status(target_id, action, scope)
    status_fa = "فعال" if res.get('status_bool') else "غیرفعال"
    msg = f"✅ وضعیت به **{status_fa}** تغییر کرد.\nتعداد سرورهای موفق: {res.get('count', 0)}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, msg, reply_markup=kb, parse_mode="Markdown")

@admin_only
async def handle_delete_user_confirm(call, params):
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
    await _safe_edit(call.from_user.id, call.message.message_id, 
                     f"⚠️ حذف کاربر `{target_id}`؟ (غیرقابل بازگشت)", reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_delete_user_action(call, params):
    decision, target_id = params[0], int(params[2])
    if decision == 'cancel':
        await show_user_summary(call.from_user.id, call.message.message_id, target_id)
        return
    await admin_user_service.purge_user(target_id)
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ کاربر حذف شد.", 
                     reply_markup=await admin_menu.management_menu([]))