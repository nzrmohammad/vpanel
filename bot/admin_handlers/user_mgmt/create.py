# bot/admin_handlers/user_mgmt/create.py

import uuid as uuid_lib
import time
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.parsers import validate_uuid
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service

# متغیرهای گلوبال ماژول
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
# هندلرهای مربوط به اسکواد (Remnawave) - توابع جا مانده
# ==============================================================================

@admin_only
async def handle_squad_callback(call, params):
    """هندلر انتخاب اسکواد داخلی"""
    # فعلاً یک نسخه ساده برای جلوگیری از کرش
    await bot.answer_callback_query(call.id, "⚠️ قابلیت انتخاب اسکواد در حال بازنویسی است.")

@admin_only
async def handle_external_squad_callback(call, params):
    """هندلر انتخاب اسکواد خارجی"""
    # فعلاً یک نسخه ساده برای جلوگیری از کرش
    await bot.answer_callback_query(call.id, "⚠️ قابلیت انتخاب اسکواد خارجی در حال بازنویسی است.")

# ==============================================================================
# ویزارد ساخت کاربر (Add User Flow)
# ==============================================================================

@admin_only
async def handle_add_user_select_panel(call: types.CallbackQuery):
    """شروع: انتخاب پنل"""
    uid, msg_id = call.from_user.id, call.message.message_id
    # فرمت دیتا: admin:add_user:panel_name
    parts = call.data.split(':')
    panel_name = parts[2] if len(parts) > 2 else "all"
    
    admin_conversations[uid] = {
        'action': 'add_user', 
        'step': 'get_name', 
        'msg_id': msg_id,
        'data': {'panel_name': panel_name}, 
        'next_handler': get_new_user_name,
        'timestamp': time.time()
    }
    
    msg = f"👤 سرور انتخابی: *{escape_markdown(panel_name)}*\n\nلطفاً **نام کاربر جدید** را وارد کنید:"
    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.cancel_action("admin:management_menu"))

@admin_only
async def get_new_user_name(message: types.Message):
    """دریافت نام"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['data']['name'] = text
    admin_conversations[uid]['step'] = 'get_uuid'
    admin_conversations[uid]['next_handler'] = get_new_user_uuid
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                     "🔑 لطفاً **UUID** را وارد کنید (یا `.` برای تولید خودکار):", 
                     reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_uuid(message: types.Message):
    """دریافت یا تولید UUID"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    # تولید یا اعتبارسنجی UUID
    if text == '.' or text.lower() == 'random':
        final_uuid = str(uuid_lib.uuid4())
    else:
        if not validate_uuid(text):
            await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                             "❌ فرمت UUID نامعتبر است. مجدد تلاش کنید:", 
                             reply_markup=await admin_menu.cancel_action())
            return
        final_uuid = text

    admin_conversations[uid]['data']['uuid'] = final_uuid
    admin_conversations[uid]['step'] = 'get_limit'
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                     "📦 **حجم محدودیت (GB)** را وارد کنید:\n(عدد `0` به معنی نامحدود)", 
                     reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_limit(message: types.Message):
    """دریافت محدودیت حجمی"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    try:
        val = float(text)
        if val < 0: raise ValueError
        admin_conversations[uid]['data']['limit'] = val
        
        admin_conversations[uid]['step'] = 'get_days'
        admin_conversations[uid]['next_handler'] = get_new_user_days
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "📅 **مدت اعتبار (روز)** را وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())
    except ValueError:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "❌ لطفاً یک عدد معتبر وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_days(message: types.Message):
    """دریافت روز و پایان"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    try:
        days = int(text)
        if days < 0: raise ValueError
        admin_conversations[uid]['data']['days'] = days
        
        # پایان پروسه و ساخت کاربر
        await _finalize_user_creation(uid)
        
    except ValueError:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "❌ لطفاً یک عدد صحیح وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())

async def _finalize_user_creation(uid):
    """ارسال درخواست به سرویس و نمایش نتیجه"""
    if uid not in admin_conversations: return
    
    data_pack = admin_conversations.pop(uid)
    user_data = data_pack['data']
    msg_id = data_pack['msg_id']
    
    await _safe_edit(uid, msg_id, "⏳ در حال ساخت کاربر در پنل‌ها...", reply_markup=None)
    
    # فراخوانی سرویس (Bussiness Logic)
    result = await admin_user_service.create_user(user_data)
    
    # پردازش نتیجه برای نمایش
    final_uuid = result.get('uuid') or user_data.get('uuid')
    
    success_list = []
    for p in result.get('success', []):
        success_list.append(f"✅ {escape_markdown(p['name'])}")
        
    fail_list = []
    for p in result.get('fail', []):
        fail_list.append(f"❌ {escape_markdown(p['name'])}")
    
    report_text = (
        f"👤 کاربر جدید: `{escape_markdown(user_data['name'])}`\n"
        f"🔑 UUID: `{final_uuid}`\n"
        f"📦 حجم: {user_data['limit']} GB | 📅 مدت: {user_data['days']} روز\n"
        f"──────────────────\n"
    )
    
    if success_list:
        report_text += "\n".join(success_list) + "\n"
    
    if fail_list:
        report_text += "\n⚠️ ناموفق در:\n" + "\n".join(fail_list)
        
    if not success_list and fail_list:
        report_text += "\n🛑 عملیات در هیچ پنلی موفق نبود!"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت", callback_data="admin:management_menu"))
    
    await _safe_edit(uid, msg_id, report_text, reply_markup=kb, parse_mode="MarkdownV2")