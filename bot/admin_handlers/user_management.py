# bot/admin_handlers/user_management.py

import logging
import asyncio
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, or_, cast, String, func, desc, and_
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, Panel, WalletTransaction
from bot.utils import _safe_edit, escape_markdown, format_currency
from bot.formatters import admin_formatter
from bot import combined_handler
from bot.services.panels import PanelFactory

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
    admin_conversations[uid] = {'step': 'global_search', 'msg_id': msg_id}
    
    text = "🔎 لطفاً **نام**، **نام کاربری** یا بخشی از **UUID** کاربر را ارسال کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))
    bot.register_next_step_handler(call.message, process_search_input)

async def handle_search_by_telegram_id_convo(call, params):
    """شروع جستجو با آیدی عددی تلگرام"""
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'tid_search', 'msg_id': msg_id}
    
    text = "🆔 لطفاً **آیدی عددی تلگرام** (User ID) کاربر را ارسال کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))
    bot.register_next_step_handler(call.message, process_search_input)

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
            # جستجوی ترکیبی (نام، یوزرنیم، UUID)
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
        await _safe_edit(uid, msg_id, f"❌ کاربری با مشخصات «{query}» یافت نشد.", reply_markup=await admin_menu.search_menu())
        return
    
    if len(users) == 1:
        # اگر یک نفر پیدا شد، مستقیم به پروفایلش برو
        await show_user_summary(uid, msg_id, users[0].user_id)
    else:
        # نمایش لیست نتایج (محدود به ۱۰ مورد)
        text = f"🔍 نتایج جستجو برای `{query}` ({len(users)} مورد):"
        kb = types.InlineKeyboardMarkup(row_width=1)
        for u in users[:10]:
            display = f"{u.first_name or 'NoName'} (@{u.username or 'NoUser'})"
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:us:{u.user_id}:s")) # s for search context
        
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:search_menu"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")

async def handle_purge_user_convo(call, params):
    """شروع پروسه حذف کامل (Purge) با آیدی"""
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'purge_user', 'msg_id': msg_id}
    await _safe_edit(uid, msg_id, "🔥 برای **پاکسازی کامل** (حذف از دیتابیس)، آیدی عددی کاربر را بفرستید:", 
                     reply_markup=await admin_menu.cancel_action("admin:search_menu"))
    bot.register_next_step_handler(call.message, process_purge_user)

async def process_purge_user(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    msg_id = admin_conversations.pop(uid)['msg_id']
    
    if not text.isdigit():
        await _safe_edit(uid, msg_id, "❌ آیدی نامعتبر.", reply_markup=await admin_menu.search_menu())
        return
        
    target_id = int(text)
    # حذف از دیتابیس
    success = await db.purge_user_by_telegram_id(target_id)
    if success:
        await _safe_edit(uid, msg_id, f"✅ کاربر {target_id} با موفقیت کامل پاکسازی شد.", reply_markup=await admin_menu.search_menu())
    else:
        await _safe_edit(uid, msg_id, "❌ کاربر یافت نشد یا خطا در حذف.", reply_markup=await admin_menu.search_menu())

# ==============================================================================
# 2. مدیریت و نمایش کاربر (User Profile)
# ==============================================================================

async def handle_show_user_summary(call, params):
    """هندلر کال‌بک نمایش پروفایل کاربر"""
    # params: [target_id, context_suffix] (optional)
    target_id = params[0]
    # تشخیص اینکه آیا ورودی ID عددی است یا UUID (معمولاً در لیست‌ها ID عددی داریم)
    # اگر UUID بود، باید UserID را پیدا کنیم
    uid, msg_id = call.from_user.id, call.message.message_id
    
    real_user_id = None
    if str(target_id).isdigit():
        real_user_id = int(target_id)
    else:
        # اگر UUID بود
        real_user_id = await db.get_user_id_by_uuid(target_id)
    
    if not real_user_id:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")
        return

    # context برای دکمه بازگشت (مثلاً بازگشت به جستجو یا لیست)
    context = params[1] if len(params) > 1 else None
    await show_user_summary(uid, msg_id, real_user_id, context)

async def show_user_summary(admin_id, msg_id, target_user_id, context=None):
    """تابع اصلی نمایش اطلاعات کاربر"""
    async with db.get_session() as session:
        user = await session.get(User, target_user_id)
        if not user:
            await _safe_edit(admin_id, msg_id, "❌ کاربر در دیتابیس یافت نشد.", reply_markup=await admin_menu.main())
            return
            
        # دریافت اکانت‌های فعال
        uuids = await db.uuids(target_user_id)
        active_uuids = [u for u in uuids if u['is_active']]
        
        # دریافت مجموع مصرف (Hiddify + Marzban)
        # برای سادگی، فعلاً مصرف سرویس اول را نشان می‌دهیم یا جمع کل
        total_usage = 0
        total_limit = 0
        main_uuid = None
        
        if active_uuids:
            # دریافت اطلاعات لایو از پنل‌ها
            main_uuid = active_uuids[0]['uuid']
            info = await combined_handler.get_combined_user_info(str(main_uuid))
            if info:
                total_usage = info.get('current_usage_GB', 0)
                total_limit = info.get('usage_limit_GB', 0)

    status_emoji = "🟢" if active_uuids else "🔴"
    note = f"\n📝 یادداشت: {user.admin_note}" if user.admin_note else ""
    
    text = (
        f"👤 **پروفایل کاربر**\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🆔 شناسه: `{user.user_id}`\n"
        f"📛 نام: {escape_markdown(user.first_name or 'نامشخص')}\n"
        f"🔗 یوزرنیم: @{escape_markdown(user.username or 'ندارد')}\n"
        f"💰 کیف پول: `{int(user.wallet_balance or 0):,}` تومان\n"
        f"🎫 سرویس‌های فعال: {len(active_uuids)}\n"
        f"{status_emoji} وضعیت کلی: {'فعال' if active_uuids else 'غیرفعال'}\n"
        f"📊 مصرف کل (تخمینی): `{total_usage:.2f}` / `{total_limit:.0f}` GB\n"
        f"{note}"
    )
    
    # تعیین دکمه بازگشت بر اساس کانتکست
    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    
    # استفاده از پنل پیش‌فرض برای دکمه‌ها (می‌تواند بهبود یابد)
    panel_type = 'hiddify' 
    
    markup = await admin_menu.user_interactive_menu(str(user.user_id), bool(active_uuids), panel_type, back_callback=back_cb)
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="Markdown")

# ==============================================================================
# 3. ویرایش سرویس (Edit User - Volume/Days)
# ==============================================================================

async def handle_edit_user_menu(call, params):
    """منوی انتخاب نوع ویرایش (حجم یا زمان)"""
    # params[0] = user_id
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # برای ویرایش نیاز است بدانیم روی کدام پنل اعمال شود
    # فعلاً منویی برای انتخاب پنل یا اعمال روی همه نشان می‌دهیم
    # اما admin_menu.edit_user_menu دکمه‌های مستقیم دارد.
    
    markup = await admin_menu.edit_user_menu(target_id, 'both') # Default to both/auto
    await _safe_edit(uid, msg_id, "🔧 چه تغییری می‌خواهید اعمال کنید؟", reply_markup=markup)

async def handle_ask_edit_value(call, params):
    """پرسیدن مقدار عددی برای افزایش حجم یا روز"""
    # params: [action_type, panel_scope, target_id]
    action, scope, target_id = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    action_name = "حجم (GB)" if "gb" in action else "زمان (روز)"
    
    admin_conversations[uid] = {
        'step': 'edit_value',
        'msg_id': msg_id,
        'action': action,
        'scope': scope,
        'target_id': target_id
    }
    
    text = f"🔢 لطفاً مقدار **{action_name}** را که می‌خواهید **اضافه** کنید وارد نمایید (عدد مثبت برای افزودن، منفی برای کسر):"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))
    bot.register_next_step_handler(call.message, process_edit_value)

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
    
    # پیدا کردن UUID های کاربر
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await _safe_edit(uid, msg_id, "❌ کاربر سرویس فعالی ندارد.", reply_markup=await admin_menu.user_interactive_menu(target_id, False, 'both'))
        return
        
    # اعمال روی اولین UUID (معمولاً کاربر یک UUID دارد)
    # اگر چندتا داشت، باید منطق پیچیده‌تری باشد یا روی همه اعمال شود
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
        # ثبت در دیتابیس اگر لازم است (مثلاً برای تاریخچه)
        # اما modify_user_on_all_panels خودش با پنل‌ها سینک می‌کند
    else:
        result_text = "❌ خطا در اعمال تغییرات روی پنل(ها)."
        
    await _safe_edit(uid, msg_id, result_text, reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))

# این هندلر برای انتخاب پنل در صورت نیاز (فعلاً استفاده نشده در فلو اصلی ولی در روتر هست)
async def handle_select_panel_for_edit(call, params):
    pass 

# ==============================================================================
# 4. تغییر وضعیت (Toggle Status)
# ==============================================================================

async def handle_toggle_status(call, params):
    """منوی تغییر وضعیت (فعال/غیرفعال)"""
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
    """اجرای تغییر وضعیت"""
    action, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
        return
        
    uuid_str = str(uuids[0]['uuid'])
    uuid_id = uuids[0]['id']
    
    if action == 'disable':
        # حذف موقت از پنل‌ها یا تغییر وضعیت به غیرفعال
        # در اینجا از delete_user_from_all_panels استفاده نمی‌کنیم چون می‌خواهیم فقط غیرفعال شود
        # اما پنل‌ها معمولاً متد disable ندارند، مگر اینکه لیمیت را 0 کنیم یا تاریخ را منقضی
        # روش بهتر: Deactivate در دیتابیس و حذف از پنل (کاربر باید بداند)
        
        # راه حل ساده: فعلاً فقط در دیتابیس غیرفعال می‌کنیم
        await db.deactivate_uuid(uuid_id)
        # و حذف از پنل‌ها (طبق منطق مرسوم)
        await combined_handler.delete_user_from_all_panels(uuid_str)
        
        msg = "🔴 کاربر غیرفعال و از پنل‌ها حذف شد."
        
    else: # Enable
        # فعال‌سازی مجدد در دیتابیس
        # و افزودن مجدد به پنل‌ها (نیاز به بازسازی دارد)
        # این بخش پیچیده است چون باید پلان کاربر را بدانیم.
        # فعلاً فقط دیتابیس را فعال می‌کنیم و پیغام می‌دهیم که باید تمدید شود.
        
        # برای فعال‌سازی واقعی، بهتر است از دکمه "تمدید اشتراک" استفاده شود.
        await bot.answer_callback_query(call.id, "برای فعال‌سازی مجدد، لطفاً اشتراک را تمدید کنید.", show_alert=True)
        return

    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.user_interactive_menu(target_id, False, 'both'))

# ==============================================================================
# 5. تاریخچه پرداخت و ثبت دستی (Payment)
# ==============================================================================

async def handle_payment_history(call, params):
    """نمایش تاریخچه پرداخت"""
    # params: [target_id, page, context]
    target_id = int(params[0])
    page = int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(target_id)
    if not uuids:
        await bot.answer_callback_query(call.id, "بدون سرویس.")
        return
        
    # تاریخچه پرداخت مربوط به اولین سرویس
    history = await db.get_user_payment_history(uuids[0]['id'])
    
    if not history:
        await _safe_edit(uid, msg_id, "📜 هیچ سابقه‌ای یافت نشد.", reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
        return
        
    text = f"📜 **تاریخچه تمدیدها** ({len(history)} مورد):\n\n"
    for item in history:
        date_str = item['payment_date'].strftime("%Y-%m-%d %H:%M")
        text += f"📅 {date_str}\n"
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗑 پاکسازی تاریخچه", callback_data=f"admin:reset_phist:{uuids[0]['id']}:{target_id}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")

async def handle_log_payment(call, params):
    """ثبت دستی یک پرداخت (تمدید)"""
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    
    if uuids:
        await db.add_payment_record(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ پرداخت ثبت شد.")
        # رفرش تاریخچه اگر باز بود، یا فقط نوتیفیکیشن
    else:
        await bot.answer_callback_query(call.id, "سرویسی برای ثبت پرداخت وجود ندارد.", show_alert=True)

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
# 6. ریست‌ها و ابزارها (Resets & Tools)
# ==============================================================================

async def handle_user_reset_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی (پنل‌ها)", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("🎂 حذف تاریخ تولد", callback_data=f"admin:us_rb:{target_id}"),
        types.InlineKeyboardButton("⏳ ریست محدودیت انتقال", callback_data=f"admin:us_rtr:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, "♻️ کدام مورد را می‌خواهید ریست کنید؟", reply_markup=kb)

async def handle_reset_usage_menu(call, params):
    target_id = params[0]
    # نمایش منوی انتخاب پنل برای ریست حجم
    markup = await admin_menu.reset_usage_selection_menu(target_id, "rsa") # rsa = Reset Usage Action
    await _safe_edit(call.from_user.id, call.message.message_id, "انتخاب پنل برای ریست حجم:", reply_markup=markup)

async def handle_reset_usage_action(call, params):
    # params: [panel_scope, target_id]
    scope, target_id = params[0], params[1]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuids = await db.uuids(int(target_id))
    if not uuids: return
    uuid_str = str(uuids[0]['uuid'])
    
    await _safe_edit(uid, msg_id, "⏳ در حال ریست حجم...", reply_markup=None)
    
    # باید هندلر مربوطه صدا زده شود
    # برای سادگی، فرض می‌کنیم متد ریست در combined_handler نیست و باید مستقیم صدا زد
    # اما می‌توان از modify_user_on_all_panels با فلگ خاص استفاده کرد یا متد جدید
    
    # پیاده‌سازی مستقیم:
    panels = await db.get_active_panels()
    success_count = 0
    
    for p in panels:
        if scope != 'both' and p['panel_type'] != scope: continue # فیلتر پنل
        
        handler = await PanelFactory.get_panel(p['name'])
        try:
            # متد reset_user_usage باید در کلاس‌های پنل پیاده‌سازی شده باشد
            # برای هیدیفای: usage=0، برای مرزبان: endpoint reset
            # در فایل‌های شما: HiddifyPanel.reset_user_usage و MarzbanPanel.reset_user_usage وجود دارد.
            
            identifier = uuid_str
            if p['panel_type'] == 'marzban':
                identifier = await db.get_marzban_username_by_uuid(uuid_str) or f"marzban_{uuid_str}" # Fallback
                
            if await handler.reset_user_usage(identifier):
                success_count += 1
        except Exception as e:
            logger.error(f"Reset usage failed for {p['name']}: {e}")

    if success_count > 0:
        await _safe_edit(uid, msg_id, "✅ حجم کاربر در پنل‌های انتخابی ریست شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در ریست حجم.", 
                         reply_markup=await admin_menu.user_interactive_menu(target_id, True, 'both'))

async def handle_reset_birthday(call, params):
    target_id = int(params[0])
    await db.reset_user_birthday(target_id)
    await bot.answer_callback_query(call.id, "✅ تاریخ تولد حذف شد.")
    await handle_user_reset_menu(call, params)

async def handle_reset_transfer_cooldown(call, params):
    target_id = int(params[0])
    # پیدا کردن UUID
    uuids = await db.uuids(target_id)
    if uuids:
        # حذف رکوردهای انتقال از دیتابیس (TransferDB)
        # چون کلاس TransferDB میکس شده، متد delete_transfer_history در db موجود است
        await db.delete_transfer_history(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ محدودیت انتقال ریست شد.")
    else:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
    
    await handle_user_reset_menu(call, params)

# ==============================================================================
# 7. هشدارها و پیام‌ها (Warnings & Notes)
# ==============================================================================

async def handle_user_warning_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔔 یادآوری پرداخت", callback_data=f"admin:us_spn:{target_id}"),
        types.InlineKeyboardButton("🚨 هشدار قطع سرویس", callback_data=f"admin:us_sdw:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    
    await _safe_edit(uid, msg_id, "⚠️ ارسال پیام هشدار به کاربر:", reply_markup=kb)

async def handle_send_payment_reminder(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    
    # دریافت زبان کاربر
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    
    msg = get_string('payment_reminder_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ پیام ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا در ارسال (شاید ربات بلاک شده).", show_alert=True)

async def handle_send_disconnection_warning(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    
    msg = get_string('disconnection_warning_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ هشدار ارسال شد.", show_alert=True)
        # لاگ کردن هشدار
        uuids = await db.uuids(target_id)
        if uuids:
            await db.log_warning(uuids[0]['id'], 'manual_disconnect_warn')
    except:
        await bot.answer_callback_query(call.id, "❌ خطا در ارسال.", show_alert=True)

async def handle_ask_for_note(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {'step': 'save_note', 'msg_id': msg_id, 'target_id': int(target_id)}
    
    await _safe_edit(uid, msg_id, "📝 لطفاً یادداشت خود را برای این کاربر بنویسید (برای حذف یادداشت، 'پاک' بفرستید):",
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))
    bot.register_next_step_handler(call.message, process_save_note)

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

async def manual_winback_handler(call, params):
    """ارسال پیام دلتنگی (Winback)"""
    target_id = int(params[0])
    # می‌توانیم متن پیش‌فرض یا کاستوم داشته باشیم
    msg = "👋 سلام! دلمون برات تنگ شده. 🌹\nخیلی وقته سری به ما نزدی. یه کد تخفیف ویژه برات داریم:\n🎁 Code: `WELCOME_BACK`"
    
    try:
        await bot.send_message(target_id, msg, parse_mode="Markdown")
        await bot.answer_callback_query(call.id, "✅ پیام ارسال شد.")
    except:
        await bot.answer_callback_query(call.id, "❌ ارسال ناموفق.")

async def handle_churn_contact_user(call, params):
    """تماس با کاربر در لیست ریزش (Churn)"""
    # در اینجا فقط به هندلر ارسال پیام ارجاع می‌دهیم
    # params: [user_id]
    from bot.admin_handlers.user_management import handle_user_send_msg 
    # اما چون در همان فایل هستیم، نیاز به ایمپورت نیست، فقط باید به router وصل باشد
    # یا مستقیماً لاجیک را اجرا کنیم.
    # برای سادگی، لاجیک ارسال پیام را دوباره استفاده می‌کنیم اما با context خاص
    pass # Implementation shared with send_msg

async def handle_churn_send_offer(call, params):
    """ارسال پیشنهاد ویژه به کاربر ریزشی"""
    await manual_winback_handler(call, params)

# ==============================================================================
# 8. حذف و دستگاه‌ها (Delete & Devices)
# ==============================================================================

async def handle_delete_user_confirm(call, params):
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
    await _safe_edit(call.from_user.id, call.message.message_id, 
                     f"⚠️ **هشدار:** حذف کاربر `{target_id}` باعث حذف تمام سوابق و قطع دسترسی او می‌شود.\nآیا مطمئن هستید؟",
                     reply_markup=markup, parse_mode="Markdown")

async def handle_delete_user_action(call, params):
    # params: [decision, panel, target_id]
    decision, target_id = params[0], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    if decision == 'cancel':
        await show_user_summary(uid, msg_id, int(target_id))
        return
        
    # اجرای حذف
    uuids = await db.uuids(int(target_id))
    
    # 1. حذف از پنل‌ها
    if uuids:
        await combined_handler.delete_user_from_all_panels(str(uuids[0]['uuid']))
    
    # 2. حذف از دیتابیس
    await db.purge_user_by_telegram_id(int(target_id))
    
    await _safe_edit(uid, msg_id, "✅ کاربر با موفقیت حذف شد.", reply_markup=await admin_menu.management_menu())

async def handle_delete_devices_confirm(call, params):
    target_id = params[0]
    # نمایش تعداد دستگاه‌ها
    uuids = await db.uuids(int(target_id))
    count = 0
    if uuids:
        count = await db.count_user_agents(uuids[0]['id'])
        
    text = f"📱 کاربر دارای {count} دستگاه ثبت شده است.\nآیا می‌خواهید همه را حذف کنید؟ (کاربر مجبور به لاگین مجدد نمی‌شود، فقط لیست پاک می‌شود)"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("بله، پاک کن", callback_data=f"admin:del_devs_exec:{target_id}"),
        types.InlineKeyboardButton("خیر", callback_data=f"admin:us:{target_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)

async def handle_delete_devices_action(call, params):
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_user_agents_by_uuid_id(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ دستگاه‌ها پاک شدند.")
    else:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
        
    await show_user_summary(call.from_user.id, call.message.message_id, target_id)

# ==============================================================================
# 9. تمدید و نشان‌ها (Renew & Badges)
# ==============================================================================

async def handle_renew_subscription_menu(call, params):
    """منوی انتخاب پلن برای تمدید"""
    target_id = params[0]
    
    # دریافت پلن‌ها از دیتابیس
    plans = await db.get_all_plans()
    if not plans:
        await bot.answer_callback_query(call.id, "هیچ پلنی تعریف نشده است.", show_alert=True)
        return
        
    markup = await admin_menu.select_plan_for_renew_menu(target_id, "", plans)
    await _safe_edit(call.from_user.id, call.message.message_id, "🔄 پلن جدید را برای تمدید انتخاب کنید:", reply_markup=markup)

async def handle_renew_select_plan_menu(call, params):
    # این هندلر واسط است، در واقع همان قبلی است
    await handle_renew_subscription_menu(call, params)

async def handle_renew_apply_plan(call, params):
    """اجرای تمدید"""
    # params: [plan_id, target_id]
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    
    uuids = await db.uuids(target_id)
    if not uuids:
        await bot.answer_callback_query(call.id, "سرویسی برای تمدید نیست.")
        return
    
    uuid_str = str(uuids[0]['uuid'])
    
    await _safe_edit(uid, msg_id, "⏳ در حال تمدید...", reply_markup=None)
    
    # تمدید = افزودن حجم و روز پلن انتخاب شده
    # نکته: اگر می‌خواهید "جایگزین" شود، باید متد modify را با set_gb فراخوانی کنید
    # اما معمولاً تمدید یعنی افزودن.
    # در اینجا فرض بر افزودن است.
    
    success = await combined_handler.modify_user_on_all_panels(
        identifier=uuid_str,
        add_gb=plan['volume_gb'],
        add_days=plan['days']
    )
    
    if success:
        # ثبت تراکنش (اختیاری - اگر پول گرفته شده دستی)
        await db.add_payment_record(uuids[0]['id'])
        await _safe_edit(uid, msg_id, f"✅ سرویس با پلن «{plan['name']}» تمدید شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در تمدید سرویس.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

async def handle_award_badge_menu(call, params):
    target_id = params[0]
    markup = await admin_menu.award_badge_menu(target_id, "")
    await _safe_edit(call.from_user.id, call.message.message_id, "🏅 نشان مورد نظر را انتخاب کنید:", reply_markup=markup)

async def handle_award_badge(call, params):
    badge_code, target_id = params[0], int(params[1])
    
    if await db.add_achievement(target_id, badge_code):
        await bot.answer_callback_query(call.id, "✅ نشان اهدا شد.")
        # ارسال پیام به کاربر
        try:
            await bot.send_message(target_id, f"🎉 تبریک! شما نشان جدیدی دریافت کردید.")
        except: pass
    else:
        await bot.answer_callback_query(call.id, "این کاربر قبلاً این نشان را دارد.")
        
    await handle_award_badge_menu(call, [str(target_id)])

async def handle_achievement_request_callback(call, params):
    """تایید یا رد درخواست نشان"""
    # params comes from router parsing (action:req_id)
    # But callback data is admin:ach_approve:req_id
    action = call.data.split(':')[1] # ach_approve or ach_reject
    req_id = int(params[0])
    
    status = 'approved' if 'approve' in action else 'rejected'
    await db.update_achievement_request_status(req_id, status, call.from_user.id)
    
    req = await db.get_achievement_request(req_id)
    if req and status == 'approved':
        await db.add_achievement(req['user_id'], req['badge_code'])
        # جایزه امتیاز
        await db.add_achievement_points(req['user_id'], 50) # امتیاز نمادین
        
        try:
            await bot.send_message(req['user_id'], "✅ درخواست نشان شما تایید شد!")
        except: pass
        
    await bot.edit_message_caption(f"{call.message.caption}\n\nوضعیت: {status}", call.from_user.id, call.message.message_id)

# ==============================================================================
# 10. ابزارهای سیستمی (System Tools)
# ==============================================================================

async def handle_system_tools_menu(call, params):
    # این توسط admin_router هندل می‌شود و به admin_menu.system_tools_menu ارجاع می‌دهد
    pass 

async def handle_reset_all_daily_usage_confirm(call, params):
    await _safe_edit(call.from_user.id, call.message.message_id, 
                     "⚠️ آیا مطمئن هستید؟ این کار مصرف روزانه تمام کاربران را صفر می‌کند.",
                     reply_markup=await admin_menu.cancel_action("admin:system_tools_menu"))
    # دکمه تایید باید جداگانه هندل شود یا در همین جا دکمه inline بسازیم
    # برای سادگی یک دکمه inline می‌سازیم
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ بله، انجام بده", callback_data="admin:reset_all_daily_usage_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=kb)

async def handle_reset_all_daily_usage_action(call, params):
    await _safe_edit(call.from_user.id, call.message.message_id, "⏳ در حال انجام...", reply_markup=None)
    # از db.usage برای حذف اسنپ‌شات‌های امروز استفاده می‌کنیم
    count = await db.delete_all_daily_snapshots()
    await _safe_edit(call.from_user.id, call.message.message_id, f"✅ انجام شد. {count} رکورد پاک شد.", 
                     reply_markup=await admin_menu.system_tools_menu())

async def handle_force_snapshot(call, params):
    """اجرای دستی اسنپ‌شات (آپدیت آمار)"""
    await bot.answer_callback_query(call.id, "دستور اجرا شد. (این قابلیت در نسخه کامل فعال می‌شود)")
    # در اینجا باید تسک snapshot را صدا بزنید اگر ایمپورت شده باشد

async def handle_reset_all_points_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید ریست امتیازها", callback_data="admin:reset_all_points_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ تمام امتیازات کاربران صفر خواهد شد!", reply_markup=kb)

async def handle_reset_all_points_execute(call, params):
    count = await db.reset_all_achievement_points()
    await bot.answer_callback_query(call.id, f"✅ امتیاز {count} کاربر صفر شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ عملیات موفق.", reply_markup=await admin_menu.system_tools_menu())

async def handle_delete_all_devices_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید حذف دستگاه‌ها", callback_data="admin:delete_all_devices_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ لیست دستگاه‌های متصل تمام کاربران پاک می‌شود.", reply_markup=kb)

async def handle_delete_all_devices_execute(call, params):
    count = await db.delete_all_user_agents()
    await bot.answer_callback_query(call.id, f"✅ {count} دستگاه حذف شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ عملیات موفق.", reply_markup=await admin_menu.system_tools_menu())

async def handle_reset_all_balances_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید صفر کردن موجودی‌ها", callback_data="admin:reset_all_balances_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ موجودی کیف پول همه کاربران صفر و تاریخچه پاک می‌شود!", reply_markup=kb)

async def handle_reset_all_balances_execute(call, params):
    count = await db.reset_all_wallet_balances()
    await bot.answer_callback_query(call.id, "✅ انجام شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, f"✅ موجودی {count} کاربر صفر شد.", reply_markup=await admin_menu.system_tools_menu())