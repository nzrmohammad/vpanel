# bot/admin_handlers/user_management/status.py

import logging
from telebot import types
from sqlalchemy import update, select  # ✅ اضافه شدن select

from bot.database import db
from bot.db.base import UserUUID
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot import combined_handler
from bot.services.panels import PanelFactory
from bot.services import cache_manager  # مدیریت کش

# ایمپورت‌های ماژولار
from bot.bot_instance import bot
from bot.admin_handlers.user_management import state

logger = logging.getLogger(__name__)

async def handle_toggle_status(call, params):
    """
    منوی تغییر وضعیت هوشمند.
    """
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # 1. دریافت اطلاعات کاربر از دیتابیس (اصلاح شده: دریافت همه رکوردها حتی غیرفعال‌ها)
    # قبلاً db.uuids() فقط فعال‌ها را می‌داد که باعث باگ می‌شد.
    uuids = []
    async with db.get_session() as session:
        stmt = select(UserUUID).where(UserUUID.user_id == int(target_id))
        result = await session.execute(stmt)
        rows = result.scalars().all()
        # تبدیل به دیکشنری برای سازگاری با کدهای قبلی
        uuids = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]

    if not uuids:
        await bot.answer_callback_query(call.id, "❌ سرویسی یافت نشد.", show_alert=True)
        return

    uuid_str = str(uuids[0]['uuid'])
    
    # 2. دریافت اطلاعات از کش
    combined_info = await combined_handler.get_combined_user_info(uuid_str)
    
    # 3. تعیین وضعیت کلی
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
    
    # 4. ساخت دکمه‌ها
    kb = types.InlineKeyboardMarkup(row_width=2)

    # دکمه سراسری
    if global_is_active:
        global_action_text = "⚡️ غیرفعال‌سازی سراسری (همه)"
        global_next_action = "disable"
    else:
        global_action_text = "⚡️ فعال‌سازی سراسری (همه)"
        global_next_action = "enable"

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
            
            # تشخیص وضعیت
            p_is_active = False
            if p_data.get('status') == 'active': p_is_active = True
            elif p_data.get('status') == 'disabled': p_is_active = False
            elif p_data.get('enable') is True: p_is_active = True
            elif p_data.get('enable') is False: p_is_active = False
            elif p_data.get('is_active') is True: p_is_active = True
            
            # رنگ‌بندی: سبز=فعال، قرمز=غیرفعال
            if p_is_active:
                btn_text = f"🟢 {panel_name}"
                btn_action = "disable"
            else:
                btn_text = f"🔴 {panel_name}"
                btn_action = "enable"
            
            panel_buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:tglA:{btn_action}:{target_id}:{panel_db['id']}"))

    if panel_buttons:
        kb.add(*panel_buttons)

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_toggle_status_action(call, params):
    """اجرای عملیات تغییر وضعیت"""
    action = params[0]
    target_id = params[1]
    scope = params[2] if len(params) > 2 else 'all' 

    # اصلاح شده: دریافت همه رکوردها حتی غیرفعال‌ها
    uuids = []
    async with db.get_session() as session:
        stmt = select(UserUUID).where(UserUUID.user_id == int(target_id))
        result = await session.execute(stmt)
        rows = result.scalars().all()
        uuids = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]

    if not uuids:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
        return
        
    uuid_str = str(uuids[0]['uuid'])
    uuid_id = uuids[0]['id']
    
    new_status_bool = (action == 'enable')
    target_panels = []

    # 1. آپدیت دیتابیس
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

    # 2. ارسال درخواست به پنل‌ها
    success_count = 0
    updated_panel_names = []
    
    for p in target_panels:
        try:
            handler = await PanelFactory.get_panel(p['name'])
            identifier = uuid_str
            if p['panel_type'] == 'marzban':
                mapping = await db.get_marzban_username_by_uuid(uuid_str)
                identifier = mapping if mapping else uuid_str

            if await _toggle_panel_user_status(handler, p['panel_type'], identifier, action):
                success_count += 1
                updated_panel_names.append(p['name'])
        except Exception as e:
            logger.error(f"Error toggling status on {p['name']}: {e}")

    # 3. بازخورد
    status_fa = "فعال" if new_status_bool else "غیرفعال"
    feedback = f"وضعیت {status_fa} شد ✅"
    if scope != 'all' and success_count == 0:
        feedback = "⚠️ خطا: تغییری اعمال نشد"
    
    await bot.answer_callback_query(call.id, feedback, show_alert=False)

    # 4. آپدیت هوشمند کش (In-Memory Patch)
    try:
        cached_data = await cache_manager.get_data()
        user_in_cache = next((u for u in cached_data if str(u.get('uuid')) == uuid_str), None)
        
        if user_in_cache:
            # اگر سراسری بود
            if scope == 'all':
                user_in_cache['is_active'] = new_status_bool
            
            # آپدیت پنل‌های خاص در کش
            if 'breakdown' in user_in_cache:
                for p_name in updated_panel_names:
                    if p_name in user_in_cache['breakdown']:
                        p_data = user_in_cache['breakdown'][p_name].get('data', {})
                        if new_status_bool: # Enable
                            p_data['status'] = 'active'
                            p_data['enable'] = True
                            p_data['is_active'] = True
                        else: # Disable
                            p_data['status'] = 'disabled'
                            p_data['enable'] = False
                            p_data['is_active'] = False

    except Exception as e:
        logger.error(f"Manual cache patch failed: {e}")

    # 5. رفرش منو
    await handle_toggle_status(call, [target_id])

async def _toggle_panel_user_status(handler, panel_type, identifier, action):
    """تابع کمکی درخواست API"""
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
            # اصلاح شده برای اکشن‌های جدید
            endpoint_action = "enable" if action == 'enable' else "disable"
            return await handler._request("POST", f"users/{identifier}/actions/{endpoint_action}") is not None

    except Exception as e:
        logger.error(f"Failed to toggle status API: {e}")
        return False