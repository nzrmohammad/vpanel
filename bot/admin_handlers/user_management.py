# bot/admin_handlers/user_management.py

import logging
import asyncio
import time
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, Panel
from bot.utils import _safe_edit, escape_markdown
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
        # ✅ اصلاح: دوبل کردن بک‌اسلش در f-string
        await _safe_edit(uid, msg_id, f"❌ کاربری با مشخصات «{safe_query}» یافت نشد\\.", reply_markup=await admin_menu.search_menu())
        return
    
    if len(users) == 1:
        await show_user_summary(uid, msg_id, users[0].user_id)
    else:
        safe_query = escape_markdown(query)
        # ✅ اصلاح: دوبل کردن بک‌اسلش در f-string
        text = f"🔍 نتایج جستجو برای `{safe_query}` \\({len(users)} مورد\\):"
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
    # ✅ اصلاح: دوبل کردن بک‌اسلش
    await _safe_edit(uid, msg_id, "🔥 برای *پاکسازی کامل* \\(حذف از دیتابیس\\)، آیدی عددی کاربر را بفرستید:", 
                     reply_markup=await admin_menu.cancel_action("admin:search_menu"))

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

async def show_user_summary(admin_id, msg_id, target_user_id, context=None):
    """نمایش پروفایل دقیق کاربر (مشابه پنل کاربری + اطلاعات ادمین)"""
    async with db.get_session() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await _safe_edit(admin_id, msg_id, "❌ کاربر در دیتابیس یافت نشد.", reply_markup=await admin_menu.main())
            return
            
        uuids = await db.uuids(target_user_id)
        active_uuids = [u for u in uuids if u['is_active']]
        
        if active_uuids:
            # دریافت اطلاعات کامل برای فرمت‌دهی
            main_uuid = active_uuids[0]['uuid']
            info = await combined_handler.get_combined_user_info(str(main_uuid))
            
            if info:
                info['db_id'] = active_uuids[0]['id']
                # دریافت تعداد پرداخت‌ها
                history = await db.get_user_payment_history(active_uuids[0]['id'])
                payment_count = len(history)
                
                # تولید متن پایه با فرمتر
                formatted_body = await user_formatter.profile_info(info, 'fa')
                
                # ✅ تغییر خط اول (هدر) برای افزودن تعداد پرداخت
                lines = formatted_body.split('\n')
                # خط اول معمولاً: 👤 نام : Name (✅ فعال)
                # آن را بازنویسی می‌کنیم:
                status_emoji = "✅" if info.get('is_active') else "❌"
                status_text = "فعال" if info.get('is_active') else "غیرفعال"
                new_header = f"👤 نام : {escape_markdown(user.first_name or 'Unknown')}  ({status_emoji} {status_text} \| {payment_count} پرداخت)"
                lines[0] = f"*{new_header}*"
                
                admin_info = []
                if user.admin_note:
                    admin_info.append(f"\n📝 یادداشت: {escape_markdown(user.admin_note)}")
                
                admin_info.append(f"\n🆔 آیدی عددی: `{target_user_id}`")
                admin_info.append(f"💰 کیف پول: `{int(user.wallet_balance or 0):,}`")
                
                text = "\n".join(lines) + "".join(admin_info)
            else:
                text = "❌ خطا در دریافت اطلاعات از سرور."
        else:
            text = f"👤 کاربر: {escape_markdown(user.first_name or '')}\n🔴 وضعیت: غیرفعال (بدون سرویس فعال)\n🆔 `{target_user_id}`"

    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    # پنل تایپ را پیش‌فرض hiddify می‌گیریم یا از دیتابیس می‌خوانیم (برای دکمه‌ها)
    panel_type = 'hiddify' 
    
    markup = await admin_menu.user_interactive_menu(str(user.user_id), bool(active_uuids), panel_type, back_callback=back_cb)
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")
# ==============================================================================
# 3. افزودن کاربر جدید (Add User Flow)
# ==============================================================================

async def handle_add_user_start(call: types.CallbackQuery, params: list):
    panel_type = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        stmt = select(Panel).where(and_(Panel.panel_type == panel_type, Panel.is_active == True))
        result = await session.execute(stmt)
        panels = result.scalars().all()
    
    if not panels:
        await bot.answer_callback_query(call.id, "❌ هیچ پنل فعالی از این نوع یافت نشد.", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in panels:
        kb.add(types.InlineKeyboardButton(f"سرور: {p.name}", callback_data=f"admin:add_user_select_panel:{p.name}"))
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:management_menu"))
    
    await _safe_edit(uid, msg_id, f"➕ **افزودن کاربر به {panel_type.capitalize()}**\n\nلطفاً سرور مورد نظر را انتخاب کنید:", reply_markup=kb, parse_mode="Markdown")

async def handle_add_user_select_panel_callback(call: types.CallbackQuery, params: list):
    panel_name = params[0]
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    admin_conversations[uid] = {
        'action': 'add_user',
        'step': 'get_name',
        'data': {'panel_name': panel_name},
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': get_new_user_name
    }
    
    await _safe_edit(uid, msg_id, 
                     f"👤 سرور انتخاب شد: *{escape_markdown(panel_name)}*\n\nلطفاً *نام کاربر* را وارد کنید:", 
                     reply_markup=await admin_menu.cancel_action())

async def get_new_user_name(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['data']['name'] = text
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    msg_id = admin_conversations[uid]['msg_id']
    
    # ✅ اصلاح: دوبل کردن بک‌اسلش
    await _safe_edit(uid, msg_id, 
                     "📦 لطفاً *حجم محدودیت \\(GB\\)* را وارد کنید \\(عدد\\):", 
                     reply_markup=await admin_menu.cancel_action())

async def get_new_user_limit(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    try:
        limit = float(text)
        admin_conversations[uid]['data']['limit'] = limit
        admin_conversations[uid]['next_handler'] = get_new_user_days
        msg_id = admin_conversations[uid]['msg_id']
        
        # ✅ اصلاح: دوبل کردن بک‌اسلش
        await _safe_edit(uid, msg_id, 
                         "📅 لطفاً *تعداد روز اعتبار* را وارد کنید \\(عدد\\):", 
                         reply_markup=await admin_menu.cancel_action())
    except ValueError:
        msg_id = admin_conversations[uid]['msg_id']
        # ✅ اصلاح: دوبل کردن بک‌اسلش
        await _safe_edit(uid, msg_id, "❌ لطفاً فقط عدد وارد کنید. حجم \\(GB\\):", reply_markup=await admin_menu.cancel_action())

async def get_new_user_days(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    try:
        days = int(text)
        data = admin_conversations.pop(uid)['data']
        msg_id = admin_conversations[uid]['msg_id'] 
        
        await _safe_edit(uid, msg_id, "⏳ در حال ساخت کاربر در پنل...", reply_markup=None)
        
        panel_name = data['panel_name']
        name = data['name']
        limit = data['limit']
        
        panel_api = await PanelFactory.get_panel(panel_name)
        new_user = await panel_api.add_user(name, limit, days)
        
        if new_user:
            identifier = new_user.get('uuid') or name 
            
            # ✅ اصلاح: دوبل کردن بک‌اسلش در f-string
            res_text = (
                f"✅ کاربر با موفقیت ساخته شد\\!\n\n"
                f"👤 نام: `{escape_markdown(name)}`\n"
                f"📦 حجم: `{limit} GB`\n"
                f"📅 مدت: `{days} روز`\n"
                f"🔑 شناسه: `{escape_markdown(str(identifier))}`"
            )
            
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت", callback_data=f"admin:management_menu"))
            
            await _safe_edit(uid, msg_id, res_text, reply_markup=kb, parse_mode="MarkdownV2")
            
        else:
            await _safe_edit(uid, msg_id, "❌ خطا در ساخت کاربر در پنل. لطفاً لاگ را بررسی کنید.", reply_markup=await admin_menu.main())
            
    except ValueError:
        if uid in admin_conversations:
            msg_id = admin_conversations[uid]['msg_id']
            await _safe_edit(uid, msg_id, "❌ لطفاً فقط عدد صحیح وارد کنید. روز:", reply_markup=await admin_menu.cancel_action())
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        if uid in admin_conversations:
            msg_id = admin_conversations[uid].get('msg_id')
            await _safe_edit(uid, msg_id, f"❌ خطای غیرمنتظره: {e}", reply_markup=await admin_menu.main())

# ==============================================================================
# 4. ویرایش سرویس (Edit User - Volume/Days)
# ==============================================================================

async def handle_edit_user_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    markup = await admin_menu.edit_user_menu(target_id, 'both') 
    await _safe_edit(uid, msg_id, "🔧 چه تغییری می‌خواهید اعمال کنید؟", reply_markup=markup)

async def handle_ask_edit_value(call, params):
    action, scope, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    
    admin_conversations[uid] = {
        'step': 'edit_value',
        'msg_id': msg_id,
        'action': action,
        'scope': scope,
        'target_id': target_id,
        'timestamp': time.time(),
        'next_handler': process_edit_value
    }
    
    # ✅ اصلاح: دوبل کردن بک‌اسلش در f-string
    text = f"🔢 لطفاً مقدار *{action_name}* را که می‌خواهید *اضافه* کنید وارد نمایید \\(عدد مثبت برای افزودن، منفی برای کسر\\):"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

async def process_edit_value(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    msg_id, target_id = data['msg_id'], data['target_id']
    action, scope = data['action'], data['scope']
    
    try:
        value = float(text)
        if value == 0: raise ValueError
    except:
        await _safe_edit(uid, msg_id, "❌ مقدار نامعتبر.", reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))
        return

    await _safe_edit(uid, msg_id, "⏳ در حال اعمال تغییرات روی پنل‌ها...", reply_markup=None)
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await _safe_edit(uid, msg_id, "❌ کاربر سرویس فعالی ندارد.", reply_markup=await admin_menu.user_interactive_menu(target_id, False, 'both'))
        return
        
    main_uuid_str = str(uuids[0]['uuid'])
    add_gb = value if 'gb' in action else 0
    add_days = int(value) if 'days' in action else 0
    
    success = await combined_handler.modify_user_on_all_panels(
        identifier=main_uuid_str,
        add_gb=add_gb,
        add_days=add_days
    )
    
    if success:
        result_text = f"✅ تغییرات با موفقیت اعمال شد.\n➕ {value} {'GB' if add_gb else 'روز'}"
    else:
        result_text = "❌ خطا در اعمال تغییرات روی پنل(ها)."
        
    await _safe_edit(uid, msg_id, result_text, reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))

async def handle_select_panel_for_edit(call, params):
    pass 

# ==============================================================================
# 5. تغییر وضعیت (Toggle Status)
# ==============================================================================

async def handle_toggle_status(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    text = "⚙️ آیا می‌خواهید وضعیت کاربر را تغییر دهید؟\n(غیرفعال کردن باعث قطع دسترسی در تمام پنل‌ها می‌شود)"
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🔴 غیرفعال کردن", callback_data=f"admin:tglA:disable:{target_id}"),
        types.InlineKeyboardButton("🟢 فعال کردن", callback_data=f"admin:tglA:enable:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb)

async def handle_toggle_status_action(call, params):
    action, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
        return
        
    uuid_str = str(uuids[0]['uuid'])
    uuid_id = uuids[0]['id']
    
    if action == 'disable':
        await db.deactivate_uuid(uuid_id)
        await combined_handler.delete_user_from_all_panels(uuid_str)
        msg = "🔴 کاربر غیرفعال و از پنل‌ها حذف شد."
        
    else: 
        await bot.answer_callback_query(call.id, "برای فعال‌سازی مجدد، لطفاً اشتراک را تمدید کنید.", show_alert=True)
        return

    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.user_interactive_menu(target_id, False, 'both'))

# ==============================================================================
# 6. تاریخچه پرداخت و ثبت دستی
# ==============================================================================

async def handle_payment_history(call, params):
    """نمایش تاریخچه پرداخت"""
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(target_id)
    if not uuids:
        await bot.answer_callback_query(call.id, "بدون سرویس.")
        return
        
    history = await db.get_user_payment_history(uuids[0]['id'])
    
    if not history:
        await _safe_edit(uid, msg_id, "📜 هیچ سابقه‌ای یافت نشد.", reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
        return
    
    text = f"📜 *تاریخچه تمدیدها* \\({len(history)} مورد\\):\n\n"
    for item in history:
        dt_str = item['payment_date'].strftime("%Y-%m-%d %H:%M")
        dt_safe = dt_str.replace("-", "\\-").replace(":", "\\:")
        text += f"📅 {dt_safe}\n"
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗑 پاکسازی تاریخچه", callback_data=f"admin:reset_phist:{uuids[0]['id']}:{target_id}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

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
    """دریافت یادداشت از ادمین"""
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {
        'step': 'save_note', 
        'msg_id': msg_id, 
        'target_id': int(target_id),
        'timestamp': time.time(),
        'next_handler': process_save_note
    }
    
    text = "📝 یادداشت خود را بنویسید \\(برای حذف، 'پاک' بفرستید\\):"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

async def process_save_note(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    target_id = data['target_id']
    msg_id = data['msg_id']
    
    note_val = None if text == 'پاک' else text
    await db.update_user_note(target_id, note_val)
    
    await _safe_edit(uid, msg_id, "✅ یادداشت ذخیره شد.", 
                     reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

async def handle_delete_user_confirm(call, params):
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
    # ✅ اصلاح: دوبل کردن بک‌اسلش در f-string
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