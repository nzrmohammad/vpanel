import uuid as uuid_lib
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.parsers import validate_uuid
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

# ✅ اضافه شد برای جلوگیری از ارور
@admin_only
async def handle_squad_callback(call, params):
    """هندلر انتخاب اسکواد (برای سازگاری با روتر قدیمی)"""
    await bot.answer_callback_query(call.id, "⚠️ این قابلیت در نسخه جدید موقتاً غیرفعال است.")

@admin_only
async def handle_add_user_select_panel(call: types.CallbackQuery):
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_name = call.data.split(':')[2]
    admin_conversations[uid] = {
        'action': 'add_user', 'step': 'get_name', 'msg_id': msg_id,
        'data': {'panel_name': panel_name}, 'next_handler': get_new_user_name
    }
    await _safe_edit(uid, msg_id, f"👤 سرور: *{escape_markdown(panel_name)}*\nنام کاربر جدید را وارد کنید:", 
                     reply_markup=await admin_menu.cancel_action("admin:management_menu"))

@admin_only
async def get_new_user_name(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['data']['name'] = text
    admin_conversations[uid]['step'] = 'get_uuid'
    admin_conversations[uid]['next_handler'] = get_new_user_uuid
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                     "🔑 لطفاً UUID را وارد کنید (یا `.` برای رندوم):", reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_uuid(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    
    final_uuid = str(uuid_lib.uuid4()) if text == '.' or text.lower() == 'random' else text
    if text != '.' and not validate_uuid(text):
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "❌ فرمت نامعتبر.", reply_markup=await admin_menu.cancel_action())
        return

    admin_conversations[uid]['data']['uuid'] = final_uuid
    admin_conversations[uid]['step'] = 'get_limit'
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "📦 حجم محدودیت (GB)؟ (0 = نامحدود)", reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_limit(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    try:
        val = float(text)
        admin_conversations[uid]['data']['limit'] = val
        admin_conversations[uid]['step'] = 'get_days'
        admin_conversations[uid]['next_handler'] = get_new_user_days
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "📅 مدت اعتبار (روز)؟", reply_markup=await admin_menu.cancel_action())
    except:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "❌ عدد معتبر وارد کنید:", reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_days(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    if uid not in admin_conversations: return
    try:
        admin_conversations[uid]['data']['days'] = int(text)
        await _finalize_user_creation(uid)
    except:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "❌ عدد صحیح وارد کنید:", reply_markup=await admin_menu.cancel_action())

async def _finalize_user_creation(uid):
    data = admin_conversations.pop(uid)
    msg_id = data['msg_id']
    await _safe_edit(uid, msg_id, "⏳ در حال ساخت کاربر...", reply_markup=None)
    result = await admin_user_service.create_user(data['data'])
    
    success_list = [f"🟢 {p['name']}" for p in result['success']]
    fail_list = [f"🔴 {p['name']}" for p in result['fail']]
    txt = f"✅ پایان عملیات.\n👤 نام: {data['data']['name']}\n🔑 UUID: `{result['uuid']}`\n\n"
    if success_list: txt += "\n".join(success_list)
    if fail_list: txt += "\n\nنا موفق:\n" + "\n".join(fail_list)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("مدیریت", callback_data="admin:management_menu"))
    await _safe_edit(uid, msg_id, txt, reply_markup=kb, parse_mode="Markdown")