# bot/admin_handlers/user_management/creation.py

import uuid as uuid_lib
import time
import asyncio
import logging
from telebot import types

# ایمپورت‌های پروژه
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.parsers import validate_uuid
from bot.services.panels import PanelFactory
from bot.bot_instance import bot # ✅ اصلاح شده: ایمپورت مستقیم بات اصلی

# ✅ اصلاح شده: به جای ایمپورت متغیرها، کل ماژول state را ایمپورت کنید
from bot.admin_handlers.user_management import state 
from bot.admin_handlers.user_management.helpers import _delete_user_message, _auto_delete

logger = logging.getLogger(__name__)

# ==============================================================================
# 3. افزودن کاربر جدید (Add User Flow)
# ==============================================================================

async def handle_add_user_select_panel(call: types.CallbackQuery):
    """شروع پروسه: ذخیره پنل و درخواست نام"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    data_parts = call.data.split(':')
    if len(data_parts) < 3: return
    panel_name = data_parts[2]
    
    # ✅ اصلاح شده: دسترسی از طریق ماژول state
    state.admin_conversations[uid] = {
        'action': 'add_user',
        'step': 'get_name',
        'data': {
            'panel_name': panel_name,
            'telegram_id': None,
            'squad_uuid': None
        },
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': get_new_user_name
    }
    
    safe_panel_name = escape_markdown(panel_name)
    text = (
        f"✅ سرور انتخاب شد: *{safe_panel_name}*\n\n"
        f"👤 لطفاً *نام کاربر جدید* را وارد کنید:"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(admin_menu.btn("انصراف", "admin:cancel"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def get_new_user_name(message: types.Message):
    """مرحله ۱: دریافت نام ⬅️ رفتن به UUID"""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    # ✅ اصلاح شده
    if uid not in state.admin_conversations: return
    
    state.admin_conversations[uid]['data']['name'] = name
    
    await _ask_uuid(uid, name)

async def _ask_uuid(uid, name):
    """نمایش درخواست UUID"""
    # ✅ اصلاح شده
    state.admin_conversations[uid]['step'] = 'get_uuid'
    state.admin_conversations[uid]['next_handler'] = get_new_user_uuid
    
    # استفاده از try-except برای جلوگیری از ارسال پیام جدید (طبق خواسته قبلی شما)
    msg_id = state.admin_conversations[uid]['msg_id']
    text = (
        f"👤 نام: `{escape_markdown(name)}`\n\n"
        f"🔑 لطفاً *UUID* دلخواه را ارسال کنید:\n"
        f"\(یا برای ساخت رندوم، فقط کاراکتر `.` را بفرستید\)"
    )
    try:
        await bot.edit_message_text(
            text, 
            uid, 
            msg_id, 
            reply_markup=await admin_menu.cancel_action(),
            parse_mode="MarkdownV2"
        )
    except:
        pass

async def get_new_user_uuid(message: types.Message):
    """مرحله ۲: دریافت UUID و درخواست حجم"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in state.admin_conversations: return # ✅ اصلاح شده
    
    final_uuid = None
    if text == '.' or text.lower() == 'random':
        final_uuid = str(uuid_lib.uuid4())
    elif validate_uuid(text):
        final_uuid = text
    else:
        msg_id = state.admin_conversations[uid]['msg_id'] # ✅ اصلاح شده
        try:
            await bot.edit_message_text(
                r"❌ فرمت UUID نامعتبر است\. مجدد ارسال کنید یا `\.` بزنید:", 
                uid, msg_id, 
                reply_markup=await admin_menu.cancel_action(),
                parse_mode="MarkdownV2"
            )
        except: pass
        return

    state.admin_conversations[uid]['data']['uuid'] = final_uuid # ✅ اصلاح شده
    await _ask_limit(uid)

async def _ask_limit(uid):
    """نمایش درخواست حجم"""
    state.admin_conversations[uid]['step'] = 'get_limit' # ✅ اصلاح شده
    state.admin_conversations[uid]['next_handler'] = get_new_user_limit
    
    msg_id = state.admin_conversations[uid]['msg_id']
    try:
        await bot.edit_message_text(
            "📦 لطفاً *حجم محدودیت \(GB\)* را وارد کنید:\n\(عدد 0 برای نامحدود\)", 
            uid, msg_id,
            reply_markup=await admin_menu.cancel_action(), 
            parse_mode="MarkdownV2"
        )
    except: pass

async def get_new_user_limit(message: types.Message):
    """مرحله ۳: دریافت حجم ⬅️ رفتن به زمان"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in state.admin_conversations: return # ✅ اصلاح شده
    
    msg_id = state.admin_conversations[uid]['msg_id']
    
    try:
        limit = float(text)
        state.admin_conversations[uid]['data']['limit'] = limit # ✅ اصلاح شده
        
        state.admin_conversations[uid]['step'] = 'get_days'
        state.admin_conversations[uid]['next_handler'] = get_new_user_days
        
        try:
            msg_text = "📅 لطفاً *مدت اعتبار* را به روز وارد کنید:"
            await bot.edit_message_text(msg_text, uid, msg_id, reply_markup=await admin_menu.cancel_action())
        except: pass
        
    except ValueError:
        try:
            error_text = "❌ لطفاً *عدد معتبر* وارد کنید\.\n\n📦 لطفاً حجم را به گیگابایت وارد کنید:"
            await bot.edit_message_text(error_text, uid, msg_id, reply_markup=await admin_menu.cancel_action(), parse_mode="MarkdownV2")
        except: pass

async def get_new_user_days(message: types.Message):
    """مرحله ۴: دریافت زمان ⬅️ تصمیم‌گیری"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in state.admin_conversations: return # ✅ اصلاح شده
    
    try:
        days = int(text)
        state.admin_conversations[uid]['data']['days'] = days # ✅ اصلاح شده
        
        panel_name = state.admin_conversations[uid]['data'].get('panel_name')
        is_remnawave = False
        
        if panel_name != 'all':
             p = await db.get_panel_by_name(panel_name)
             if p and p['panel_type'] == 'remnawave':
                 is_remnawave = True
        
        if is_remnawave:
            name = state.admin_conversations[uid]['data']['name']
            await _ask_telegram_id(uid, name)
        else:
            await _finalize_user_creation(uid)

    except ValueError:
        msg_id = state.admin_conversations[uid]['msg_id']
        try:
            error_text = "❌ لطفاً *عدد معتبر* وارد کنید\.\n\n📅 لطفاً *مدت اعتبار* را به روز وارد کنید:"
            await bot.edit_message_text(error_text, uid, msg_id, reply_markup=await admin_menu.cancel_action(), parse_mode="MarkdownV2")
        except: pass

async def _ask_telegram_id(uid, name, prefix_msg=""):
    """نمایش درخواست تلگرام آیدی"""
    state.admin_conversations[uid]['step'] = 'get_telegram_id' # ✅ اصلاح شده
    state.admin_conversations[uid]['next_handler'] = get_new_user_telegram_id
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("رد کردن (خالی)", callback_data="admin:skip_telegram_id"),
        admin_menu.btn("انصراف", "admin:cancel")
    )

    safe_name = escape_markdown(name)
    safe_prefix = escape_markdown(prefix_msg) if prefix_msg else ""
    full_msg = f"{safe_prefix}\n\n" if safe_prefix else ""
    
    full_msg += (
        f"👤 نام: `{safe_name}`\n\n"
        f"🆔 لطفاً *آیدی عددی تلگرام* کاربر را وارد کنید:\n"
        f"\(اختیاری \- جهت اطلاع‌رسانی\)"
    )

    try:
        await bot.edit_message_text(full_msg, uid, state.admin_conversations[uid]['msg_id'], reply_markup=kb, parse_mode="MarkdownV2")
    except: pass

async def get_new_user_telegram_id(message: types.Message):
    """مرحله ۵ (رمناویو): دریافت تلگرام آیدی"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in state.admin_conversations: return # ✅ اصلاح شده
    
    msg_id = state.admin_conversations[uid]['msg_id']

    if not text.isdigit():
        try:
            await bot.edit_message_text(
                "❌ لطفاً فقط عدد وارد کنید (آیدی عددی تلگرام):", 
                uid, msg_id, 
                reply_markup=await admin_menu.cancel_action()
            )
        except: pass
        return

    state.admin_conversations[uid]['data']['telegram_id'] = text # ✅ اصلاح شده
    await _ask_squad_selection(uid)

async def skip_telegram_id(call: types.CallbackQuery, params: list):
    """رد کردن تلگرام آیدی"""
    uid = call.from_user.id
    
    if uid in state.admin_conversations: # ✅ اصلاح شده
        state.admin_conversations[uid]['data']['telegram_id'] = None
        await _ask_squad_selection(uid)

async def _ask_squad_selection(uid):
    """مرحله ۶ (رمناویو): نمایش لیست اسکوادها"""
    msg_id = state.admin_conversations[uid]['msg_id'] # ✅ اصلاح شده
    panel_name = state.admin_conversations[uid]['data'].get('panel_name')
    name = state.admin_conversations[uid]['data']['name']
    
    try:
        try:
            await bot.edit_message_text("⏳ در حال دریافت لیست گروه‌ها \(Squads\)\.\.\.", uid, msg_id, parse_mode="MarkdownV2")
        except: pass
        
        panel_api = await PanelFactory.get_panel(panel_name)
        squads = await panel_api.get_active_squads()

        if squads:
            kb = types.InlineKeyboardMarkup(row_width=2)
            squad_buttons = []
            for s in squads:
                squad_buttons.append(
                    types.InlineKeyboardButton(f"🛡 {s['name']}", callback_data=f"admin:sel_squad:{s['uuid']}")
                )
            kb.add(*squad_buttons)
            kb.add(types.InlineKeyboardButton("رد کردن (پیش‌فرض)", callback_data="admin:skip_squad"))
            kb.add(admin_menu.btn("انصراف", "admin:cancel"))

            state.admin_conversations[uid]['step'] = 'get_squad' # ✅ اصلاح شده
            state.admin_conversations[uid]['next_handler'] = None 
            
            safe_name = escape_markdown(name)
            prompt_text = (
                f"👤 نام: `{safe_name}`\n\n"
                f"🛡 لطفاً یک *گروه \(Squad\)* برای کاربر انتخاب کنید:\n"
                f"\(تنظیمات پروتکل‌ها از این گروه خوانده می‌شود\)"
            )
            try:
                await bot.edit_message_text(prompt_text, uid, msg_id, reply_markup=kb, parse_mode="MarkdownV2")
            except: pass
        else:
            await _finalize_user_creation(uid)
            
    except Exception as e:
        logger.error(f"Error in squad selection: {e}")
        await _finalize_user_creation(uid)

async def handle_squad_callback(call: types.CallbackQuery, params: list):
    """دریافت انتخاب اسکواد داخلی"""
    uid = call.from_user.id
    if uid not in state.admin_conversations: return # ✅ اصلاح شده

    action = call.data.split(':')[1]
    squad_uuid = None

    if action == 'sel_squad' and params:
        squad_uuid = params[0]
        try: await bot.answer_callback_query(call.id, "✅ گروه داخلی انتخاب شد.")
        except: pass
    else:
        try: await bot.answer_callback_query(call.id, "⏭ رد شد.")
        except: pass

    state.admin_conversations[uid]['data']['squad_uuid'] = squad_uuid # ✅ اصلاح شده
    await _ask_external_squad_selection(uid)

async def _ask_external_squad_selection(uid):
    """مرحله ۷ (رمناویو): نمایش لیست External Squads"""
    msg_id = state.admin_conversations[uid]['msg_id'] # ✅ اصلاح شده
    panel_name = state.admin_conversations[uid]['data'].get('panel_name')
    
    try:
        try: await bot.edit_message_text("⏳ دریافت لیست External Squads...", uid, msg_id)
        except: pass
        
        panel_api = await PanelFactory.get_panel(panel_name)
        
        if not hasattr(panel_api, 'get_active_external_squads'):
            await _finalize_user_creation(uid)
            return

        ext_squads = await panel_api.get_active_external_squads()

        if ext_squads:
            kb = types.InlineKeyboardMarkup(row_width=2)
            buttons = []
            for s in ext_squads:
                buttons.append(
                    types.InlineKeyboardButton(f"🌍 {s['name']}", callback_data=f"admin:sel_ext_squad:{s['uuid']}")
                )
            kb.add(*buttons)
            kb.add(admin_menu.btn("انصراف", "admin:cancel"))

            state.admin_conversations[uid]['step'] = 'get_ext_squad' # ✅ اصلاح شده
            
            prompt_text = (
                "🌍 لطفاً یک *External Squad* انتخاب کنید:\n"
                "\(تنظیمات ظاهری و لینک اشتراک از این گروه خوانده می‌شود\)"
            )
            try: await bot.edit_message_text(prompt_text, uid, msg_id, reply_markup=kb, parse_mode="MarkdownV2")
            except: pass
        else:
            await _finalize_user_creation(uid)
            
    except Exception as e:
        logger.error(f"Error in external squad selection: {e}")
        await _finalize_user_creation(uid)

async def handle_external_squad_callback(call: types.CallbackQuery, params: list):
    """دریافت انتخاب اسکواد خارجی"""
    uid = call.from_user.id
    if uid not in state.admin_conversations: return # ✅ اصلاح شده

    ext_uuid = params[0]
    try: await bot.answer_callback_query(call.id, "✅ انتخاب شد.")
    except: pass

    state.admin_conversations[uid]['data']['external_squad_uuid'] = ext_uuid # ✅ اصلاح شده
    await _finalize_user_creation(uid)

async def _finalize_user_creation(uid):
    """مرحله نهایی: ساخت کاربر"""
    if uid not in state.admin_conversations: return # ✅ اصلاح شده
    
    convo_data = state.admin_conversations.pop(uid) # ✅ اصلاح شده
    data = convo_data['data']
    msg_id = convo_data['msg_id']
    
    def safe_code(text):
        return f"`{str(text).replace('`', '')}`"

    try: await bot.edit_message_text("⏳ در حال ساخت کاربر\.\.\.", uid, msg_id, parse_mode="MarkdownV2")
    except: pass

    # استخراج داده‌ها
    panel_name_target = data['panel_name']
    name = data['name']
    limit = data['limit']
    days = data.get('days', 30)
    user_uuid = data.get('uuid')
    telegram_id = data.get('telegram_id')
    squad_uuid = data.get('squad_uuid')
    external_squad_uuid = data.get('external_squad_uuid')

    success_list = []
    fail_list = []
    
    target_panels = []
    if panel_name_target == 'all':
        target_panels = await db.get_active_panels()
    else:
        p = await db.get_panel_by_name(panel_name_target)
        if p: target_panels = [p]

    if not target_panels:
         try: await bot.edit_message_text("❌ پنلی یافت نشد.", uid, msg_id, reply_markup=await admin_menu.main())
         except: pass
         return

    for p in target_panels:
        try:
            panel_api = await PanelFactory.get_panel(p['name'])
            res = await panel_api.add_user(
                name, limit, days, 
                uuid=user_uuid, 
                telegram_id=telegram_id, 
                squad_uuid=squad_uuid,
                external_squad_uuid=external_squad_uuid
            )
            
            if res and res.get('uuid') and not user_uuid:
                user_uuid = res.get('uuid')

            display_str = f"{escape_markdown(p['name'])} \({escape_markdown(p['panel_type'])}\)"
            
            if res: success_list.append(display_str)
            else: fail_list.append(display_str)

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            fail_list.append(escape_markdown(p['name']))

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:management_menu"))

    if success_list:
        success_str = "\n".join([f"🟢 {s}" for s in success_list])
        if not user_uuid: user_uuid = "نامشخص"
        
        limit_val = int(limit) if limit == int(limit) else limit
        limit_display = f"{limit_val}\u00A0GB"
        days_display = f"{days}\u00A0روز"
        
        result_text = (
            f"✅ *{escape_markdown('عملیات پایان یافت')}*\n\n"
            f"👤 {escape_markdown('نام')} : {safe_code(name)}\n"
            f"🔑 {escape_markdown('شناسه یکتا')} : {safe_code(user_uuid)}\n"
            f"📦 {escape_markdown('حجم')} : {safe_code(limit_display)} \| 📅 {escape_markdown('مدت')} : {safe_code(days_display)}\n\n"
            f"👇 {escape_markdown('موفق در')}:\n{success_str}\n"
        )
        
        if fail_list:
            fail_str = "\n".join([f"🔴 {s}" for s in fail_list])
            result_text += f"\n{escape_markdown('ناموفق در')}:\n{fail_str}"
            
        try: await bot.edit_message_text(result_text, uid, msg_id, reply_markup=kb, parse_mode="MarkdownV2")
        except: pass
    else:
        try: await bot.edit_message_text("❌ خطا در ساخت کاربر.", uid, msg_id, reply_markup=kb)
        except: pass

async def handle_cancel_process(call: types.CallbackQuery, params: list):
    """لغو عملیات"""
    uid = call.from_user.id
    if uid in state.admin_conversations: # ✅ اصلاح شده
        del state.admin_conversations[uid]
    
    try: await bot.answer_callback_query(call.id, "❌ عملیات لغو شد.")
    except: pass
    try:
        active_panels = await db.get_active_panels()
        await _safe_edit(uid, call.message.message_id, "منوی مدیریت:", reply_markup=await admin_menu.management_menu(active_panels))
    except: pass

async def handle_start_add_user(call: types.CallbackQuery, params: list):
    await handle_add_user_select_panel(call)