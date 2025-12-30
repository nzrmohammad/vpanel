# bot/admin_handlers/user_management/editing.py

import time
from telebot import types

# ایمپورت‌های پروژه
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot import combined_handler

# ایمپورت‌های ماژولار
from bot.bot_instance import bot  # ایمپورت بات اصلی
from bot.admin_handlers.user_management import state  # ایمپورت ماژول state
from bot.admin_handlers.user_management.helpers import _delete_user_message

# ==============================================================================
# 4. ویرایش سرویس (Edit User - Volume/Days)
# ==============================================================================

async def handle_edit_user_menu(call, params):
    """نمایش منوی انتخاب پنل برای ویرایش"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
        return
    uuid_str = str(uuids[0]['uuid'])
    info = await combined_handler.get_combined_user_info(uuid_str)
    
    active_panels = await db.get_active_panels()
    categories = await db.get_server_categories()
    cat_map = {c['code']: c['emoji'] for c in categories}
    user_panels = [{'name': 'همه پنل‌ها', 'id': 'all', 'flag': '🌐'}]

    if info and 'breakdown' in info:
        for p_name in info['breakdown'].keys():
            p_cfg = next((p for p in active_panels if p['name'] == p_name), None)
            flag = cat_map.get(p_cfg.get('category'), "") if p_cfg else ""
            user_panels.append({'name': p_name, 'id': p_name, 'flag': flag})

    markup = await admin_menu.edit_user_panel_select_menu(target_id, user_panels)
    await _safe_edit(uid, msg_id, "🔧 **ویرایش کاربر**\nپنل مورد نظر را انتخاب کنید:", reply_markup=markup, parse_mode="Markdown")

async def handle_select_panel_for_edit(call, params):
    """نمایش منوی انتخاب نوع ویرایش (حجم یا روز)"""
    panel_target, identifier = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    markup = await admin_menu.edit_user_action_menu(identifier, panel_target)
    panel_display = "همه پنل‌ها" if panel_target == 'all' else panel_target
    
    await _safe_edit(uid, msg_id, f"🔧 ویرایش روی: **{escape_markdown(panel_display)}**\nچه تغییری اعمال شود؟", reply_markup=markup, parse_mode="Markdown")

async def handle_ask_edit_value(call, params):
    """درخواست مقدار عددی از ادمین"""
    action, panel_target, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    
    state.admin_conversations[uid] = {
        'step': 'edit_value', 
        'msg_id': msg_id, 
        'action': action, 
        'scope': panel_target,
        'target_id': target_id, 
        'timestamp': time.time(), 
        'next_handler': process_edit_value
    }
    
    await _safe_edit(uid, msg_id, f"🔢 مقدار *{action_name}* را وارد کنید (مثبت برای افزودن، منفی برای کسر):", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"), parse_mode="Markdown")

async def process_edit_value(message: types.Message):
    """پردازش مقدار وارد شده و اعمال تغییرات"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in state.admin_conversations: return
    
    data = state.admin_conversations.pop(uid)
    msg_id, target_id = data['msg_id'], data['target_id']
    action, panel_target = data['action'], data['scope']
    
    try:
        value = float(text)
        if value == 0: raise ValueError
    except:
        await _safe_edit(uid, msg_id, "❌ مقدار نامعتبر.", reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))
        return

    await _safe_edit(uid, msg_id, "⏳ اعمال تغییرات...", reply_markup=None)
    
    uuids = await db.uuids(int(target_id))
    if not uuids: return
    
    main_uuid_str = str(uuids[0]['uuid'])
    add_gb = value if 'gb' in action else 0
    add_days = int(value) if 'days' in action else 0
    target_name = panel_target if panel_target != 'all' else None
    
    # اعمال تغییرات روی پنل‌ها
    success = await combined_handler.modify_user_on_all_panels(
        main_uuid_str, 
        add_gb=add_gb, 
        add_days=add_days, 
        target_panel_name=target_name
    )
    
    res_text = f"✅ انجام شد: {value}" if success else "❌ خطا در انجام عملیات."
    markup = await admin_menu.edit_user_action_menu(target_id, panel_target)    
    await _safe_edit(uid, msg_id, res_text, reply_markup=markup)