from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.formatters import user_formatter
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.database import db

# متغیرهای مشترک (در __init__ مقداردهی می‌شوند)
bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

@admin_only
async def handle_global_search_convo(call, params):
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'global_search', 'msg_id': msg_id, 'next_handler': process_search_input}
    await _safe_edit(uid, msg_id, "🔎 لطفاً نام، یوزرنیم یا UUID را وارد کنید:", 
                     reply_markup=await admin_menu.cancel_action("admin:search_menu"))

@admin_only
async def handle_search_by_telegram_id_convo(call, params):
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'tid_search', 'msg_id': msg_id, 'next_handler': process_search_input}
    await _safe_edit(uid, msg_id, "🆔 آیدی عددی تلگرام را وارد کنید:", 
                     reply_markup=await admin_menu.cancel_action("admin:search_menu"))

@admin_only
async def process_search_input(message: types.Message):
    uid, query = message.from_user.id, message.text.strip()
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    search_type = 'telegram_id' if data['step'] == 'tid_search' else 'global'
    
    users = await admin_user_service.search_users(query, search_type)

    if not users:
        await _safe_edit(uid, data['msg_id'], f"❌ کاربری یافت نشد: {escape_markdown(query)}", 
                         reply_markup=await admin_menu.search_menu())
        return
    
    if len(users) == 1:
        await show_user_summary(uid, data['msg_id'], users[0].user_id)
    else:
        text = f"🔍 نتایج جستجو ({len(users)} مورد):"
        kb = types.InlineKeyboardMarkup(row_width=1)
        for u in users[:10]:
            display = f"{u.first_name or 'NoName'} (@{u.username or 'NoUser'})"
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:us:{u.user_id}:s"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:search_menu"))
        await _safe_edit(uid, data['msg_id'], text, reply_markup=kb)

@admin_only
async def handle_show_user_summary(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    if not str(target_id).isdigit():
        real_id = await db.get_user_id_by_uuid(target_id)
        if real_id: target_id = real_id
    await show_user_summary(uid, msg_id, int(target_id), params[1] if len(params)>1 else None)

async def show_user_summary(admin_id, msg_id, target_user_id, context=None, extra_message=None):
    data = await admin_user_service.get_user_profile_data(target_user_id)
    if not data or not data['user']:
        await _safe_edit(admin_id, msg_id, "❌ کاربر یافت نشد.", reply_markup=await admin_menu.main())
        return

    user = data['user']
    info = data['combined_info']
    safe_name = escape_markdown(user.first_name or 'Unknown')
    
    if info:
        formatted_body = await user_formatter.profile_info(info, 'fa')
        lines = formatted_body.split('\n')
        status_emoji = "✅" if info.get('is_active') else "❌"
        lines[0] = f"👤 نام: {safe_name} ({status_emoji} | {data['payment_count']} پرداخت)"
        lines.append("──────────────────")
        if user.admin_note: lines.append(f"📝 یادداشت: {escape_markdown(user.admin_note)}")
        lines.append(f"🆔 آیدی: `{target_user_id}`")
        lines.append(f"💰 کیف پول: `{int(user.wallet_balance or 0):,} تومان`")
        text = "\n".join(lines)
    else:
        text = f"👤 کاربر: {safe_name}\n🔴 وضعیت: غیرفعال (بدون سرویس)\n🆔 `{target_user_id}`"

    if extra_message: text += f"\n\n{extra_message}"
    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    markup = await admin_menu.user_interactive_menu(str(target_user_id), bool(data['active_uuids']), 'hiddify', back_callback=back_cb)
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")