# bot/admin_handlers/user_management/status.py

import logging
from telebot import types
from sqlalchemy import update

from bot.database import db
from bot.db.base import UserUUID
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot import combined_handler
from bot.services.panels import PanelFactory

# ایمپورت‌های ماژولار
from bot.admin_handlers.user_management.state import bot

logger = logging.getLogger(__name__)

async def handle_toggle_status(call, params):
    """
    منوی تغییر وضعیت هوشمند و داینامیک (دو ردیفه) با اصلاح MarkdownV2.
    """
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # 1. دریافت اطلاعات کاربر از دیتابیس
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "❌ سرویسی یافت نشد.", show_alert=True)
        return

    uuid_str = str(uuids[0]['uuid'])
    
    # 2. نمایش وضعیت "در حال بارگذاری"
    await _safe_edit(uid, msg_id, "⏳ در حال استعلام وضعیت از سرورها...", reply_markup=None, parse_mode=None)
    
    # 3. دریافت اطلاعات ترکیبی (لایو) از سرورها
    combined_info = await combined_handler.get_combined_user_info(uuid_str)
    
    # 4. تعیین وضعیت کلی در دیتابیس ربات
    global_is_active = uuids[0]['is_active']
    status_icon = "🟢" if global_is_active else "🔴"
    status_text = 'فعال' if global_is_active else 'غیرفعال'
    
    header = escape_markdown("مدیریت وضعیت کاربر")
    db_status_label = escape_markdown("وضعیت کلی در دیتابیس")
    status_val = escape_markdown(status_text)
    prompt = escape_markdown("برای تغییر وضعیت، گزینه مورد نظر را انتخاب کنید:")
    
    text = (
        f"⚙️ *{header}*\n\n"
        f"{status_icon} {db_status_label}: *{status_val}*\n\n"
        f"👇 {prompt}"
    )
    
    # 6. ساخت دکمه‌ها
    kb = types.InlineKeyboardMarkup(row_width=2)

    # دکمه تغییر وضعیت سراسری
    global_action_text = "🔴 غیرفعال‌سازی سراسری (همه)" if global_is_active else "🟢 فعال‌سازی سراسری (همه)"
    global_next_action = "disable" if global_is_active else "enable"
    kb.add(types.InlineKeyboardButton(global_action_text, callback_data=f"admin:tglA:{global_next_action}:{target_id}:all"))

    # دکمه‌های وضعیت تک‌تک پنل‌ها
    panel_buttons = []

    if combined_info and 'breakdown' in combined_info:
        active_panels = await db.get_active_panels()
        panel_map = {p['name']: p for p in active_panels}

        for panel_name, details in combined_info['breakdown'].items():
            panel_db = panel_map.get(panel_name)
            if not panel_db: continue

            p_data = details.get('data', {})
            p_is_active = (p_data.get('status') == 'active') or (p_data.get('enable') == True) or (p_data.get('is_active') == True)
            
            if p_is_active:
                btn_text = f"🔴 {panel_name}" # دکمه برای غیرفعال کردن
                btn_action = "disable"
            else:
                btn_text = f"🟢 {panel_name}" # دکمه برای فعال کردن
                btn_action = "enable"
            
            panel_buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:tglA:{btn_action}:{target_id}:{panel_db['id']}"))

    if panel_buttons:
        kb.add(*panel_buttons)

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_toggle_status_action(call, params):
    """اجرای عملیات تغییر وضعیت (سراسری یا تکی)"""
    action = params[0]
    target_id = params[1]
    scope = params[2] if len(params) > 2 else 'all' 

    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
        return
        
    uuid_str = str(uuids[0]['uuid'])
    uuid_id = uuids[0]['id']
    
    await _safe_edit(uid, msg_id, "⏳ در حال اعمال تغییرات...", reply_markup=None)

    new_status_bool = (action == 'enable')
    success_count = 0
    target_panels = []

    if scope == 'all':
        async with db.get_session() as session:
            stmt = update(UserUUID).where(UserUUID.id == uuid_id).values(is_active=new_status_bool)
            await session.execute(stmt)
            await session.commit()
        target_panels = await db.get_active_panels()
    else:
        try:
            panel_id = int(scope)
            panel = await db.get_panel_by_id(panel_id)
            if panel: target_panels = [panel]
        except ValueError: pass

    for p in target_panels:
        try:
            handler = await PanelFactory.get_panel(p['name'])
            identifier = uuid_str
            if p['panel_type'] == 'marzban':
                mapping = await db.get_marzban_username_by_uuid(uuid_str)
                identifier = mapping if mapping else uuid_str

            if await _toggle_panel_user_status(handler, p['panel_type'], identifier, action):
                success_count += 1
        except Exception as e:
            logger.error(f"Error toggling status on {p['name']}: {e}")

    action_fa = "فعال" if new_status_bool else "غیرفعال"
    
    if scope == 'all':
        msg = f"✅ وضعیت کاربر به *{action_fa}* تغییر کرد (سراسری).\n📊 اعمال شده روی {success_count} سرور."
    else:
        p_name = target_panels[0]['name'] if target_panels else "پنل انتخاب شده"
        msg = f"✅ کاربر در سرور *{escape_markdown(p_name)}* {action_fa} شد."

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت وضعیت", callback_data=f"admin:us_tgl:{target_id}"))
    kb.add(types.InlineKeyboardButton("👤 پروفایل کاربر", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, msg, reply_markup=kb, parse_mode="Markdown")

async def _toggle_panel_user_status(handler, panel_type, identifier, action):
    """تابع کمکی برای ارسال درخواست به API پنل‌ها"""
    try:
        if panel_type == 'marzban':
            status_val = "active" if action == 'enable' else "disabled"
            payload = {"status": status_val}
            return await handler._request("PUT", f"user/{identifier}", json=payload) is not None

        elif panel_type == 'hiddify':
            is_enable = (action == 'enable')
            payload = {"enable": is_enable, "is_active": is_enable, "mode": "no_reset"}
            return await handler._request("PATCH", f"user/{identifier}", json=payload) is not None

        elif panel_type == 'remnawave':
            status_val = "ACTIVE" if action == 'enable' else "DISABLED"
            payload = {"status": status_val}
            return await handler._request("PATCH", f"api/users/{identifier}", json=payload) is not None

    except Exception as e:
        logger.error(f"Failed to toggle status API: {e}")
        return False