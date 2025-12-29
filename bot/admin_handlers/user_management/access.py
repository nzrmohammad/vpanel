# bot/admin_handlers/user_management/access.py

import time
from telebot import types
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database import db
from bot.db.base import User, UserUUID, Panel, PanelNode, ServerCategory
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.services.panels import PanelFactory

# ایمپورت‌های ماژولار
from bot.admin_handlers.user_management.state import bot, admin_conversations
from bot.admin_handlers.user_management.helpers import _delete_user_message

# ==============================================================================
# 1. Marzban Mapping
# ==============================================================================

async def handle_mapping_menu(call: types.CallbackQuery, params: list):
    """منوی اصلی مدیریت اتصال"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    text = (
        f"🔗 *{escape_markdown('مدیریت اتصال‌های مرزبان')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید مشخص کنید کدام UUID در ربات به کدام Username در مرزبان متصل است.')}\n"
        f"{escape_markdown('لطفاً یک گزینه را انتخاب کنید:')}"
    )
    markup = await admin_menu.mapping_main_menu()
    await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

async def handle_mapping_list(call: types.CallbackQuery, params: list):
    """نمایش لیست اتصالات موجود"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    page = int(params[0]) if params else 0
    PAGE_SIZE = 10 
    
    all_mappings = await db.get_all_marzban_mappings()
    total_count = len(all_mappings)
    
    total_pages = 1 if total_count == 0 else ((total_count - 1) // PAGE_SIZE) + 1
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_mappings = all_mappings[start_idx:end_idx]
    
    markup = await admin_menu.mapping_list_menu(current_mappings, page, total_count, PAGE_SIZE)
    
    text = f"📋 *{escape_markdown('لیست اتصال‌های موجود')}*\n\n"
    if not current_mappings: text += escape_markdown("⚠️ هیچ اتصالی یافت نشد.")
    if total_pages > 1: text += f"\n📄 *{escape_markdown(f'صفحه {page + 1} از {total_pages}')}*"
        
    await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

async def handle_add_mapping_start(call: types.CallbackQuery, params: list):
    """شروع پروسه افزودن مپ جدید"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'get_map_uuid',
        'msg_id': msg_id,
        'timestamp': time.time(), 
        'next_handler': get_mapping_uuid_step
    }
    
    prompt = f"1️⃣ {escape_markdown('لطفاً UUID کاربر (شناسه هیدیفای) را ارسال کنید:')}"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:mapping_menu"))

async def get_mapping_uuid_step(message: types.Message):
    """مرحله دوم: دریافت UUID"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    if len(text) < 20: 
        msg_id = admin_conversations[uid]['msg_id']
        error_msg = escape_markdown("❌ فرمت UUID صحیح نیست. مجدد ارسال کنید:")
        await _safe_edit(uid, msg_id, error_msg, reply_markup=await admin_menu.cancel_action("admin:mapping_menu"))
        return

    admin_conversations[uid]['uuid'] = text
    admin_conversations[uid]['next_handler'] = get_mapping_username_step
    msg_id = admin_conversations[uid]['msg_id']
    
    prompt = f"2️⃣ {escape_markdown('حالا نام کاربری (Username) متناظر در مرزبان را ارسال کنید:')}"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:mapping_menu"))

async def get_mapping_username_step(message: types.Message):
    """مرحله سوم افزودن: دریافت نام کاربری و ذخیره"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    uuid_str = data['uuid']
    msg_id = data['msg_id']
    
    if await db.add_marzban_mapping(uuid_str, text):
        success_msg = f"✅ {escape_markdown('اتصال با موفقیت ایجاد شد.')}\n\nUUID: `{escape_markdown(uuid_str)}`\nMarzban: `{escape_markdown(text)}`"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:mapping_list:0"))
        await _safe_edit(uid, msg_id, success_msg, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        error_msg = escape_markdown("خطا: این اتصال ممکن است تکراری باشد یا UUID نامعتبر است.")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:mapping_menu"))
        await _safe_edit(uid, msg_id, f"❌ {error_msg}", reply_markup=kb, parse_mode="MarkdownV2")

async def handle_delete_mapping_confirm(call: types.CallbackQuery, params: list):
    """مرحله اول حذف: نمایش تاییدیه"""
    uuid_str = params[0]
    page = int(params[1]) if len(params) > 1 else 0
    marzban_user = await db.get_marzban_username_by_uuid(uuid_str) or "ناشناس"
    
    prompt = (
        f"⚠️ *{escape_markdown('حذف اتصال')}*\n\n"
        f"{escape_markdown('آیا مطمئن هستید می‌خواهید اتصال زیر را حذف کنید؟')}\n"
        f"UUID: `{escape_markdown(uuid_str)}`\n"
        f"Marzban: `{escape_markdown(marzban_user)}`"
    )
    markup = await admin_menu.confirm_delete_mapping_menu(uuid_str, page)
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=markup, parse_mode="MarkdownV2")

async def handle_delete_mapping_execute(call: types.CallbackQuery, params: list):
    """اجرای حذف"""
    uuid_str = params[0]
    page = int(params[1]) if len(params) > 1 else 0
    
    if await db.delete_marzban_mapping(uuid_str):
        await bot.answer_callback_query(call.id, "✅ اتصال حذف شد.")
        await handle_mapping_list(call, [page])
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در حذف.", show_alert=True)
        await handle_mapping_list(call, [page])

# ==============================================================================
# 2. Panel Management & Listings
# ==============================================================================

async def handle_manage_single_panel_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی مدیریت برای یک سرور خاص"""
    panel_id = int(params[0])
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.", show_alert=True)
        return

    text = (
        f"👥 *مدیریت کاربران \- {escape_markdown(panel['name'])}*\n\n"
        f"لطفاً یک گزینه را انتخاب کنید:"
    )
    markup = await admin_menu.manage_single_panel_menu(panel['id'], panel['panel_type'], panel['name'])
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=markup, parse_mode="MarkdownV2")

async def handle_panel_users_list(call: types.CallbackQuery, params: list):
    """نمایش لیست کاربران یک پنل خاص"""
    if len(params) == 3 and params[0] == 'panel_users':
        panel_id = int(params[1])
        page = int(params[2])
    else:
        panel_id = int(params[0])
        page = int(params[1])

    PAGE_SIZE = 25
    panel = await db.get_panel_by_id(panel_id)
    if not panel: return

    try:
        panel_api = await PanelFactory.get_panel(panel['name'])
        users = await panel_api.get_all_users()
        users.sort(key=lambda x: x.get('expire') or x.get('package_days') or 0, reverse=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا در اتصال به پنل.")
        return

    total_count = len(users)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0
    
    current_users = users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    lines = [f"\(صفحه {page + 1} از {total_pages} \| کل: {total_count}\)\n"]
    current_time = time.time()
    
    for u in current_users:
        name = u.get('username') or u.get('name') or "بی‌نام"
        expire_val = u.get('expire')
        package_days = u.get('package_days')
        start_date = u.get('start_date')
        status_str = "نامحدود"
        
        if expire_val and isinstance(expire_val, (int, float)) and expire_val > 100_000:
            if expire_val > current_time:
                status_str = f"{int((expire_val - current_time) / 86400)} روز"
            else: status_str = "منقضی"
        elif package_days is not None:
            try:
                p_days = int(package_days)
                if start_date:
                    s_date_str = str(start_date).split(' ')[0]
                    s_dt = datetime.strptime(s_date_str, "%Y-%m-%d").timestamp()
                    days_passed = int((current_time - s_dt) / 86400)
                    rem_days = p_days - days_passed
                    status_str = f"{rem_days} روز" if rem_days > 0 else "منقضی"
                else:
                    status_str = f"{p_days} روز (نو)"
            except: status_str = f"{package_days} روز"

        lines.append(f"• {escape_markdown(name)} \| 📅 {escape_markdown(status_str)}")

    text = "\n".join(lines)
    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin:p_users:{panel_id}:{page - 1}"))
    if ((page + 1) * PAGE_SIZE) < total_count:
        nav_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin:p_users:{panel_id}:{page + 1}"))
        
    if nav_buttons: kb.add(*nav_buttons)
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data=f"admin:manage_single_panel:{panel_id}:{panel['panel_type']}"))

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_add_user_to_panel_start(call: types.CallbackQuery, params: list):
    """شروع فرآیند افزودن کاربر به یک پنل خاص"""
    panel_id = int(params[0])
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel: return

    # ایمپورت داخلی برای جلوگیری از چرخه
    from bot.admin_handlers.user_management.creation import get_new_user_name

    admin_conversations[uid] = {
        'action': 'add_user',
        'step': 'get_name',
        'data': {'panel_name': panel['name']}, 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': get_new_user_name
    }
    
    back_kb = types.InlineKeyboardMarkup()
    back_kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:manage_single_panel:{panel['id']}:{panel['panel_type']}"))
    
    text = f"👤 سرور انتخاب شد: *{escape_markdown(panel['name'])}*\n\nلطفاً *نام کاربر* جدید را وارد کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=back_kb)

# ==============================================================================
# 3. Node & Access Management
# ==============================================================================

async def get_user_db_object(session, identifier: str):
    """تابع کمکی هوشمند برای پیدا کردن کاربر"""
    if identifier.isdigit():
        return await session.get(User, int(identifier))
    else:
        stmt = select(UserUUID).where(UserUUID.uuid == identifier)
        result = await session.execute(stmt)
        uuid_obj = result.scalar_one_or_none()
        if uuid_obj:
            return await session.get(User, uuid_obj.user_id)
    return None

async def handle_user_access_panel_list(call, params):
    """نمایش لیست پنل‌ها و مدیریت دسترسی (پرچم‌ها)"""
    input_id = int(params[0])
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    async with db.get_session() as session:
        # دریافت کاربر
        stmt_user = (
            select(UserUUID)
            .options(selectinload(UserUUID.allowed_panels))
            .where(UserUUID.user_id == input_id)
            .limit(1)
        )
        result = await session.execute(stmt_user)
        user_uuid = result.scalar_one_or_none()
        
        if not user_uuid:
            user_uuid = await session.get(UserUUID, input_id)
            if user_uuid: await session.refresh(user_uuid, ["allowed_panels"])

        if not user_uuid:
            await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
            return

        real_uuid_id = user_uuid.id
        telegram_id = user_uuid.user_id or 0
        config_name = user_uuid.name or "بی‌نام"
        allowed_panel_ids = {p.id for p in user_uuid.allowed_panels}

        cats = (await session.execute(select(ServerCategory))).scalars().all()
        cat_map = {c.code: c.emoji for c in cats}
        panels = (await session.execute(select(Panel).where(Panel.is_active == True).order_by(Panel.id))).scalars().all()
        all_nodes = (await session.execute(select(PanelNode).where(PanelNode.is_active == True))).scalars().all()

    nodes_by_panel = {}
    for node in all_nodes:
        if node.panel_id not in nodes_by_panel: nodes_by_panel[node.panel_id] = []
        nodes_by_panel[node.panel_id].append(node)

    kb = types.InlineKeyboardMarkup()
    for panel in panels:
        is_active = panel.id in allowed_panel_ids
        status_mark = "✅" if is_active else "❌"
        next_action = "disable" if is_active else "enable"
        panel_flag = cat_map.get(panel.category, "🏳️") if panel.category else "🏳️"
        
        # Header
        kb.add(types.InlineKeyboardButton(f"{panel_flag} {panel.name} ({panel.panel_type})", callback_data="admin:none"))
        
        # Actions
        toggle_callback = f"admin:ptgl:{real_uuid_id}:{panel.id}:{next_action}"
        row_buttons = [types.InlineKeyboardButton(f"{panel_flag} {status_mark}", callback_data=toggle_callback)]
        
        for node in nodes_by_panel.get(panel.id, []):
            node_flag = cat_map.get(node.country_code, "🏳️")
            row_buttons.append(types.InlineKeyboardButton(f"{node_flag} {status_mark}", callback_data=toggle_callback))
        
        kb.row(*row_buttons)

    back_target = telegram_id if telegram_id else "search_menu"
    back_cb = f"admin:us:{back_target}" if str(back_target).isdigit() else "admin:search_menu"
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))
    
    text = (
        f"⚙️ *مدیریت دسترسی سرورها*\n"
        f"👤 کانفیگ: `{escape_markdown(config_name)}`\n"
        f"🆔 شناسه تلگرام: `{escape_markdown(str(telegram_id))}`\n\n"
        f"برای قطع یا وصل دسترسی، روی پرچم‌های زیر هر پنل کلیک کنید\\."
    )
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_user_access_toggle(call, params):
    """تغییر وضعیت دسترسی کاربر به یک پنل خاص"""
    try:
        uuid_id = int(params[0])
        panel_id = int(params[1])
        action = params[2]
        should_enable = (action == "enable")
        
        success = await db.update_user_panel_access_by_id(uuid_id, panel_id, should_enable)
        if success:
            status_text = "فعال" if should_enable else "غیرفعال"
            await bot.answer_callback_query(call.id, f"✅ دسترسی {status_text} شد.")
            await handle_user_access_panel_list(call, [uuid_id])
        else:
            await bot.answer_callback_query(call.id, "❌ خطا در تغییر وضعیت.", show_alert=True)
    except Exception as e:
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی.", show_alert=True)