# bot/admin_handlers/user_management.py

import uuid as uuid_lib
import logging
import asyncio
import time
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, or_, and_, update
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.keyboards.base import CATEGORY_META
from bot.database import db
from bot.db.base import User, UserUUID, Panel, UserUUID, ServerCategory
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.date_helpers import to_shamsi
from bot.utils.parsers import validate_uuid
from bot import combined_handler
from bot.services.panels import PanelFactory
from bot.formatters import user_formatter

logger = logging.getLogger(__name__)

# استیت برای مکالمات ادمین (جستجو، ادیت مقدار، یادداشت و ...)
admin_conversations = {}

def initialize_user_management_handlers(b, conv_dict):
    """دریافت مقادیر سراسری از فایل اصلی"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    """حذف پیام کاربر جهت تمیز نگه داشتن چت"""
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

# ==============================================================================
# 1. جستجو و یافتن کاربر (Search & Find)
# ==============================================================================

async def handle_global_search_convo(call, params):
    """شروع جستجوی کاربر با نام، یوزرنیم یا UUID"""
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {
        'step': 'global_search', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_search_input
    }
    
    text = r"🔎 لطفاً *نام*، *نام کاربری* یا بخشی از *UUID* کاربر را ارسال کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def handle_search_by_telegram_id_convo(call, params):
    """شروع جستجو با آیدی عددی تلگرام"""
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {
        'step': 'tid_search', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_search_input
    }
    
    text = "🆔 لطفاً *آیدی عددی تلگرام* کاربر را ارسال کنید:"
    
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def process_search_input(message: types.Message):
    """پردازش ورودی جستجو"""
    uid, query = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    msg_id = data['msg_id']
    step = data['step']
    
    async with db.get_session() as session:
        stmt = select(User).distinct().options(selectinload(User.uuids))
        
        if step == 'tid_search':
            if not query.isdigit():
                await _safe_edit(uid, msg_id, "❌ آیدی باید عدد باشد.", reply_markup=await admin_menu.search_menu())
                return
            stmt = stmt.where(User.user_id == int(query))
        else:
            stmt = stmt.outerjoin(UserUUID).where(
                or_(
                    User.username.ilike(f"%{query}%"),
                    User.first_name.ilike(f"%{query}%"),
                    User.last_name.ilike(f"%{query}%"),
                    UserUUID.uuid.ilike(f"%{query}%"),
                    UserUUID.name.ilike(f"%{query}%")
                )
            )
        
        result = await session.execute(stmt)
        users = result.scalars().all()

    if not users:
        safe_query = escape_markdown(query)
        await _safe_edit(uid, msg_id, rf"❌ کاربری با مشخصات «{safe_query}» یافت نشد\.", reply_markup=await admin_menu.search_menu())
        return
    
    if len(users) == 1:
        await show_user_summary(uid, msg_id, users[0].user_id)
    else:
        safe_query = escape_markdown(query)
        text = rf"🔍 نتایج جستجو برای `{safe_query}` \({len(users)} مورد\):"
        kb = types.InlineKeyboardMarkup(row_width=1)
        for u in users[:10]:
            display = f"{u.first_name or 'NoName'} (@{u.username or 'NoUser'})"
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:us:{u.user_id}:s"))
        
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:search_menu"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_purge_user_convo(call, params):
    """شروع پروسه حذف کامل (Purge) با آیدی"""
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {
        'step': 'purge_user', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_purge_user
    }
    text = r"🔥 برای *پاکسازی کامل* \(حذف از دیتابیس\)، آیدی عددی کاربر را بفرستید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def process_purge_user(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    msg_id = admin_conversations.pop(uid)['msg_id']
    
    if not text.isdigit():
        await _safe_edit(uid, msg_id, "❌ آیدی نامعتبر.", reply_markup=await admin_menu.search_menu())
        return
        
    target_id = int(text)
    success = await db.purge_user_by_telegram_id(target_id)
    if success:
        await _safe_edit(uid, msg_id, f"✅ کاربر {target_id} با موفقیت کامل پاکسازی شد.", reply_markup=await admin_menu.search_menu())
    else:
        await _safe_edit(uid, msg_id, "❌ کاربر یافت نشد یا خطا در حذف.", reply_markup=await admin_menu.search_menu())

# ==============================================================================
# 2. مدیریت و نمایش کاربر (User Profile)
# ==============================================================================

async def handle_show_user_summary(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    real_user_id = None
    if str(target_id).isdigit():
        real_user_id = int(target_id)
    else:
        real_user_id = await db.get_user_id_by_uuid(target_id)
    
    if not real_user_id:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
        return

    context = params[1] if len(params) > 1 else None
    await show_user_summary(uid, msg_id, real_user_id, context)


async def show_user_summary(admin_id, msg_id, target_user_id, context=None, extra_message=None):
    async with db.get_session() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await _safe_edit(admin_id, msg_id, escape_markdown("❌ کاربر در دیتابیس یافت نشد."), reply_markup=await admin_menu.main(), parse_mode="MarkdownV2")
            return
            
        uuids = await db.uuids(target_user_id)
        active_uuids = [u for u in uuids if u['is_active']]
        
        safe_name = escape_markdown(user.first_name or 'Unknown')
        
        if active_uuids:
            main_uuid = active_uuids[0]['uuid']
            info = await combined_handler.get_combined_user_info(str(main_uuid))
            
            if info:
                info['db_id'] = active_uuids[0]['id']
                history = await db.get_user_payment_history(active_uuids[0]['id'])
                payment_count = len(history)
                
                formatted_body = await user_formatter.profile_info(info, 'fa')
                lines = formatted_body.split('\n')
                
                is_active = info.get('is_active')
                status_emoji = "✅" if is_active else "❌"
                status_text = "فعال" if is_active else "غیرفعال"
                
                new_header = f"👤 نام : {safe_name} \({status_emoji} {status_text} \| {payment_count} پرداخت\)"
                lines[0] = f"*{new_header}*"
                
                admin_lines = ["──────────────────"]
                
                if user.admin_note:
                    safe_note = escape_markdown(user.admin_note)
                    admin_lines.append(f"📝 یادداشت: {safe_note}")
                
                admin_lines.append(f"🆔 آیدی عددی: `{target_user_id}`")
                wallet_balance = int(user.wallet_balance or 0)
                admin_lines.append(f"💰 کیف پول: `{wallet_balance:,}` تومان")
                
                text = "\n".join(lines) + "\n" + "\n".join(admin_lines)
            else:
                text = escape_markdown("❌ خطا در دریافت اطلاعات از سرور.")
        else:
            text = f"👤 کاربر: {safe_name}\n🔴 وضعیت: غیرفعال \(بدون سرویس فعال\)\n🆔 `{target_user_id}`"

    if extra_message:
        text += f"\n\n{extra_message}"

    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    panel_type = 'hiddify'
    
    markup = await admin_menu.user_interactive_menu(str(user.user_id), bool(active_uuids), panel_type, back_callback=back_cb)
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

# 3. افزودن کاربر جدید (Add User Flow)
# ==============================================================================

# ==================================================================
#  User Creation Flow: Name -> UUID -> Limit -> Days -> [Tel -> Squad] -> Final
# ==================================================================

async def handle_add_user_select_panel(call: types.CallbackQuery):
    """شروع پروسه: ذخیره پنل و درخواست نام"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    data_parts = call.data.split(':')
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
    """مرحله ۴: دریافت UUID و درخواست حجم"""
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
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    msg_id = admin_conversations[uid]['msg_id']
    
    await _safe_edit(uid, msg_id, 
                     "📦 لطفاً *حجم محدودیت \(GB\)* را وارد کنید:\n\(عدد 0 برای نامحدود\)", 
                     reply_markup=await admin_menu.cancel_action(), parse_mode="MarkdownV2")

async def _ask_limit(uid, name):
    """نمایش درخواست حجم (اصلاح شده)"""
    admin_conversations[uid]['step'] = 'get_limit'
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    
    text = "📦 لطفاً *حجم محدودیت \(GB\)* را وارد کنید:\n\(عدد 0 برای نامحدود\)"
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], text, reply_markup=await admin_menu.cancel_action())

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
        asyncio.create_task(_auto_delete(msg, 3))
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
    """مرحله نهایی: ارسال درخواست به پنل و نمایش نتیجه (با اصلاح فاصله نشکن)"""
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

            cat_code = p.get('category')
            meta = CATEGORY_META.get(cat_code, {})
            flag = meta.get('emoji', '')
            raw_cat_name = meta.get('name') if meta.get('name') else p['name']
            
            display_str = f"{flag} {escape_markdown(raw_cat_name)} \({escape_markdown(p['panel_type'])}\)"
            
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
        
        # ✅ اصلاح مهم: استفاده از \u00A0 (فاصله نشکن) به جای فاصله معمولی
        # این کار باعث می‌شود 3 و GB به هم بچسبند و برعکس نشوند، اما فاصله بصری داشته باشند.
        limit_display = f"{limit_val}\u00A0GB"
        
        # برای روز هم همین کار را می‌کنیم
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

async def _auto_delete(msg, seconds):
    """پیام را بعد از چند ثانیه حذف می‌کند"""
    await asyncio.sleep(seconds)
    try:
        await msg.delete()
    except:
        pass

# ==============================================================================
# 4. ویرایش سرویس (Edit User - Volume/Days)
# ==============================================================================

async def handle_edit_user_menu(call, params):
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
    panel_target, identifier = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    markup = await admin_menu.edit_user_action_menu(identifier, panel_target)
    panel_display = "همه پنل‌ها" if panel_target == 'all' else panel_target
    await _safe_edit(uid, msg_id, f"🔧 ویرایش روی: **{escape_markdown(panel_display)}**\nچه تغییری اعمال شود؟", reply_markup=markup, parse_mode="Markdown")

async def handle_ask_edit_value(call, params):
    action, panel_target, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    
    admin_conversations[uid] = {
        'step': 'edit_value', 'msg_id': msg_id, 'action': action, 'scope': panel_target,
        'target_id': target_id, 'timestamp': time.time(), 'next_handler': process_edit_value
    }
    await _safe_edit(uid, msg_id, f"🔢 مقدار *{action_name}* را وارد کنید (مثبت برای افزودن، منفی برای کسر):", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"), parse_mode="Markdown")

async def process_edit_value(message: types.Message):
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
        await _safe_edit(uid, msg_id, "❌ مقدار نامعتبر.", reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))
        return

    await _safe_edit(uid, msg_id, "⏳ اعمال تغییرات...", reply_markup=None)
    uuids = await db.uuids(int(target_id))
    if not uuids: return
    
    main_uuid_str = str(uuids[0]['uuid'])
    add_gb = value if 'gb' in action else 0
    add_days = int(value) if 'days' in action else 0
    target_name = panel_target if panel_target != 'all' else None
    
    success = await combined_handler.modify_user_on_all_panels(main_uuid_str, add_gb=add_gb, add_days=add_days, target_panel_name=target_name)
    
    res_text = f"✅ انجام شد: {value}" if success else "❌ خطا در انجام عملیات."
    markup = await admin_menu.edit_user_action_menu(target_id, panel_target)    
    await _safe_edit(uid, msg_id, res_text, reply_markup=markup)

# ==============================================================================
# 5. تغییر وضعیت (Toggle Status) - اصلاح شده: هوشمند و داینامیک
# ==============================================================================

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
    
    # 2. نمایش وضعیت "در حال بارگذاری" (بدون مارک‌داون برای جلوگیری از ارور احتمالی در پیام موقت)
    await _safe_edit(uid, msg_id, "⏳ در حال استعلام وضعیت از سرورها...", reply_markup=None, parse_mode=None)
    
    # 3. دریافت اطلاعات ترکیبی (لایو) از سرورها
    combined_info = await combined_handler.get_combined_user_info(uuid_str)
    
    # 4. تعیین وضعیت کلی در دیتابیس ربات
    global_is_active = uuids[0]['is_active']
    status_icon = "🟢" if global_is_active else "🔴"
    status_text = 'فعال' if global_is_active else 'غیرفعال'
    
    # 5. آماده‌سازی متن با رعایت MarkdownV2
    # نکته: تمام متون فارسی و متغیرها باید اسکیپ شوند
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
    # پارامتر 'all' نشان‌دهنده تغییر روی تمام پنل‌هاست
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
            # بررسی وضعیت در پنل (ممکن است کلیدهای مختلفی داشته باشد)
            p_is_active = (p_data.get('status') == 'active') or (p_data.get('enable') == True) or (p_data.get('is_active') == True)
            
            if p_is_active:
                btn_text = f"🔴 {panel_name}" # دکمه برای غیرفعال کردن
                btn_action = "disable"
            else:
                btn_text = f"🟢 {panel_name}" # دکمه برای فعال کردن
                btn_action = "enable"
            
            # ارسال ID پنل خاص برای تغییر وضعیت فقط در همان پنل
            panel_buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:tglA:{btn_action}:{target_id}:{panel_db['id']}"))

    # چینش دکمه‌های پنل (دوتا دوتا)
    if panel_buttons:
        kb.add(*panel_buttons)

    # دکمه بازگشت
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    # 7. ارسال پیام نهایی (از تابع safe_edit پروژه استفاده می‌شود که پیش‌فرض V2 دارد)
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_toggle_status_action(call, params):
    """
    اجرای عملیات تغییر وضعیت (سراسری یا تکی).
    """
    # params: [action, target_id, scope_id]
    action = params[0]
    target_id = params[1]
    # اگر پارامتر سوم وجود نداشت، پیش‌فرض 'all' در نظر گرفته می‌شود (سازگاری با کدهای قبلی)
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

    # سناریو ۱: تغییر سراسری (Global)
    if scope == 'all':
        # آپدیت وضعیت در دیتابیس ربات فقط وقتی سراسری است
        async with db.get_session() as session:
            stmt = update(UserUUID).where(UserUUID.id == uuid_id).values(is_active=new_status_bool)
            await session.execute(stmt)
            await session.commit()
        
        # همه پنل‌های فعال هدف هستند
        target_panels = await db.get_active_panels()

    # سناریو ۲: تغییر تکی (Specific Panel)
    else:
        # پیدا کردن پنل خاص
        try:
            panel_id = int(scope)
            panel = await db.get_panel_by_id(panel_id)
            if panel:
                target_panels = [panel]
        except ValueError:
            pass

    # اعمال تغییرات روی API پنل‌های هدف
    for p in target_panels:
        try:
            handler = await PanelFactory.get_panel(p['name'])
            
            # تعیین شناسه کاربر برای پنل
            identifier = uuid_str
            if p['panel_type'] == 'marzban':
                mapping = await db.get_marzban_username_by_uuid(uuid_str)
                identifier = mapping if mapping else uuid_str

            # فراخوانی متد تغییر وضعیت
            if await _toggle_panel_user_status(handler, p['panel_type'], identifier, action):
                success_count += 1
                
        except Exception as e:
            logger.error(f"Error toggling status on {p['name']}: {e}")

    # نمایش نتیجه
    action_fa = "فعال" if new_status_bool else "غیرفعال"
    
    if scope == 'all':
        msg = f"✅ وضعیت کاربر به *{action_fa}* تغییر کرد (سراسری).\n📊 اعمال شده روی {success_count} سرور."
    else:
        # اگر تکی بود، اسم پنل را هم نشان دهیم بهتر است
        p_name = target_panels[0]['name'] if target_panels else "پنل انتخاب شده"
        msg = f"✅ کاربر در سرور *{escape_markdown(p_name)}* {action_fa} شد."

    # بازگشت به منوی تغییر وضعیت (برای دیدن تغییرات جدید)
    # برای این کار دوباره تابع handle_toggle_status را صدا می‌زنیم تا لیست رفرش شود
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت وضعیت", callback_data=f"admin:us_tgl:{target_id}"))
    kb.add(types.InlineKeyboardButton("👤 پروفایل کاربر", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, msg, reply_markup=kb, parse_mode="Markdown")


async def _toggle_panel_user_status(handler, panel_type, identifier, action):
    """
    تابع کمکی برای ارسال درخواست فعال/غیرفعال سازی به API پنل‌ها
    """
    try:
        if panel_type == 'marzban':
            status_val = "active" if action == 'enable' else "disabled"
            payload = {"status": status_val}
            return await handler._request("PUT", f"user/{identifier}", json=payload) is not None

        elif panel_type == 'hiddify':
            is_enable = (action == 'enable')
            payload = {
                "enable": is_enable, 
                "is_active": is_enable,
                "mode": "no_reset"
            }
            return await handler._request("PATCH", f"user/{identifier}", json=payload) is not None

        elif panel_type == 'remnawave':
            status_val = "ACTIVE" if action == 'enable' else "DISABLED"
            payload = {"status": status_val}
            
            return await handler._request("PATCH", f"api/users/{identifier}", json=payload) is not None

    except Exception as e:
        logger.error(f"Failed to toggle status API: {e}")
        return False
# ==============================================================================
# 6. تاریخچه پرداخت و ثبت دستی
# ==============================================================================

async def handle_payment_history(call, params):
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    user_info = await db.user(target_id)
    user_name = user_info.get('first_name', str(target_id)) if user_info else str(target_id)
    safe_name = escape_markdown(user_name)
    
    history = await db.get_wallet_history(target_id, limit=20)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    if not history:
        # نمایش پیام مخصوص زمانی که سابقه‌ای وجود ندارد
        text = f"سابقه پرداخت‌های کاربر: {safe_name}\n\nهیچ پرداخت ثبت‌شده‌ای برای این کاربر یافت نشد\\."
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")
        return
    
    # نمایش لیست تراکنش‌ها در صورت وجود
    lines = [f"📜 *تاریخچه تراکنش‌های {safe_name}*", "──────────────────"]
    
    for t in history:
        amount = t.get('amount', 0)
        desc = t.get('description') or t.get('type', '')
        dt_str = to_shamsi(t.get('transaction_date'), include_time=True)
        
        icon = "🟢" if amount > 0 else "🔴"
        amt_str = f"{int(abs(amount)):,} تومان"
        
        block = (
            f"{icon} *{escape_markdown(amt_str)}*\n"
            f"📅 {escape_markdown(dt_str)}\n"
            f"📝 {escape_markdown(desc)}\n"
            "──────────────────"
        )
        lines.append(block)
        
    final_text = "\n".join(lines)
    
    await _safe_edit(uid, msg_id, final_text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_log_payment(call, params):
    """ثبت دستی پرداخت"""
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    
    if uuids:
        await db.add_payment_record(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ پرداخت ثبت شد.")
        
        try:
            await bot.send_message(target_id, "✅ اشتراک شما توسط مدیریت تمدید شد.\nبا تشکر از پرداخت شما.")
        except Exception as e:
            logger.warning(f"Could not send msg to {target_id}: {e}")

        await show_user_summary(call.from_user.id, call.message.message_id, target_id)
    else:
        await bot.answer_callback_query(call.id, "سرویسی وجود ندارد.", show_alert=True)

async def handle_reset_payment_history_confirm(call, params):
    uuid_id, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    text = "⚠️ آیا مطمئن هستید که می‌خواهید تاریخچه پرداخت‌ها را پاک کنید؟"
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("بله، پاک کن", callback_data=f"admin:do_reset_phist:{uuid_id}:{target_id}"),
        types.InlineKeyboardButton("خیر", callback_data=f"admin:us_phist:{target_id}:0")
    )
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_reset_payment_history_action(call, params):
    uuid_id, target_id = int(params[0]), params[1]
    await db.delete_user_payment_history(uuid_id)
    await bot.answer_callback_query(call.id, "🗑 تاریخچه پاک شد.")
    await handle_show_user_summary(call, [target_id])

# ==============================================================================
# 7. سایر (ریست، هشدار، یادداشت، حذف، تمدید، بج)
# ==============================================================================

async def handle_user_reset_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("🎂 حذف تاریخ تولد", callback_data=f"admin:us_rb:{target_id}"),
        types.InlineKeyboardButton("⏳ ریست محدودیت انتقال", callback_data=f"admin:us_rtr:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, "♻️ انتخاب کنید:", reply_markup=kb)

async def handle_reset_usage_menu(call, params):
    target_id = params[0]
    markup = await admin_menu.reset_usage_selection_menu(target_id, "rsa") 
    await _safe_edit(call.from_user.id, call.message.message_id, "انتخاب پنل برای ریست حجم:", reply_markup=markup)

async def handle_reset_usage_action(call, params):
    scope, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids: return
    uuid_str = str(uuids[0]['uuid'])
    
    await _safe_edit(uid, msg_id, "⏳ در حال ریست حجم...", reply_markup=None)
    
    panels = await db.get_active_panels()
    success_count = 0
    
    for p in panels:
        if scope != 'both' and p['panel_type'] != scope: continue 
        
        handler = await PanelFactory.get_panel(p['name'])
        try:
            identifier = uuid_str
            if p['panel_type'] == 'marzban':
                identifier = await db.get_marzban_username_by_uuid(uuid_str) or f"marzban_{uuid_str}" 
                
            if await handler.reset_user_usage(identifier):
                success_count += 1
        except Exception as e:
            logger.error(f"Reset usage failed for {p['name']}: {e}")

    msg = "✅ حجم ریست شد." if success_count > 0 else "❌ خطا در ریست."
    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))

async def handle_reset_birthday(call, params):
    target_id = int(params[0])
    await db.reset_user_birthday(target_id)
    await bot.answer_callback_query(call.id, "✅ تاریخ تولد حذف شد.")
    await handle_user_reset_menu(call, params)

async def handle_reset_transfer_cooldown(call, params):
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_transfer_history(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ محدودیت انتقال ریست شد.")
    else:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
    await handle_user_reset_menu(call, params)

async def handle_user_warning_menu(call, params):
    """منوی ارسال هشدار"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔔 یادآوری پرداخت", callback_data=f"admin:us_spn:{target_id}"),
        types.InlineKeyboardButton("🚨 هشدار قطع سرویس", callback_data=f"admin:us_sdw:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, "⚠️ ارسال هشدار:", reply_markup=kb)

async def handle_send_payment_reminder(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    msg = get_string('payment_reminder_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا (شاید بلاک).", show_alert=True)

async def handle_send_disconnection_warning(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    msg = get_string('disconnection_warning_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا.", show_alert=True)

async def handle_ask_for_note(call, params):
    target_id = params[0]
    context_code = params[1] if len(params) > 1 else None
    
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'save_note', 
        'msg_id': msg_id, 
        'target_id': int(target_id),
        'context': context_code,
        'timestamp': time.time(),
        'next_handler': process_save_note
    }
    
    prompt = r"📝 یادداشت خود را بنویسید \(برای حذف، *پاک* بفرستید\):"
    
    await _safe_edit(uid, msg_id, prompt,
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}:{context_code}"),
                     parse_mode="MarkdownV2")


async def process_save_note(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    target_id = data['target_id']
    msg_id = data['msg_id']
    context_code = data.get('context')
    
    note_val = None if text == 'پاک' else text
    await db.update_user_note(target_id, note_val)
    
    status_msg = r"🗑 *یادداشت حذف شد\.*" if text == 'پاک' else r"✅ *یادداشت ذخیره شد\.*"
    
    await show_user_summary(uid, msg_id, target_id, context=context_code, extra_message=status_msg)

async def handle_delete_user_confirm(call, params):
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
    await _safe_edit(call.from_user.id, call.message.message_id, 
                     f"⚠️ *هشدار:* حذف کاربر `{target_id}` باعث حذف تمام سوابق و قطع دسترسی او می‌شود\\.\nآیا مطمئن هستید؟",
                     reply_markup=markup, parse_mode="MarkdownV2")

async def handle_delete_user_action(call, params):
    decision, target_id = params[0], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    if decision == 'cancel':
        await show_user_summary(uid, msg_id, int(target_id))
        return
        
    uuids = await db.uuids(int(target_id))
    if uuids:
        await combined_handler.delete_user_from_all_panels(str(uuids[0]['uuid']))
    await db.purge_user_by_telegram_id(int(target_id))
    
    panels = await db.get_active_panels()
    await _safe_edit(uid, msg_id, "✅ کاربر حذف شد.", reply_markup=await admin_menu.management_menu(panels))

async def handle_delete_devices_confirm(call, params):
    target_id = params[0]
    uuids = await db.uuids(int(target_id))
    count = await db.count_user_agents(uuids[0]['id']) if uuids else 0
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("بله، پاک کن", callback_data=f"admin:del_devs_exec:{target_id}"),
        types.InlineKeyboardButton("خیر", callback_data=f"admin:us:{target_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, f"📱 حذف {count} دستگاه؟", reply_markup=kb)

async def handle_delete_devices_action(call, params):
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_user_agents_by_uuid_id(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ دستگاه‌ها پاک شدند.")
    await show_user_summary(call.from_user.id, call.message.message_id, target_id)

async def handle_renew_subscription_menu(call, params):
    target_id = params[0]
    plans = await db.get_all_plans()
    if not plans:
        await bot.answer_callback_query(call.id, "هیچ پلنی تعریف نشده است.", show_alert=True)
        return
    markup = await admin_menu.select_plan_for_renew_menu(target_id, "", plans)
    await _safe_edit(call.from_user.id, call.message.message_id, "🔄 پلن جدید را انتخاب کنید:", reply_markup=markup)

async def handle_renew_select_plan_menu(call, params):
    await handle_renew_subscription_menu(call, params)

async def handle_renew_apply_plan(call, params):
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    uuids = await db.uuids(target_id)
    if not uuids: return
    
    await _safe_edit(uid, msg_id, "⏳ در حال تمدید...", reply_markup=None)
    success = await combined_handler.modify_user_on_all_panels(
        identifier=str(uuids[0]['uuid']),
        add_gb=plan['volume_gb'],
        add_days=plan['days']
    )
    
    if success:
        await db.add_payment_record(uuids[0]['id'])
        await _safe_edit(uid, msg_id, f"✅ تمدید شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در تمدید.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

async def handle_award_badge_menu(call, params):
    target_id = params[0]
    markup = await admin_menu.award_badge_menu(target_id, "")
    await _safe_edit(call.from_user.id, call.message.message_id, "🏅 انتخاب نشان:", reply_markup=markup)

async def handle_award_badge(call, params):
    badge_code, target_id = params[0], int(params[1])
    if await db.add_achievement(target_id, badge_code):
        await bot.answer_callback_query(call.id, "✅ اهدا شد.")
    else:
        await bot.answer_callback_query(call.id, "قبلاً داشته است.")
    await handle_award_badge_menu(call, [str(target_id)])

async def handle_achievement_request_callback(call, params):
    action = call.data.split(':')[1]
    req_id = int(params[0])
    status = 'approved' if 'approve' in action else 'rejected'
    await db.update_achievement_request_status(req_id, status, call.from_user.id)
    req = await db.get_achievement_request(req_id)
    if req and status == 'approved':
        await db.add_achievement(req['user_id'], req['badge_code'])
        await db.add_achievement_points(req['user_id'], 50)
        try: await bot.send_message(req['user_id'], "✅ درخواست نشان تایید شد!")
        except: pass
    await bot.edit_message_caption(f"{call.message.caption}\n\nوضعیت: {status}", call.from_user.id, call.message.message_id)

# ==============================================================================
# 8. سیستم تولز و ریست کلی
# ==============================================================================

async def handle_system_tools_menu(call, params):
    pass 

async def handle_reset_all_daily_usage_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ بله", callback_data="admin:reset_all_daily_usage_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ ریست مصرف امروز همه؟", reply_markup=kb)

async def handle_reset_all_daily_usage_action(call, params):
    count = await db.delete_all_daily_snapshots()
    await bot.answer_callback_query(call.id, f"✅ {count} رکورد پاک شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_force_snapshot(call, params):
    await bot.answer_callback_query(call.id, "دستور اجرا شد.")

async def handle_reset_all_points_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید", callback_data="admin:reset_all_points_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ صفر کردن امتیازات همه؟", reply_markup=kb)

async def handle_reset_all_points_execute(call, params):
    count = await db.reset_all_achievement_points()
    await bot.answer_callback_query(call.id, f"✅ امتیاز {count} کاربر صفر شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_delete_all_devices_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید", callback_data="admin:delete_all_devices_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ حذف تمام دستگاه‌ها؟", reply_markup=kb)

async def handle_delete_all_devices_execute(call, params):
    count = await db.delete_all_user_agents()
    await bot.answer_callback_query(call.id, f"✅ {count} دستگاه حذف شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_reset_all_balances_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید", callback_data="admin:reset_all_balances_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ صفر کردن موجودی کیف پول همه؟", reply_markup=kb)

async def handle_reset_all_balances_execute(call, params):
    count = await db.reset_all_wallet_balances()
    await bot.answer_callback_query(call.id, "✅ انجام شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, f"✅ موجودی {count} کاربر صفر شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_churn_contact_user(call, params):
    """تماس با کاربر (ارسال پیام دستی)"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'send_msg_to_user',
        'target_id': int(target_id),
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_send_msg_to_user
    }
    
    await _safe_edit(uid, msg_id, "📝 لطفاً پیام خود را برای ارسال به کاربر بنویسید:", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

async def process_send_msg_to_user(message: types.Message):
    """پردازش و ارسال پیام وارد شده توسط ادمین"""
    uid, text = message.from_user.id, message.text
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    target_id = data['target_id']
    msg_id = data['msg_id']
    
    try:
        await bot.send_message(target_id, f"📩 پیام از پشتیبانی:\n\n{text}")
        await _safe_edit(uid, msg_id, "✅ پیام شما با موفقیت برای کاربر ارسال شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'hiddify')) # پنل پیش‌فرض
    except Exception as e:
        logger.error(f"Error sending msg to user {target_id}: {e}")
        await _safe_edit(uid, msg_id, "❌ ارسال ناموفق (ممکن است ربات بلاک شده باشد).", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'hiddify'))

async def handle_churn_send_offer(call, params):
    """ارسال پیشنهاد ویژه (همان Winback)"""
    await manual_winback_handler(call, params)

async def manual_winback_handler(call, params):
    """ارسال پیام دلتنگی آماده"""
    target_id = int(params[0])
    msg = "👋 سلام! دلمون برات تنگ شده. 🌹\nخیلی وقته سری به ما نزدی. یه کد تخفیف ویژه برات داریم:\n🎁 Code: `WELCOME_BACK`"
    
    try:
        await bot.send_message(target_id, msg, parse_mode="Markdown")
        await bot.answer_callback_query(call.id, "✅ پیام ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ ارسال ناموفق.", show_alert=True)

async def handle_mapping_menu(call: types.CallbackQuery, params: list):
    """منوی اصلی مدیریت اتصال (دارای دو دکمه)"""
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
    
    if total_count == 0:
        total_pages = 1
    else:
        total_pages = ((total_count - 1) // PAGE_SIZE) + 1
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_mappings = all_mappings[start_idx:end_idx]
    
    markup = await admin_menu.mapping_list_menu(current_mappings, page, total_count, PAGE_SIZE)
    
    text = f"📋 *{escape_markdown('لیست اتصال‌های موجود')}*\n\n"
    
    if not current_mappings:
        text += escape_markdown("⚠️ هیچ اتصالی یافت نشد.")
    
    if total_pages > 1:
        text += f"\n📄 *{escape_markdown(f'صفحه {page + 1} از {total_pages}')}*"
        
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
    await _delete_user_message(message) # حذف پیام کاربر
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['timestamp'] = time.time()
    
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
    username = text
    msg_id = data['msg_id']
    
    success = await db.add_marzban_mapping(uuid_str, username)
    
    if success:
        success_msg = f"✅ {escape_markdown('اتصال با موفقیت ایجاد شد.')}\n\nUUID: `{escape_markdown(uuid_str)}`\nMarzban: `{escape_markdown(username)}`"
        
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
# 1. نمایش منوی مدیریت کاربران برای یک پنل خاص
# Callback: admin:manage_single_panel:<panel_id>:<panel_type>
# ==============================================================================

async def handle_manage_single_panel_menu(call: types.CallbackQuery, params: list):
    """
    نمایش منوی مدیریت برای یک کشور/سرور انتخاب شده.
    """
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.", show_alert=True)
        return

    # ✅ اصلاح شده: خط فاصله (-) با \- جایگزین شد
    text = (
        f"👥 *مدیریت کاربران \- {escape_markdown(panel['name'])}*\n\n"
        f"لطفاً یک گزینه را انتخاب کنید:"
    )
    
    # دریافت منو از admin_menu (فرض بر این است که متد در admin_menu وجود دارد)
    # اگر متد manage_single_panel_menu در admin_menu نیست، کد آن را پایین‌تر گذاشته‌ام
    markup = await admin_menu.manage_single_panel_menu(panel['id'], panel['panel_type'], panel['name'])
    
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=markup, parse_mode="MarkdownV2")


# ==============================================================================
# 2. نمایش لیست کاربران پنل با فرمت درخواستی
# Callback: admin:p_users:<panel_id>:<page>
# ==============================================================================

async def handle_panel_users_list(call: types.CallbackQuery, params: list):
    """
    نمایش لیست کاربران یک پنل خاص (نسخه اصلاح شده و بدون ارور پرانتز).
    """
    # هندل کردن پارامترها
    if len(params) == 3 and params[0] == 'panel_users':
        panel_id = int(params[1])
        page = int(params[2])
    else:
        panel_id = int(params[0])
        page = int(params[1])

    PAGE_SIZE = 25
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    try:
        panel_api = await PanelFactory.get_panel(panel['name'])
        users = await panel_api.get_all_users()
        # مرتب‌سازی
        users.sort(key=lambda x: x.get('expire') or x.get('package_days') or 0, reverse=True)
    except Exception as e:
        await bot.answer_callback_query(call.id, "❌ خطا در اتصال به پنل.")
        return

    total_count = len(users)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_users = users[start_idx:end_idx]

    # هدر لیست (اینجا چون متغیر نیست، دستی اسکیپ می‌کنیم)
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
                days_left = int((expire_val - current_time) / 86400)
                status_str = f"{days_left} روز"
            else:
                status_str = "منقضی"
                
        elif package_days is not None:
            try:
                p_days = int(package_days)
                if start_date:
                    s_date_str = str(start_date).split(' ')[0]
                    s_dt = datetime.strptime(s_date_str, "%Y-%m-%d").timestamp()
                    days_passed = int((current_time - s_dt) / 86400)
                    rem_days = p_days - days_passed
                    
                    if rem_days > 0:
                        status_str = f"{rem_days} روز"
                    else:
                        status_str = "منقضی"
                else:
                    # ✅ اصلاح شد: حذف بک‌اسلش‌های دستی از (نو)
                    # تابع escape_markdown خودش پرانتزها را درست می‌کند
                    status_str = f"{p_days} روز (نو)"
            except Exception:
                status_str = f"{package_days} روز"

        # خط زیر هر دو متغیر را اسکیپ می‌کند، پس پرانتزهای داخل name یا status_str مشکلی نخواهند داشت
        lines.append(f"• {escape_markdown(name)} \| 📅 {escape_markdown(status_str)}")

    text = "\n".join(lines)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin:p_users:{panel_id}:{page - 1}"))
    
    if end_idx < total_count:
        nav_buttons.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin:p_users:{panel_id}:{page + 1}"))
        
    if nav_buttons:
        kb.add(*nav_buttons)
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data=f"admin:manage_single_panel:{panel_id}:{panel['panel_type']}"))

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_add_user_to_panel_start(call: types.CallbackQuery, params: list):
    """
    شروع فرآیند افزودن کاربر به یک پنل خاص (با دکمه بازگشت صحیح).
    """
    panel_id = int(params[0])
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    # دریافت اطلاعات پنل برای دکمه بازگشت
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    # ذخیره استیت برای دریافت نام کاربر
    admin_conversations[uid] = {
        'action': 'add_user',
        'step': 'get_name',
        'data': {'panel_name': panel['name']}, # نام پنل برای استفاده بعدی
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': get_new_user_name
    }
    
    # ساخت دکمه بازگشت اختصاصی (بازگشت به منوی همین کشور)
    back_kb = types.InlineKeyboardMarkup()
    back_kb.add(types.InlineKeyboardButton(
        "🔙 بازگشت", 
        callback_data=f"admin:manage_single_panel:{panel['id']}:{panel['panel_type']}"
    ))
    
    text = f"👤 سرور انتخاب شد: *{escape_markdown(panel['name'])}*\n\nلطفاً *نام کاربر* جدید را وارد کنید:"
    
    await _safe_edit(uid, msg_id, text, reply_markup=back_kb)


    # افزودن ایمپورت‌های لازم در بالای فایل اگر نیستند
from bot.db.base import UserUUID, ServerCategory

# ---------------------------------------------------------
# هندلرهای مدیریت دسترسی کشورها
# ---------------------------------------------------------

async def get_user_db_object(session, identifier: str):
    """
    تابع کمکی هوشمند برای پیدا کردن آبجکت User
    از روی Telegram ID یا UUID
    """
    user_db = None
    
    # حالت ۱: اگر شناسه تماماً عدد باشد، یعنی Telegram ID است
    if identifier.isdigit():
        user_id = int(identifier)
        user_db = await session.get(User, user_id)
        
    # حالت ۲: اگر عدد نیست، فرض می‌کنیم UUID است
    else:
        # ابتدا باید UserID را از روی UUID پیدا کنیم
        # (فرض بر این است که متد get_user_uuid_record یا مشابه وجود دارد که رکورد UserUUID برمی‌گرداند)
        # اگر متد get_user_uuid_record ندارید، از کوئری مستقیم استفاده می‌کنیم:
        from sqlalchemy import select
        stmt = select(UserUUID).where(UserUUID.uuid == identifier)
        result = await session.execute(stmt)
        uuid_obj = result.scalar_one_or_none()
        
        if uuid_obj:
            user_db = await session.get(User, uuid_obj.user_id)
            
    return user_db

# =========================================================
# مدیریت دسترسی نودها (Node Access Management) - اصلاح شده
# =========================================================

# تابع کمکی (اگر قبلاً اضافه نکرده‌اید)
async def get_user_db_object(session, identifier: str):
    """تابع کمکی هوشمند برای پیدا کردن کاربر از Telegram ID یا UUID"""
    if identifier.isdigit():
        return await session.get(User, int(identifier))
    else:
        from sqlalchemy import select
        stmt = select(UserUUID).where(UserUUID.uuid == identifier)
        result = await session.execute(stmt)
        uuid_obj = result.scalar_one_or_none()
        if uuid_obj:
            return await session.get(User, uuid_obj.user_id)
    return None

async def handle_user_access_panel_list(call, params):
    """
    نمایش لیست پنل‌ها با طراحی جدید:
    - هدر: نام پنل (غیرقابل کلیک، بدون وضعیت)
    - زیرمجموعه: دکمه‌های پرچمی (کشور اصلی + نودها) برای تغییر وضعیت
    """
    input_id = int(params[0])
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    async with db.get_session() as session:
        from bot.db.base import UserUUID, Panel, PanelNode, ServerCategory
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        # دریافت کاربر و پنل‌های مجاز
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

        # دریافت اطلاعات سیستم
        cats = (await session.execute(select(ServerCategory))).scalars().all()
        cat_map = {c.code: c.emoji for c in cats}
        
        panels = (await session.execute(select(Panel).where(Panel.is_active == True).order_by(Panel.id))).scalars().all()
        all_nodes = (await session.execute(select(PanelNode).where(PanelNode.is_active == True))).scalars().all()

    # گروه‌بندی نودها
    nodes_by_panel = {}
    for node in all_nodes:
        if node.panel_id not in nodes_by_panel:
            nodes_by_panel[node.panel_id] = []
        nodes_by_panel[node.panel_id].append(node)

    # --- ساخت کیبورد ---
    kb = types.InlineKeyboardMarkup()
    
    for panel in panels:
        # 1. وضعیت دسترسی (برای دکمه‌های زیرین)
        is_active = panel.id in allowed_panel_ids
        status_mark = "✅" if is_active else "❌"
        next_action = "disable" if is_active else "enable"
        
        # 2. اطلاعات ظاهری
        panel_flag = cat_map.get(panel.category, "🏳️") if panel.category else "🏳️"
        
        # 3. دکمه هدر (غیرقابل کلیک - فقط نمایش نام و نوع)
        # طبق خواسته شما: کل خط را بگیرد، وضعیت نداشته باشد، کلیک نشود
        header_text = f"{panel_flag} {panel.name} ({panel.panel_type})"
        kb.add(types.InlineKeyboardButton(header_text, callback_data="admin:none"))
        
        # 4. دکمه‌های عملیاتی (کشور اصلی + نودها)
        # همه این دکمه‌ها یک کار را می‌کنند: تغییر وضعیت دسترسی به پنل
        toggle_callback = f"admin:ptgl:{real_uuid_id}:{panel.id}:{next_action}"
        
        row_buttons = []
        
        # الف) دکمه کشور اصلی (Server)
        row_buttons.append(
            types.InlineKeyboardButton(f"{panel_flag} {status_mark}", callback_data=toggle_callback)
        )
        
        # ب) دکمه‌های نودها (Nodes)
        panel_nodes = nodes_by_panel.get(panel.id, [])
        for node in panel_nodes:
            node_flag = cat_map.get(node.country_code, "🏳️")
            row_buttons.append(
                types.InlineKeyboardButton(f"{node_flag} {status_mark}", callback_data=toggle_callback)
            )
        
        # افزودن ردیف دکمه‌های کنترلی (تا 8 عدد در یک خط جا می‌شوند)
        kb.row(*row_buttons)

    # دکمه بازگشت
    back_target = telegram_id if telegram_id else "search_menu"
    back_cb = f"admin:us:{back_target}" if str(back_target).isdigit() else "admin:search_menu"
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))
    
    # متن پیام (با اسکیپ صحیح پرانتزها برای جلوگیری از ارور)
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
        
        # فراخوانی متد دیتابیس
        success = await db.update_user_panel_access_by_id(uuid_id, panel_id, should_enable)
        
        if success:
            status_text = "فعال" if should_enable else "غیرفعال"
            await bot.answer_callback_query(call.id, f"✅ دسترسی {status_text} شد.")
            # رفرش کردن منو
            await handle_user_access_panel_list(call, [uuid_id])
        else:
            await bot.answer_callback_query(call.id, "❌ خطا در تغییر وضعیت.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error toggling access: {e}")
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی.", show_alert=True)