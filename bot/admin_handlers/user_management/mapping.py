# bot/admin_handlers/user_management/mapping.py

import time
from telebot import types
from bot.database import db
from bot.language import get_string as t
from bot.utils.formatters import escape_markdown
from bot.admin_handlers.user_management.helpers import _delete_user_message
from bot.utils.network import _safe_edit
from bot.utils.decorators import admin_only
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.bot_instance import bot

# ==============================================================================
# 1. منوی اصلی و لیست (Menu & List)
# ==============================================================================

@admin_only
async def handle_mapping_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی مدیریت اتصال‌های مرزبان"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    text = (
        f"🔗 *{escape_markdown('مدیریت اتصال‌های مرزبان')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید مشخص کنید کدام UUID در ربات به کدام Username در مرزبان متصل است.')}\n"
        f"{escape_markdown('لطفاً یک گزینه را انتخاب کنید:')}"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    btn_list = types.InlineKeyboardButton("📋 لیست اتصال‌ها", callback_data="admin:mapping_list")
    btn_add = types.InlineKeyboardButton("➕ ایجاد اتصال", callback_data="admin:add_mapping")
    
    kb.add(btn_list, btn_add)
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")


@admin_only
async def handle_mapping_list(call: types.CallbackQuery, params: list):
    """نمایش لیست خلاصه اتصال‌ها"""
    uid, msg_id = call.from_user.id, call.message.message_id
    mappings = await db.get_all_marzban_mappings()
    
    if not mappings:
        text = "📭 *لیست اتصال‌ها خالی است\.*\n\nهیچ اتصالی تعریف نشده است\."
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:mapping_menu"))
        
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")
        return

    text = "📋 *لیست اتصال‌های فعال:*\n\nبرای مشاهده جزئیات و حذف، روی نام کاربر کلیک کنید:"
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    for m in mappings:
        short_uuid = str(m['hiddify_uuid'])[:8]
        btn_text = f"👤 {m['marzban_username']} | 🆔 {short_uuid}..."
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:map_detail:{m['hiddify_uuid']}"))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:mapping_menu"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")


@admin_only
async def handle_mapping_detail(call: types.CallbackQuery, params: list):
    """Display full details of a mapping + delete button"""
    uid, msg_id = call.from_user.id, call.message.message_id
    target_uuid = params[0]
    
    username = await db.get_marzban_username_by_uuid(target_uuid)
    
    if not username:
        await bot.answer_callback_query(call.id, "❌ This mapping no longer exists.", show_alert=True)
        await handle_mapping_list(call, [])
        return

    text = (
        f"🔍 *جزئیات اتصال*\n\n"
        f"🆔 *UUID \(Hiddify\-Remnawave\):*\n`{escape_markdown(str(target_uuid))}`\n\n"
        f"👤 *Username \(Marzban\-pasarguard\):*\n`{escape_markdown(username)}`\n\n"
        f"👇 برای حذف این اتصال از گزینه زیر استفاده کنید:"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🗑 حذف اتصال", callback_data=f"admin:del_map_conf:{target_uuid}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:mapping_list"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# 2. افزودن اتصال جدید (بدون تغییر)
# ==============================================================================

@admin_only
async def handle_add_mapping_start(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id

    bot.context_state[uid] = {
        'action': 'add_marzban_mapping',
        'step': 'get_uuid',
        'msg_id': msg_id,
        'data': {},
        'next_handler': get_mapping_uuid,
        'timestamp': time.time()
    }

    prompt = escape_markdown("1️⃣ لطفاً UUID کاربر (شناسه هیدیفای) را ارسال کنید:")
    kb = await admin_menu.cancel_action("admin:mapping_menu")
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")


@admin_only
async def get_mapping_uuid(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)

    if uid not in bot.context_state: return
    
    bot.context_state[uid]['data']['target_uuid'] = text
    bot.context_state[uid]['step'] = 'get_username'
    bot.context_state[uid]['next_handler'] = get_mapping_username
    bot.context_state[uid]['timestamp'] = time.time()
    msg_id = bot.context_state[uid]['msg_id']

    prompt = "2️⃣ حالا *نام کاربری \(Username\)* متناظر در پنل مرزبان را ارسال کنید:"
    kb = await admin_menu.cancel_action("admin:mapping_menu")
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")


@admin_only
async def get_mapping_username(message: types.Message):
    uid, username = message.from_user.id, message.text.strip()
    await _delete_user_message(message)

    if uid not in bot.context_state: return
    
    target_uuid = bot.context_state[uid]['data']['target_uuid']
    msg_id = bot.context_state[uid]['msg_id']

    current_mapped_username = await db.get_marzban_username_by_uuid(target_uuid)
    current_mapped_uuid = await db.get_uuid_by_marzban_username(username)

    conflict_msg = ""
    if current_mapped_username and current_mapped_username != username:
        conflict_msg += t("marzban_mapping_conflict_uuid").format(current_username=escape_markdown(current_mapped_username)) + "\n"
    
    if current_mapped_uuid and current_mapped_uuid != str(target_uuid):
        conflict_msg += t("marzban_mapping_conflict_username").format(new_username=escape_markdown(username), existing_uuid=escape_markdown(current_mapped_uuid))

    if conflict_msg:
        bot.context_state[uid]['data']['pending_username'] = username
        bot.context_state[uid]['next_handler'] = None 
        
        full_msg = conflict_msg + t("marzban_mapping_confirm_replace")
        
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton(t("btn_cancel_replace"), callback_data="admin:confirm_map_replace:no"),
            types.InlineKeyboardButton(t("btn_confirm_replace"), callback_data="admin:confirm_map_replace:yes")
        )
        await _safe_edit(uid, msg_id, full_msg, reply_markup=kb, parse_mode="Markdown")
        return

    await _save_mapping_and_finish(uid, msg_id, target_uuid, username)


@admin_only
async def handle_confirm_map_replace(call: types.CallbackQuery, params: list):
    uid = call.from_user.id
    action = params[0]
    
    if uid not in bot.context_state:
        await bot.answer_callback_query(call.id, "نشست منقضی شد.", show_alert=True)
        return

    msg_id = bot.context_state[uid]['msg_id']

    if action == 'no':
        if uid in bot.context_state: del bot.context_state[uid]
        await _safe_edit(uid, msg_id, t("marzban_mapping_cancelled"), reply_markup=await admin_menu.cancel_action("admin:mapping_menu"))
        return

    if action == 'yes':
        data = bot.context_state[uid].get('data', {})
        await _save_mapping_and_finish(uid, msg_id, data.get('target_uuid'), data.get('pending_username'))


async def _save_mapping_and_finish(uid, msg_id, target_uuid, username):
    success = await db.add_marzban_mapping(target_uuid, username)
    if success:
        msg = t("marzban_mapping_success").format(uuid=escape_markdown(str(target_uuid)), username=escape_markdown(username))
        if uid in bot.context_state: del bot.context_state[uid]
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:mapping_menu"))
        await _safe_edit(uid, msg_id, msg, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در عملیات دیتابیس.")

# ==============================================================================
# 3. حذف اتصال (Delete Flow)
# ==============================================================================

@admin_only
async def handle_delete_mapping_confirm(call: types.CallbackQuery, params: list):
    """تایید حذف"""
    uid, msg_id = call.from_user.id, call.message.message_id
    target_uuid = params[0]
    
    prompt = (
        f"⚠️ *هشدار حذف*\n\n"
        f"آیا مطمئن هستید که می‌خواهید اتصال زیر را حذف کنید؟\n"
        f"UUID: `{escape_markdown(str(target_uuid))}`"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:del_map_exec:{target_uuid}"))
    kb.add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:map_detail:{target_uuid}"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_delete_mapping_execute(call: types.CallbackQuery, params: list):
    """اجرای حذف"""
    target_uuid = params[0]
    await db.delete_marzban_mapping(target_uuid)
    await bot.answer_callback_query(call.id, "✅ با موفقیت حذف شد.")
    await handle_mapping_list(call, [])