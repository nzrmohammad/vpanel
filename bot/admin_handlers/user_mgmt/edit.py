# bot/admin_handlers/user_mgmt/edit.py

import time
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.database import db
from bot import combined_handler 
from .search import show_user_summary # استفاده از تابع نمایش از فایل search

# متغیرهای سراسری ماژول
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
# 1. ویرایش سرویس (Edit Volume/Days)
# ==============================================================================

@admin_only
async def handle_edit_user_menu(call: types.CallbackQuery, params: list):
    """منوی انتخاب پنل برای ویرایش"""
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

    # افزودن پنل‌هایی که کاربر در آنها سرویس دارد
    if info and 'breakdown' in info:
        for p_name in info['breakdown'].keys():
            p_cfg = next((p for p in active_panels if p['name'] == p_name), None)
            flag = cat_map.get(p_cfg.get('category'), "") if p_cfg else ""
            user_panels.append({'name': p_name, 'id': p_name, 'flag': flag})

    markup = await admin_menu.edit_user_panel_select_menu(target_id, user_panels)
    await _safe_edit(uid, msg_id, "🔧 **ویرایش کاربر**\nپنل مورد نظر را انتخاب کنید:", reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_select_panel_for_edit(call: types.CallbackQuery, params: list):
    """انتخاب نوع ویرایش (حجم یا روز)"""
    panel_target, identifier = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    markup = await admin_menu.edit_user_action_menu(identifier, panel_target)
    panel_display = "همه پنل‌ها" if panel_target == 'all' else panel_target
    
    await _safe_edit(uid, msg_id, f"🔧 ویرایش روی: **{escape_markdown(panel_display)}**\nچه تغییری اعمال شود؟", reply_markup=markup, parse_mode="Markdown")

@admin_only
async def handle_ask_edit_value(call: types.CallbackQuery, params: list):
    """درخواست مقدار جدید"""
    action, panel_target, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    
    admin_conversations[uid] = {
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

@admin_only
async def process_edit_value(message: types.Message):
    """اجرای تغییرات ویرایش"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    msg_id, target_id = data['msg_id'], data['target_id']
    action, panel_target = data['action'], data['scope']
    
    try:
        value = float(text)
        if value == 0: raise ValueError
    except:
        await _safe_edit(uid, msg_id, "❌ مقدار نامعتبر.", reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
        return

    await _safe_edit(uid, msg_id, "⏳ اعمال تغییرات...", reply_markup=None)
    
    # استفاده از سرویس برای تغییرات
    success = await admin_user_service.modify_user_resources(
        int(target_id), panel_target, action, value
    )
    
    res_text = f"✅ انجام شد: {value}" if success else "❌ خطا در انجام عملیات."
    markup = await admin_menu.edit_user_action_menu(str(target_id), panel_target)    
    await _safe_edit(uid, msg_id, res_text, reply_markup=markup)

# ==============================================================================
# 2. تغییر وضعیت (Toggle Status)
# ==============================================================================

@admin_only
async def handle_toggle_status(call: types.CallbackQuery, params: list):
    """منوی انتخاب تغییر وضعیت (سراسری یا پنل خاص)"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "❌ سرویسی یافت نشد.", show_alert=True)
        return

    uuid_str = str(uuids[0]['uuid'])
    await _safe_edit(uid, msg_id, "⏳ در حال استعلام وضعیت...", reply_markup=None, parse_mode=None)
    
    # دریافت وضعیت لایو
    combined_info = await combined_handler.get_combined_user_info(uuid_str)
    
    global_is_active = uuids[0]['is_active']
    status_text = 'فعال' if global_is_active else 'غیرفعال'
    
    text = (
        f"⚙️ *مدیریت وضعیت کاربر*\n\n"
        f"وضعیت کلی در دیتابیس: *{status_text}*\n\n"
        f"👇 برای تغییر وضعیت، گزینه مورد نظر را انتخاب کنید:"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # دکمه سراسری
    global_next = "disable" if global_is_active else "enable"
    global_lbl = "🔴 غیرفعال‌سازی سراسری" if global_is_active else "🟢 فعال‌سازی سراسری"
    kb.add(types.InlineKeyboardButton(global_lbl, callback_data=f"admin:tglA:{global_next}:{target_id}:all"))

    # دکمه‌های پنلی
    panel_buttons = []
    if combined_info and 'breakdown' in combined_info:
        active_panels = await db.get_active_panels()
        panel_map = {p['name']: p for p in active_panels}

        for panel_name, details in combined_info['breakdown'].items():
            panel_db = panel_map.get(panel_name)
            if not panel_db: continue

            p_data = details.get('data', {})
            # منطق تشخیص فعال بودن در پنل
            p_is_active = (p_data.get('status') == 'active') or (p_data.get('enable') == True) or (p_data.get('is_active') == True)
            
            btn_action = "disable" if p_is_active else "enable"
            btn_icon = "🔴" if p_is_active else "🟢"
            
            panel_buttons.append(types.InlineKeyboardButton(
                f"{btn_icon} {panel_name}", 
                callback_data=f"admin:tglA:{btn_action}:{target_id}:{panel_db['id']}"
            ))

    if panel_buttons: kb.add(*panel_buttons)
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")

@admin_only
async def handle_toggle_status_action(call: types.CallbackQuery, params: list):
    """اجرای تغییر وضعیت"""
    action, target_id, scope = params[0], int(params[1]), params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    await _safe_edit(uid, msg_id, "⏳ در حال اعمال...", reply_markup=None)
    
    res = await admin_user_service.toggle_user_status(target_id, action, scope)
    
    status_fa = "فعال" if res.get('status_bool') else "غیرفعال"
    msg = f"✅ وضعیت به **{status_fa}** تغییر کرد.\nتعداد سرورهای موفق: {res.get('count', 0)}"
    
    # بازگشت به منوی تاگل برای دیدن تغییرات
    fake_params = [target_id]
    await handle_toggle_status(call, fake_params)

# ==============================================================================
# 3. حذف کاربر (Delete User)
# ==============================================================================

@admin_only
async def handle_delete_user_confirm(call: types.CallbackQuery, params: list):
    """درخواست تایید حذف"""
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
    await _safe_edit(call.from_user.id, call.message.message_id, 
                     f"⚠️ *هشدار:* حذف کاربر `{target_id}` باعث حذف تمام سوابق و قطع دسترسی او می‌شود\.\nآیا مطمئن هستید؟", 
                     reply_markup=markup, parse_mode="MarkdownV2")

@admin_only
async def handle_delete_user_action(call: types.CallbackQuery, params: list):
    """اجرای حذف کامل"""
    decision, target_id = params[0], params[2]
    uid = call.from_user.id
    
    if decision == 'cancel':
        await show_user_summary(uid, call.message.message_id, int(target_id))
        return
        
    await admin_user_service.purge_user(int(target_id))
    
    # بازگشت به لیست پنل‌ها
    await _safe_edit(uid, call.message.message_id, "✅ کاربر حذف شد.", reply_markup=await admin_menu.management_menu([]))

@admin_only
async def handle_delete_user_from_panel(call: types.CallbackQuery, params: list):
    """حذف کاربر فقط از یک پنل خاص (Placeholder)"""
    await bot.answer_callback_query(call.id, "این قابلیت در حال حاضر غیرفعال است.")