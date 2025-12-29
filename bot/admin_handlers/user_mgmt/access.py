from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

@admin_only
async def handle_user_access_panel_list(call, params):
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    data = await admin_user_service.get_node_access_matrix(target_id)
    if not data:
        await bot.answer_callback_query(call.id, "کاربر یافت نشد.")
        return

    kb = types.InlineKeyboardMarkup()
    cat_map = data['categories']
    allowed = data['allowed_ids']
    nodes_map = {}
    for n in data['nodes']: nodes_map.setdefault(n.panel_id, []).append(n)
        
    for p in data['panels']:
        is_active = p.id in allowed
        mark, action = ("✅", "disable") if is_active else ("❌", "enable")
        flag = cat_map.get(p.category, "🏳️")
        
        kb.add(types.InlineKeyboardButton(f"{flag} {p.name} ({p.panel_type})", callback_data="noop"))
        btns = [types.InlineKeyboardButton(f"سرور اصلی {mark}", callback_data=f"admin:ptgl:{data['uuid_obj'].id}:{p.id}:{action}")]
        for n in nodes_map.get(p.id, []):
            n_flag = cat_map.get(n.country_code, "🏳️")
            btns.append(types.InlineKeyboardButton(f"{n_flag} {mark}", callback_data=f"admin:ptgl:{data['uuid_obj'].id}:{p.id}:{action}"))
        kb.row(*btns)
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{data['uuid_obj'].user_id}"))
    await _safe_edit(uid, msg_id, "⚙️ مدیریت دسترسی به نودها:", reply_markup=kb)

@admin_only
async def handle_user_access_toggle(call, params):
    uuid_db_id, panel_id, action = int(params[0]), int(params[1]), params[2]
    enable = (action == 'enable')
    if await admin_user_service.toggle_node_access(uuid_db_id, panel_id, enable):
        await bot.answer_callback_query(call.id, "✅ انجام شد.")
    else:
        await bot.answer_callback_query(call.id, "❌ خطا.")

@admin_only
async def handle_user_reset_menu(call, params):
    target_id = params[0]
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("📱 حذف دستگاه‌های متصل", callback_data=f"admin:us_ddev:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(call.from_user.id, call.message.message_id, "♻️ عملیات ویژه:", reply_markup=kb)