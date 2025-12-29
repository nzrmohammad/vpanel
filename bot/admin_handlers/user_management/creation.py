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

# ایمپورت‌های ماژولار (ساختار جدید)
from bot.admin_handlers.user_management.state import bot, admin_conversations
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
    # فرمت دیتا: admin:add_user:panel_name
    if len(data_parts) < 3: return
    panel_name = data_parts[2]
    
    # شروع استیت
    admin_conversations[uid] = {
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
    
    if uid not in admin_conversations: return
    
    # ذخیره نام
    admin_conversations[uid]['data']['name'] = name
    
    # رفتن به مرحله بعد (UUID) برای همه پنل‌ها
    await _ask_uuid(uid, name)

async def _ask_uuid(uid, name):
    """نمایش درخواست UUID"""
    admin_conversations[uid]['step'] = 'get_uuid'
    admin_conversations[uid]['next_handler'] = get_new_user_uuid
    
    text = (
        f"👤 نام: `{escape_markdown(name)}`\n\n"
        f"🔑 لطفاً *UUID* دلخواه را ارسال کنید:\n"
        f"\(یا برای ساخت رندوم، فقط کاراکتر `.` را بفرستید\)"
    )
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], text, reply_markup=await admin_menu.cancel_action())

async def get_new_user_uuid(message: types.Message):
    """مرحله ۲: دریافت UUID و درخواست حجم"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    # پردازش UUID
    final_uuid = None
    if text == '.' or text.lower() == 'random':
        final_uuid = str(uuid_lib.uuid4())
    elif validate_uuid(text):
        final_uuid = text
    else:
        msg_id = admin_conversations[uid]['msg_id']
        await _safe_edit(uid, msg_id, r"❌ فرمت UUID نامعتبر است\. مجدد ارسال کنید یا `\.` بزنید:", reply_markup=await admin_menu.cancel_action())
        return

    admin_conversations[uid]['data']['uuid'] = final_uuid
    
    # رفتن به درخواست لیمیت
    await _ask_limit(uid)

async def _ask_limit(uid):
    """نمایش درخواست حجم (تابع کمکی)"""
    # در فایل قدیمی این تابع آرگومان name داشت ولی استفاده نمی‌شد، اینجا تمیزتر شد
    admin_conversations[uid]['step'] = 'get_limit'
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    
    msg_id = admin_conversations[uid]['msg_id']
    
    await _safe_edit(uid, msg_id, 
                     "📦 لطفاً *حجم محدودیت \(GB\)* را وارد کنید:\n\(عدد 0 برای نامحدود\)", 
                     reply_markup=await admin_menu.cancel_action(), parse_mode="MarkdownV2")

async def get_new_user_limit(message: types.Message):
    """مرحله ۳: دریافت حجم ⬅️ رفتن به زمان"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    msg_id = admin_conversations[uid]['msg_id']
    
    try:
        limit = float(text)
        admin_conversations[uid]['data']['limit'] = limit
        
        # رفتن به مرحله بعد (زمان)
        admin_conversations[uid]['step'] = 'get_days'
        admin_conversations[uid]['next_handler'] = get_new_user_days
        
        msg_text = "📅 لطفاً *مدت اعتبار* را به روز وارد کنید:"
        await _safe_edit(uid, msg_id, msg_text, reply_markup=await admin_menu.cancel_action())
        
    except ValueError:
        error_text = "❌ لطفاً *عدد معتبر* وارد کنید\.\n\n📦 لطفاً حجم را به گیگابایت وارد کنید:"
        await _safe_edit(uid, msg_id, error_text, reply_markup=await admin_menu.cancel_action())

async def get_new_user_days(message: types.Message):
    """مرحله ۴: دریافت زمان ⬅️ تصمیم‌گیری (تلگرام/پایان)"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    try:
        days = int(text)
        admin_conversations[uid]['data']['days'] = days
        
        # بررسی نوع پنل برای تصمیم‌گیری مسیر بعدی
        panel_name = admin_conversations[uid]['data'].get('panel_name')
        is_remnawave = False
        
        if panel_name != 'all':
             p = await db.get_panel_by_name(panel_name)
             if p and p['panel_type'] == 'remnawave':
                 is_remnawave = True
        
        if is_remnawave:
            # اگر رمناویو است ⬅️ دریافت تلگرام آیدی
            name = admin_conversations[uid]['data']['name']
            await _ask_telegram_id(uid, name)
        else:
            # اگر پنل معمولی است ⬅️ پایان و ساخت کاربر
            await _finalize_user_creation(uid)

    except ValueError:
        msg_id = admin_conversations[uid]['msg_id']
        error_text = "❌ لطفاً *عدد معتبر* وارد کنید\.\n\n📅 لطفاً *مدت اعتبار* را به روز وارد کنید:"
        await _safe_edit(uid, msg_id, error_text, reply_markup=await admin_menu.cancel_action())

async def _ask_telegram_id(uid, name, prefix_msg=""):
    """نمایش درخواست تلگرام آیدی (با منوی دو ستونه)"""
    admin_conversations[uid]['step'] = 'get_telegram_id'
    admin_conversations[uid]['next_handler'] = get_new_user_telegram_id
    
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

    await _safe_edit(uid, admin_conversations[uid]['msg_id'], full_msg, reply_markup=kb)

async def get_new_user_telegram_id(message: types.Message):
    """مرحله ۵ (رمناویو): دریافت تلگرام آیدی ⬅️ انتخاب اسکواد"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    if not text.isdigit():
        msg = await bot.send_message(uid, "❌ لطفاً فقط عدد وارد کنید.")
        await asyncio.create_task(_auto_delete(msg, 3))
        return

    admin_conversations[uid]['data']['telegram_id'] = text
    # رفتن به انتخاب اسکواد
    await _ask_squad_selection(uid)

async def skip_telegram_id(call: types.CallbackQuery, params: list):
    """رد کردن تلگرام آیدی و رفتن به انتخاب اسکواد"""
    uid = call.from_user.id
    
    if uid in admin_conversations:
        admin_conversations[uid]['data']['telegram_id'] = None
        await _ask_squad_selection(uid)

async def _ask_squad_selection(uid):
    """مرحله ۶ (رمناویو): نمایش لیست اسکوادها"""
    msg_id = admin_conversations[uid]['msg_id']
    panel_name = admin_conversations[uid]['data'].get('panel_name')
    name = admin_conversations[uid]['data']['name']
    
    try:
        waiting_text = "⏳ در حال دریافت لیست گروه‌ها \(Squads\)\.\.\."
        await _safe_edit(uid, msg_id, waiting_text, reply_markup=None)
        
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

            # تغییر وضعیت به انتظار برای کالبک
            admin_conversations[uid]['step'] = 'get_squad'
            admin_conversations[uid]['next_handler'] = None 
            
            safe_name = escape_markdown(name)
            prompt_text = (
                f"👤 نام: `{safe_name}`\n\n"
                f"🛡 لطفاً یک *گروه \(Squad\)* برای کاربر انتخاب کنید:\n"
                f"\(تنظیمات پروتکل‌ها از این گروه خوانده می‌شود\)"
            )
            await _safe_edit(uid, msg_id, prompt_text, reply_markup=kb)
        else:
            # اگر اسکوادی نبود، تمام کن
            await _finalize_user_creation(uid)
            
    except Exception as e:
        logger.error(f"Error in squad selection: {e}")
        # در صورت خطا، بدون اسکواد بساز
        await _finalize_user_creation(uid)

async def handle_squad_callback(call: types.CallbackQuery, params: list):
    """دریافت انتخاب اسکواد داخلی ⬅️ انتخاب اسکواد خارجی"""
    uid = call.from_user.id
    if uid not in admin_conversations: return

    action = call.data.split(':')[1]
    squad_uuid = None

    if action == 'sel_squad' and params:
        squad_uuid = params[0]
        await bot.answer_callback_query(call.id, "✅ گروه داخلی انتخاب شد.")
    else:
        await bot.answer_callback_query(call.id, "⏭ رد شد.")

    admin_conversations[uid]['data']['squad_uuid'] = squad_uuid
    
    await _ask_external_squad_selection(uid)

async def _ask_external_squad_selection(uid):
    """مرحله ۷ (رمناویو): نمایش لیست External Squads"""
    msg_id = admin_conversations[uid]['msg_id']
    panel_name = admin_conversations[uid]['data'].get('panel_name')
    
    try:
        await _safe_edit(uid, msg_id, "⏳ دریافت لیست External Squads...", reply_markup=None)
        
        panel_api = await PanelFactory.get_panel(panel_name)
        
        # چک می‌کنیم آیا این پنل اصلا متد اکسترنال دارد یا نه
        if not hasattr(panel_api, 'get_active_external_squads'):
            await _finalize_user_creation(uid)
            return

        ext_squads = await panel_api.get_active_external_squads()

        if ext_squads:
            kb = types.InlineKeyboardMarkup(row_width=2)
            buttons = []
            for s in ext_squads:
                # کال‌بک جدید: admin:sel_ext_squad
                buttons.append(
                    types.InlineKeyboardButton(f"🌍 {s['name']}", callback_data=f"admin:sel_ext_squad:{s['uuid']}")
                )
            kb.add(*buttons)
            kb.add(admin_menu.btn("انصراف", "admin:cancel"))

            admin_conversations[uid]['step'] = 'get_ext_squad'
            
            prompt_text = (
                "🌍 لطفاً یک *External Squad* انتخاب کنید:\n"
                "\(تنظیمات ظاهری و لینک اشتراک از این گروه خوانده می‌شود\)"
            )
            await _safe_edit(uid, msg_id, prompt_text, reply_markup=kb, parse_mode="MarkdownV2")
        else:
            # اگر اکسترنال اسکوادی نبود، تمام کن
            await _finalize_user_creation(uid)
            
    except Exception as e:
        logger.error(f"Error in external squad selection: {e}")
        await _finalize_user_creation(uid)

async def handle_external_squad_callback(call: types.CallbackQuery, params: list):
    """دریافت انتخاب اسکواد خارجی ⬅️ پایان"""
    uid = call.from_user.id
    if uid not in admin_conversations: return

    ext_uuid = params[0]
    await bot.answer_callback_query(call.id, "✅ انتخاب شد.")

    admin_conversations[uid]['data']['external_squad_uuid'] = ext_uuid
    
    await _finalize_user_creation(uid)

async def _finalize_user_creation(uid):
    """مرحله نهایی: ارسال درخواست به پنل و نمایش نتیجه"""
    if uid not in admin_conversations: return
    
    convo_data = admin_conversations.pop(uid)
    data = convo_data['data']
    msg_id = convo_data['msg_id']
    
    # تابع کمکی برای نمایش کد (بک‌تیک)
    def safe_code(text):
        return f"`{str(text).replace('`', '')}`"

    await _safe_edit(uid, msg_id, "⏳ در حال ساخت کاربر\.\.\.", reply_markup=None)

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
         # اینجا برای جلوگیری از ایمپورت چرخشی، import داخلی استفاده می‌کنیم
         from bot.admin_handlers.user_management.search import handle_management_menu
         await _safe_edit(uid, msg_id, "❌ پنلی یافت نشد.", reply_markup=await admin_menu.main())
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

            # --- بخش تغییر یافته: حذف وابستگی به CATEGORY_META ---
            display_str = f"{escape_markdown(p['name'])} \({escape_markdown(p['panel_type'])}\)"
            
            if res: success_list.append(display_str)
            else: fail_list.append(display_str)

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            fail_list.append(escape_markdown(p['name']))

    # نمایش نتیجه نهایی
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:management_menu"))

    if success_list:
        success_str = "\n".join([f"🟢 {s}" for s in success_list])
        if not user_uuid: user_uuid = "نامشخص"
        
        # حذف اعشار صفر (3.0 -> 3)
        limit_val = int(limit) if limit == int(limit) else limit
        
        # استفاده از \u00A0 (فاصله نشکن)
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
            
        await _safe_edit(uid, msg_id, result_text, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در ساخت کاربر.", reply_markup=kb)

async def handle_cancel_process(call: types.CallbackQuery, params: list):
    """لغو عملیات"""
    uid = call.from_user.id
    if uid in admin_conversations:
        del admin_conversations[uid]
    
    await bot.answer_callback_query(call.id, "❌ عملیات لغو شد.")
    try:
        active_panels = await db.get_active_panels()
        await _safe_edit(uid, call.message.message_id, "منوی مدیریت:", reply_markup=await admin_menu.management_menu(active_panels))
    except: pass

# --- این تابع را به فایل creation.py اضافه کنید ---

async def handle_start_add_user(call: types.CallbackQuery, params: list):
    """
    نقطه شروع فرآیند ساخت کاربر (جهت سازگاری با دکمه‌های قدیمی یا دستورات روتر).
    کار را به تابع انتخاب پنل می‌سپارد.
    """
    await handle_add_user_select_panel(call)