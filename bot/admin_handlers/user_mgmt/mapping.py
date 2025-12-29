# bot/admin_handlers/user_mgmt/mapping.py

import time
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.utils.decorators import admin_only
from bot.database import db

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

@admin_only
async def handle_mapping_menu(call: types.CallbackQuery, params: list):
    """منوی اصلی مدیریت اتصال"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    text = (
        f"🔗 *{escape_markdown('مدیریت اتصال‌های مرزبان')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید مشخص کنید کدام UUID در ربات به کدام Username در مرزبان متصل است.')}\n"
        "لطفاً یک گزینه را انتخاب کنید:"
    )
    
    markup = await admin_menu.mapping_main_menu()
    await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

@admin_only
async def handle_mapping_list(call: types.CallbackQuery, params: list):
    """لیست اتصالات"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    page = int(params[0]) if params else 0
    PAGE_SIZE = 10 
    
    all_mappings = await db.get_all_marzban_mappings()
    total_count = len(all_mappings)
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_mappings = all_mappings[start_idx:end_idx]
    
    markup = await admin_menu.mapping_list_menu(current_mappings, page, total_count, PAGE_SIZE)
    
    text = f"📋 *لیست اتصال‌ها ({total_count} مورد)*\n\n"
    if not current_mappings:
        text += "⚠️ موردی یافت نشد."
        
    await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

@admin_only
async def handle_add_mapping_start(call: types.CallbackQuery, params: list):
    """شروع افزودن مپ"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'get_map_uuid',
        'msg_id': msg_id,
        'next_handler': get_mapping_uuid_step
    }
    
    prompt = "1️⃣ لطفاً **UUID کاربر** را ارسال کنید:"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:mapping_menu"), parse_mode="Markdown")

@admin_only
async def get_mapping_uuid_step(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['uuid'] = text
    admin_conversations[uid]['next_handler'] = get_mapping_username_step
    
    msg_id = admin_conversations[uid]['msg_id']
    prompt = "2️⃣ حالا **نام کاربری (Username)** متناظر در مرزبان را ارسال کنید:"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:mapping_menu"), parse_mode="Markdown")

@admin_only
async def get_mapping_username_step(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    data = admin_conversations.pop(uid)
    uuid_str, username = data['uuid'], text
    
    success = await db.add_marzban_mapping(uuid_str, username)
    if success:
        msg = f"✅ اتصال ایجاد شد.\nUUID: `{uuid_str}`\nUser: `{username}`"
    else:
        msg = "❌ خطا: اتصال تکراری یا نامعتبر."
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("بازگشت", callback_data="admin:mapping_list:0"))
    await _safe_edit(uid, data['msg_id'], msg, reply_markup=kb, parse_mode="Markdown")

@admin_only
async def handle_delete_mapping_confirm(call: types.CallbackQuery, params: list):
    """تایید حذف مپ"""
    uuid_str = params[0]
    page = int(params[1]) if len(params) > 1 else 0
    markup = await admin_menu.confirm_delete_mapping_menu(uuid_str, page)
    await _safe_edit(call.from_user.id, call.message.message_id, f"⚠️ حذف اتصال `{uuid_str}`؟", reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_delete_mapping_execute(call: types.CallbackQuery, params: list):
    """اجرای حذف مپ"""
    uuid_str, page = params[0], int(params[1])
    await db.delete_marzban_mapping(uuid_str)
    await bot.answer_callback_query(call.id, "✅ حذف شد.")
    await handle_mapping_list(call, [page])