import logging
import asyncio
from telebot import types
from sqlalchemy import select, or_, cast, String, func
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, Panel, WalletTransaction
from bot.services.panels import PanelFactory
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# استیت برای مکالمات ادمین (جستجو، ادیت و ...)
admin_conversations = {}

def initialize_user_management_handlers(b, conv_dict):
    """دریافت مقادیر از فایل اصلی"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

# --- منوی اصلی مدیریت کاربران ---

async def handle_user_management_menu(call, params):
    """نمایش منوی مدیریت کاربران"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # دریافت آمار سریع
    async with db.get_session() as session:
        total_users = await session.scalar(select(func.count(User.user_id)))
    
    text = (
        f"👥 *مدیریت کاربران*\n\n"
        f"تعداد کل کاربران: `{total_users}`\n\n"
        "برای مدیریت، می‌توانید لیست را ببینید یا کاربری را جستجو کنید."
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin:user_search_start"),
        types.InlineKeyboardButton("📜 لیست کاربران (صفحه ۱)", callback_data="admin:user_list:1")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- لیست کاربران (Pagination) ---

async def handle_user_list(call, params):
    """نمایش لیست کاربران با صفحه‌بندی"""
    page = int(params[0])
    per_page = 10
    offset = (page - 1) * per_page
    
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        # دریافت کاربران با مرتب‌سازی بر اساس تاریخ عضویت (یا ID)
        stmt = select(User).order_by(User.user_id.desc()).limit(per_page).offset(offset)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        # شمارش کل برای دکمه‌های بعدی/قبلی
        total_count = await session.scalar(select(func.count(User.user_id)))

    if not users:
        await bot.answer_callback_query(call.id, "❌ کاربری یافت نشد.")
        return

    text = f"📜 *لیست کاربران - صفحه {page}*\n\n"
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    for u in users:
        display_name = u.first_name or u.username or f"User {u.user_id}"
        kb.add(types.InlineKeyboardButton(f"👤 {display_name}", callback_data=f"admin:user_details:{u.user_id}"))

    # دکمه‌های نویگیشن
    nav_btns = []
    if page > 1:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin:user_list:{page-1}"))
    if offset + per_page < total_count:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin:user_list:{page+1}"))
    
    if nav_btns:
        kb.add(*nav_btns)
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:user_manage"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- جستجوی کاربر ---

async def handle_user_search_start(call, params):
    """شروع فرآیند جستجو"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'search_query',
        'msg_id': msg_id
    }
    
    text = "🔍 لطفاً **نام کاربری**، **آیدی عددی** یا بخشی از **UUID** کاربر را ارسال کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=admin_menu.cancel_action("admin:user_manage"))
    bot.register_next_step_handler(call.message, process_user_search)

async def process_user_search(message: types.Message):
    """پردازش متن جستجو"""
    uid, query = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    msg_id = admin_conversations.pop(uid)['msg_id']
    
    async with db.get_session() as session:
        # جستجوی ترکیبی: 
        # 1. تطابق با username
        # 2. تطابق با user_id
        # 3. تطابق با یکی از uuid های کاربر (نیاز به join)
        
        stmt = select(User).distinct().outerjoin(UserUUID).where(
            or_(
                User.username.ilike(f"%{query}%"),
                cast(User.user_id, String) == query,
                UserUUID.uuid.ilike(f"%{query}%"),
                UserUUID.name.ilike(f"%{query}%")
            )
        ).limit(20) # محدود کردن نتایج
        
        result = await session.execute(stmt)
        users = result.scalars().all()

    if not users:
        await _safe_edit(uid, msg_id, f"❌ کاربری با جستجوی «{query}» یافت نشد.", reply_markup=admin_menu.cancel_action("admin:user_manage"))
        return
    
    if len(users) == 1:
        # اگر فقط یک نفر پیدا شد، مستقیم برو به جزئیاتش
        await show_user_details(uid, msg_id, users[0].user_id)
    else:
        # نمایش لیست نتایج
        text = f"🔍 *نتایج جستجو برای:* `{query}`"
        kb = types.InlineKeyboardMarkup(row_width=1)
        for u in users:
            display = f"{u.first_name or ''} (@{u.username or 'NoUser'})"
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:user_details:{u.user_id}"))
        
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:user_manage"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- جزئیات کاربر ---

async def handle_user_details(call, params):
    uid, msg_id = call.from_user.id, call.message.message_id
    target_user_id = int(params[0])
    await show_user_details(uid, msg_id, target_user_id)

async def show_user_details(admin_id, msg_id, target_user_id):
    """نمایش پنل مدیریت تکی کاربر"""
    async with db.get_session() as session:
        # لود کردن کاربر همراه با UUID ها و تراکنش‌ها
        stmt = select(User).where(User.user_id == target_user_id).options(selectinload(User.uuids))
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
    
    if not user:
        await bot.edit_message_text("❌ کاربر یافت نشد.", admin_id, msg_id)
        return

    # آمار سرویس‌ها
    active_services = [u for u in user.uuids if u.is_active]
    total_services = len(user.uuids)
    
    text = (
        f"👤 *مشخصات کاربر*\n"
        f"🆔 ID: `{user.user_id}`\n"
        f"📛 Name: {escape_markdown(user.first_name or 'Unknown')}\n"
        f"🔗 Username: @{escape_markdown(user.username or 'None')}\n"
        f"💰 Wallet: `{int(user.wallet_balance):,}` تومان\n"
        f"🎫 Services: {len(active_services)} فعال / {total_services} کل\n\n"
        "از دکمه‌های زیر برای مدیریت استفاده کنید:"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # دکمه‌های اصلی
    kb.add(
        types.InlineKeyboardButton("➕ شارژ کیف پول", callback_data=f"admin:user_wallet_add:{user.user_id}"),
        types.InlineKeyboardButton("➖ کسر کیف پول", callback_data=f"admin:user_wallet_deduct:{user.user_id}")
    )
    kb.add(
        types.InlineKeyboardButton("📦 مدیریت سرویس‌ها", callback_data=f"admin:user_services:{user.user_id}"),
        types.InlineKeyboardButton("📩 ارسال پیام", callback_data=f"admin:user_send_msg:{user.user_id}")
    )
    # دکمه‌های خطرناک
    kb.add(
        types.InlineKeyboardButton("🚫 بن/آنبن", callback_data=f"admin:user_ban_toggle:{user.user_id}"),
        types.InlineKeyboardButton("🗑 حذف کاربر", callback_data=f"admin:user_delete_confirm:{user.user_id}")
    )
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:user_manage"))
    
    await _safe_edit(admin_id, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- مدیریت سرویس‌های کاربر ---

async def handle_user_services_list(call, params):
    """لیست سرویس‌های (UUID) یک کاربر برای مدیریت جداگانه"""
    target_user_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        # لود کردن UUID ها همراه با نام پنل‌ها
        stmt = select(UserUUID).where(UserUUID.user_id == target_user_id).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        uuids = result.scalars().all()
    
    if not uuids:
        await bot.answer_callback_query(call.id, "❌ این کاربر هیچ سرویسی ندارد.")
        return

    text = f"📦 *مدیریت سرویس‌های کاربر {target_user_id}*\nیک سرویس را برای ویرایش (افزودن حجم/زمان) انتخاب کنید:"
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    for u in uuids:
        status = "✅" if u.is_active else "❌"
        # نمایش نام سرویس یا بخشی از UUID
        display = f"{status} {u.name or u.uuid[:8]}..."
        kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:service_edit:{u.id}"))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پروفایل کاربر", callback_data=f"admin:user_details:{target_user_id}"))
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- ویرایش یک سرویس خاص (افزودن حجم/زمان) ---

async def handle_service_edit_menu(call, params):
    uuid_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    uuid_obj = await db.get_by_id(UserUUID, uuid_id)
    if not uuid_obj:
        await bot.answer_callback_query(call.id, "❌ سرویس یافت نشد.")
        return

    text = (
        f"⚙️ *ویرایش سرویس*\n"
        f"🔖 نام: {escape_markdown(uuid_obj.name or 'بی‌نام')}\n"
        f"🔑 UUID: `{uuid_obj.uuid}`\n\n"
        "چه تغییری می‌خواهید اعمال کنید؟"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ افزودن حجم (GB)", callback_data=f"admin:srv_add_gb:{uuid_id}"),
        types.InlineKeyboardButton("➕ افزودن زمان (روز)", callback_data=f"admin:srv_add_days:{uuid_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:user_services:{uuid_obj.user_id}"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_service_add_action(call, params):
    """شروع پروسه افزودن حجم یا زمان"""
    action = params[0] # srv_add_gb or srv_add_days
    uuid_id = int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'service_modify_value',
        'msg_id': msg_id,
        'uuid_id': uuid_id,
        'action': action
    }
    
    item_name = "حجم (گیگابایت)" if "gb" in action else "زمان (روز)"
    text = f"🔢 لطفاً مقدار {item_name} را که می‌خواهید **اضافه** کنید وارد نمایید (عدد):"
    
    await _safe_edit(uid, msg_id, text, reply_markup=admin_menu.cancel_action(f"admin:service_edit:{uuid_id}"))
    bot.register_next_step_handler(call.message, process_service_modification)

async def process_service_modification(message: types.Message):
    """اعمال تغییرات روی دیتابیس و پنل"""
    uid, value_str = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    msg_id = data['msg_id']
    uuid_id = data['uuid_id']
    action = data['action']
    
    try:
        value = float(value_str)
        if value <= 0: raise ValueError
    except:
        await bot.send_message(uid, "❌ مقدار نامعتبر است.")
        return

    await _safe_edit(uid, msg_id, "⏳ در حال اعمال تغییرات روی پنل‌ها...", reply_markup=None)

    async with db.get_session() as session:
        # دریافت سرویس و پنل‌های متصل
        stmt = select(UserUUID).where(UserUUID.id == uuid_id).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        uuid_obj = result.scalar_one_or_none()
        
        if not uuid_obj:
            await bot.send_message(uid, "❌ سرویس پیدا نشد.")
            return

        success_msg = []
        error_msg = []
        
        # 1. اعمال روی پنل‌ها (API Call)
        if uuid_obj.allowed_panels:
            for panel in uuid_obj.allowed_panels:
                try:
                    panel_api = await PanelFactory.get_panel(panel.name)
                    
                    # --- اصلاحیه: تشخیص شناسه صحیح (UUID برای هیدیفای، Username برای مرزبان) ---
                    identifier = uuid_obj.uuid
                    
                    if panel.panel_type == 'marzban':
                        # ایمپورت مدل در داخل تابع برای جلوگیری از مشکلات ایمپورت چرخشی
                        from bot.db.base import MarzbanMapping
                        
                        # تلاش برای یافتن نام کاربری مرزبان از جدول مپینگ
                        mapping = await session.get(MarzbanMapping, uuid_obj.uuid)
                        if mapping:
                            identifier = mapping.marzban_username
                        else:
                            # فال‌بک: اگر در مپینگ نبود، از نام کانفیگ استفاده کن (معمولاً یکی هستند)
                            identifier = uuid_obj.name

                    # ارسال درخواست به پنل با شناسه صحیح
                    if "gb" in action:
                        await panel_api.modify_user(identifier, add_gb=value)
                        success_msg.append(f"✅ پنل {panel.name}: حجم اضافه شد.")
                    else:
                        await panel_api.modify_user(identifier, add_days=int(value))
                        success_msg.append(f"✅ پنل {panel.name}: زمان اضافه شد.")
                        
                except Exception as e:
                    logger.error(f"Panel update failed for {panel.name}: {e}")
                    error_msg.append(f"❌ پنل {panel.name}: خطا")
        else:
            error_msg.append("⚠️ این سرویس به هیچ پنلی متصل نیست (فقط دیتابیس آپدیت می‌شود).")

        # 2. نمایش نتیجه نهایی
        final_text = "\n".join(success_msg + error_msg)
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:service_edit:{uuid_id}"))
        await _safe_edit(uid, msg_id, f"نتایج عملیات:\n\n{final_text}", reply_markup=kb)

    async with db.get_session() as session:
        # دریافت سرویس و پنل‌های متصل
        stmt = select(UserUUID).where(UserUUID.id == uuid_id).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        uuid_obj = result.scalar_one_or_none()
        
        if not uuid_obj:
            await bot.send_message(uid, "❌ سرویس پیدا نشد.")
            return

        success_msg = []
        error_msg = []
        
        # 1. اعمال روی پنل‌ها (API Call)
        if uuid_obj.allowed_panels:
            for panel in uuid_obj.allowed_panels:
                try:
                    panel_api = await PanelFactory.get_panel(panel.name)
                    if "gb" in action:
                        await panel_api.modify_user(uuid_obj.uuid, add_gb=value)
                        success_msg.append(f"✅ پنل {panel.name}: حجم اضافه شد.")
                    else:
                        await panel_api.modify_user(uuid_obj.uuid, add_days=int(value))
                        success_msg.append(f"✅ پنل {panel.name}: زمان اضافه شد.")
                except Exception as e:
                    logger.error(f"Panel update failed: {e}")
                    error_msg.append(f"❌ پنل {panel.name}: خطا")
        else:
            error_msg.append("⚠️ این سرویس به هیچ پنلی متصل نیست (فقط دیتابیس آپدیت می‌شود).")

        # 2. (اختیاری) ثبت در دیتابیس یا لاگ
        # در معماری شما UsageSnapshot مصرف را نگه می‌دارد، اما لیمیت‌ها معمولا در پنل هستند.
        # اگر در Plan یا UserUUID فیلد limit دارید، اینجا آپدیت کنید.

        final_text = "\n".join(success_msg + error_msg)
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:service_edit:{uuid_id}"))
        await _safe_edit(uid, msg_id, f"نتایج عملیات:\n\n{final_text}", reply_markup=kb)

# --- مدیریت کیف پول کاربر ---

async def handle_user_wallet_modify(call, params):
    """شروع شارژ/کسر کیف پول"""
    action = params[0] # user_wallet_add or user_wallet_deduct
    target_user_id = int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'wallet_modify',
        'msg_id': msg_id,
        'target_id': target_user_id,
        'action': action
    }
    
    op_name = "افزایش" if "add" in action else "کاهش"
    text = f"💰 لطفاً مبلغ مورد نظر برای **{op_name}** موجودی را به تومان وارد کنید:"
    
    await _safe_edit(uid, msg_id, text, reply_markup=admin_menu.cancel_action(f"admin:user_details:{target_user_id}"))
    bot.register_next_step_handler(call.message, process_wallet_modification)

async def process_wallet_modification(message: types.Message):
    uid, amount_str = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    try:
        amount = float(amount_str)
        target_id = data['target_id']
        is_add = "add" in data['action']
        
        # استفاده از متد update_wallet_balance که در wallet.py نوشتیم
        # اگر کسر است، مقدار منفی میفرستیم (ولی تایپ را دستی تنظیم میکنیم)
        final_amount = amount if is_add else -amount
        trans_type = 'admin_charge' if is_add else 'admin_deduct'
        desc = f"توسط ادمین {uid}"
        
        async with db.get_session() as session:
            # اینجا باید دستی هندل کنیم چون متد wallet.update_wallet_balance شاید session نپذیرد (بستگی به نسخه نهایی شما دارد)
            # اما چون در wallet.py اصلاح کردیم که session بگیرد:
            from bot.db.wallet import WalletDB # فرض بر این است که این متد در کلاس اصلی db موجود است
            # چون db نمونه DatabaseManager است که WalletDB را به ارث برده:
            
            success = await db.update_wallet_balance(
                target_id, final_amount, trans_type, desc, session=session
            )
            
            if success:
                new_bal = await session.scalar(select(User.wallet_balance).where(User.user_id == target_id))
                await session.commit()
                await _safe_edit(uid, data['msg_id'], f"✅ عملیات موفق.\nموجودی جدید: {int(new_bal):,} تومان", 
                                 reply_markup=menu.admin_back_btn(f"admin:user_details:{target_id}"))
            else:
                await _safe_edit(uid, data['msg_id'], "❌ موجودی کافی نیست یا خطا رخ داد.", 
                                 reply_markup=admin_menu.cancel_action(f"admin:user_details:{target_id}"))

    except ValueError:
        await bot.send_message(uid, "❌ مبلغ نامعتبر.")

# --- ارسال پیام به کاربر ---

async def handle_user_send_msg(call, params):
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {'step': 'send_dm', 'msg_id': msg_id, 'target_id': target_id}
    
    await _safe_edit(uid, msg_id, "✉️ پیام خود را بنویسید (متن، عکس، ...):", 
                     reply_markup=admin_menu.cancel_action(f"admin:user_details:{target_id}"))
    bot.register_next_step_handler(call.message, process_send_dm)

async def process_send_dm(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    target_id = data['target_id']
    
    try:
        await bot.copy_message(target_id, uid, message.message_id)
        await bot.send_message(target_id, "🔔 __پیام از طرف پشتیبانی__", parse_mode="MarkdownV2")
        
        await _safe_edit(uid, data['msg_id'], "✅ پیام ارسال شد.", 
                         reply_markup=menu.admin_back_btn(f"admin:user_details:{target_id}"))
    except Exception as e:
        await _safe_edit(uid, data['msg_id'], f"❌ خطا در ارسال: {e}", 
                         reply_markup=menu.admin_back_btn(f"admin:user_details:{target_id}"))

# --- حذف کاربر ---

async def handle_user_delete_confirm(call, params):
    target_id = int(params[0])
    text = f"⚠️ آیا مطمئن هستید که می‌خواهید کاربر `{target_id}` را حذف کنید؟\nتمام سوابق و سرویس‌ها پاک خواهند شد."
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف شود", callback_data=f"admin:user_delete_execute:{target_id}"),
        types.InlineKeyboardButton("انصراف", callback_data=f"admin:user_details:{target_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_user_delete_execute(call, params):
    target_id = int(params[0])
    
    if await db.delete_by_id(User, target_id):
        await bot.answer_callback_query(call.id, "✅ کاربر حذف شد.")
        await handle_user_management_menu(call, [])
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در حذف.")