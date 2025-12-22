import logging
import time
from telebot import types
from sqlalchemy import select, update
from bot.database import db
from bot.db.base import Plan, ServerCategory
from bot.keyboards import admin as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.parsers import extract_country_code_from_flag

logger = logging.getLogger(__name__)
bot, admin_conversations = None, None

def initialize_plan_management_handlers(b, conv_dict):
    """مقادیر bot و admin_conversations را از فایل اصلی دریافت می‌کند."""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    """پیام کاربر را برای تمیز ماندن چت حذف می‌کند."""
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass

async def handle_plan_management_menu(call, params):
    """منوی اصلی مدیریت پلن‌های فروش"""
    uid, msg_id = call.from_user.id, call.message.message_id
    categories = await db.get_server_categories()
    
    prompt = (
        f"🗂️ *{escape_markdown('مدیریت پلن‌های فروش')}*\n\n"
        f"{escape_markdown('لطفاً لوکیشن (کشور) مورد نظر را انتخاب کنید تا پلن‌های مربوط به آن نمایش داده شود:')}"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    for cat in categories:
        buttons.append(
            types.InlineKeyboardButton(f"{cat['emoji']} {cat['name']}", callback_data=f"admin:plan_show_category:{cat['code']}")
        )
    
    if buttons:
        kb.add(*buttons)
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin:panel"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_show_plans_by_category(call, params):
    """نمایش لیست پلن‌های یک کشور خاص"""
    target_code = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    all_cats = await db.get_server_categories()
    cat_name = target_code
    cat_emoji = ""
    for c in all_cats:
        if c['code'] == target_code:
            cat_name = c['name']
            cat_emoji = c['emoji']
            break
            
    async with db.get_session() as session:
        result = await session.execute(select(Plan).order_by(Plan.price))
        all_plans = result.scalars().all()

    filtered_plans = []
    for plan in all_plans:
        cats = plan.allowed_categories or []
        if target_code in cats:
            filtered_plans.append(plan)

    prompt = f"📂 *پلن‌های کشور {cat_emoji} {escape_markdown(cat_name)}*"
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    plan_buttons = [types.InlineKeyboardButton(f"🔸 {p.name}", callback_data=f"admin:plan_details:{p.id}") for p in filtered_plans]
    if plan_buttons:
        kb.add(*plan_buttons)
            
    kb.row(
        types.InlineKeyboardButton(f"➕ افزودن پلن", callback_data=f"admin:plan_add_start:{target_code}"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:plan_manage")
    )
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_plan_details_menu(call, params):
    """نمایش جزئیات پلن."""
    plan_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        plan = await session.get(Plan, plan_id)
    
    if not plan:
        await bot.answer_callback_query(call.id, "❌ پلن یافت نشد.", show_alert=True)
        return

    cats = plan.allowed_categories or []
    is_combined = len(cats) > 1 or not cats
    plan_type_str = "ترکیبی 🚀" if is_combined else f"اختصاصی ({cats[0] if cats else '?'})"
    
    details = [
        f"🔸 *نام:* {escape_markdown(plan.name)}",
        f"🔹 *نوع:* {escape_markdown(plan_type_str)}",
        f"📦 *حجم:* `{plan.volume_gb}` گیگابایت",
        f"📅 *مدت:* `{plan.days}` روز",
        f"💰 *قیمت:* `{plan.price:,}` تومان"
    ]
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin:plan_delete_confirm:{plan_id}"),
        types.InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin:plan_edit_start:{plan_id}")
    )
    return_cat = "combined" if is_combined else "germany" 
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:plan_show_category:{return_cat}"))
    
    await _safe_edit(uid, msg_id, "\n".join(details), reply_markup=kb, parse_mode="MarkdownV2")

async def handle_delete_plan_confirm(call, params):
    """تاییدیه حذف."""
    plan_id = int(params[0])
    async with db.get_session() as session:
        plan = await session.get(Plan, plan_id)
        
    if not plan: return
    
    prompt = f"⚠️ *آیا «{escape_markdown(plan.name)}» حذف شود؟*"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:plan_delete_execute:{plan_id}"),
        types.InlineKeyboardButton("✅ خیر", callback_data=f"admin:plan_details:{plan_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_delete_plan_execute(call, params):
    """اجرای حذف."""
    plan_id = int(params[0])
    async with db.get_session() as session:
        plan = await session.get(Plan, plan_id)
        if plan:
            await session.delete(plan)
            await session.commit()
            await bot.answer_callback_query(call.id, "✅ حذف شد.")
            await handle_plan_management_menu(call, [])
        else:
            await bot.answer_callback_query(call.id, "❌ خطا: پلن یافت نشد.")

# --- Add Plan Flow ---

async def handle_plan_add_start(call, params):
    """شروع افزودن پلن"""
    uid, msg_id = call.from_user.id, call.message.message_id
    pre_selected_cat = params[0] if params else None
    
    admin_conversations[uid] = {
        'step': 'plan_add_name', 
        'msg_id': msg_id, 
        'new_plan_data': {}
    }
    
    if pre_selected_cat:
        admin_conversations[uid]['new_plan_data']['allowed_categories'] = [pre_selected_cat]
        # تنظیم هندلر مرحله بعد
        admin_conversations[uid]['next_handler'] = get_plan_add_name
        
        back_btn = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✖️ لغو", callback_data=f"admin:plan_show_category:{pre_selected_cat}")
        )
        
        await _safe_edit(uid, msg_id, "2️⃣ *نام پلن* را وارد کنید:", reply_markup=back_btn)
        
    else:
        # اگر کتگوری انتخاب نشده، فقط پیام را ادیت میکنیم (کالبک دکمه‌ها هندل می‌شود)
        admin_conversations[uid]['step'] = 'plan_add_type'
        kb = types.InlineKeyboardMarkup(row_width=2)
        # فرض بر این است که دکمه‌های اینلاین در تابع get_plan_add_type پردازش می‌شوند
        # اما چون اینجا فقط نمایش منو است، نیازی به next_handler نیست
        await _safe_edit(uid, msg_id, "1️⃣ *نوع پلن* را انتخاب کنید:", reply_markup=kb)

async def get_plan_add_type(call, params):
    uid = call.from_user.id
    if uid not in admin_conversations: return
    
    plan_type = params[0]
    allowed_cats = []
    
    if plan_type == 'combined':
        async with db.get_session() as session:
            result = await session.execute(select(ServerCategory))
            allowed_cats = [c.code for c in result.scalars().all()]
            if not allowed_cats: allowed_cats = ['de', 'fr', 'tr', 'us']
    else:
        mapping = {'germany': ['de'], 'france': ['fr'], 'turkey': ['tr']}
        allowed_cats = mapping.get(plan_type, [])

    admin_conversations[uid]['new_plan_data']['allowed_categories'] = allowed_cats
    admin_conversations[uid]['step'] = 'plan_add_name'
    
    # تنظیم هندلر مرحله بعد
    admin_conversations[uid]['next_handler'] = get_plan_add_name
    
    await _safe_edit(uid, call.message.message_id, "2️⃣ *نام پلن* را وارد کنید:", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_add_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    admin_conversations[uid]['new_plan_data']['name'] = message.text.strip()
    admin_conversations[uid]['step'] = 'plan_add_volume'
    
    # تنظیم هندلر مرحله بعد
    admin_conversations[uid]['next_handler'] = get_plan_add_volume
    
    # اصلاح متن برای جلوگیری از خطای پرانتز
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "3️⃣ *حجم \(GB\)* را وارد کنید \(فقط عدد\):", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_add_volume(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        vol = float(message.text.strip())
        admin_conversations[uid]['new_plan_data']['volume_gb'] = vol
        admin_conversations[uid]['step'] = 'plan_add_days'
        
        # تنظیم هندلر مرحله بعد
        admin_conversations[uid]['next_handler'] = get_plan_add_days
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "4️⃣ *مدت زمان \(روز\)* را وارد کنید:", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))
    except ValueError:
        await bot.send_message(uid, "❌ لطفاً عدد معتبر وارد کنید.")

async def get_plan_add_days(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        days = int(message.text.strip())
        admin_conversations[uid]['new_plan_data']['days'] = days
        admin_conversations[uid]['step'] = 'plan_add_price'
        
        # تنظیم هندلر مرحله بعد
        admin_conversations[uid]['next_handler'] = get_plan_save
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "5️⃣ *قیمت \(تومان\)* را وارد کنید:", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))
    except ValueError:
        await bot.send_message(uid, "❌ عدد صحیح وارد کنید.")

async def get_plan_save(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    data = admin_conversations.pop(uid)
    plan_data = data['new_plan_data']
    msg_id = data['msg_id']
    
    try:
        price = float(message.text.strip())
        async with db.get_session() as session:
            new_plan = Plan(
                name=plan_data['name'],
                volume_gb=plan_data['volume_gb'],
                days=plan_data['days'],
                price=price,
                allowed_categories=plan_data['allowed_categories'],
                is_active=True
            )
            session.add(new_plan)
            await session.commit()
            
        await _safe_edit(uid, msg_id, "✅ پلن جدید ساخته شد.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:plan_manage")))
    except Exception as e:
        logger.error(f"Error saving plan: {e}")
        await _safe_edit(uid, msg_id, "❌ خطای سیستمی در ذخیره.", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))

# --- Edit Plan Flow (Complete) ---

async def handle_plan_edit_start(call, params):
    """شروع ویرایش."""
    plan_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        plan = await session.get(Plan, plan_id)
        if not plan: return
        
        admin_conversations[uid] = {
            'step': 'edit_name',
            'msg_id': msg_id,
            'plan_id': plan_id,
            'edit_data': {}
        }
        
        prompt = f"نام فعلی: {plan.name}\n👇 *نام جدید* را وارد کنید (یا . بفرستید تا تغییر نکند):"
        await _safe_edit(uid, msg_id, prompt, reply_markup=admin_menu.admin_cancel_action(f"admin:plan_details:{plan_id}"))
        bot.register_next_step_handler(call.message, get_plan_edit_name)

async def get_plan_edit_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    txt = message.text.strip()
    if txt != '.':
        admin_conversations[uid]['edit_data']['name'] = txt
        
    admin_conversations[uid]['step'] = 'edit_volume'
    admin_conversations[uid]['next_handler'] = get_plan_edit_volume
    
    msg_text = "👇 *حجم جدید \(GB\)* \(یا \. برای عدم تغییر\):"
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_edit_volume(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    txt = message.text.strip()
    if txt != '.':
        try:
            admin_conversations[uid]['edit_data']['volume_gb'] = float(txt)
        except:
            await bot.send_message(uid, "❌ عدد نامعتبر.")
            return

    admin_conversations[uid]['step'] = 'edit_days'
    # ✅ تنظیم هندلر بعدی
    admin_conversations[uid]['next_handler'] = get_plan_edit_days
    
    msg_text = "👇 *مدت زمان جدید \(روز\)* \(یا \. برای عدم تغییر\):"
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_edit_days(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    txt = message.text.strip()
    if txt != '.':
        try:
            admin_conversations[uid]['edit_data']['days'] = int(txt)
        except:
            await bot.send_message(uid, "❌ عدد صحیح وارد کنید.")
            return

    admin_conversations[uid]['step'] = 'edit_price'
    admin_conversations[uid]['next_handler'] = get_plan_edit_finish
    
    msg_text = "👇 *قیمت جدید \(تومان\)* \(یا \. برای عدم تغییر\):"
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_edit_days(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    txt = message.text.strip()
    if txt != '.':
        try:
            admin_conversations[uid]['edit_data']['days'] = int(txt)
        except:
            await bot.send_message(uid, "❌ عدد صحیح وارد کنید.")
            return

    admin_conversations[uid]['step'] = 'edit_price'
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "👇 *قیمت جدید (تومان)* (یا . برای عدم تغییر):", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
    bot.register_next_step_handler(message, get_plan_edit_finish)

async def get_plan_edit_finish(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    data = admin_conversations.pop(uid)
    changes = data['edit_data']
    plan_id = data['plan_id']
    msg_id = data['msg_id']
    
    txt = message.text.strip()
    if txt != '.':
        try:
            changes['price'] = float(txt)
        except:
            await bot.send_message(uid, "❌ قیمت نامعتبر.")
            return

    if not changes:
        await _safe_edit(uid, msg_id, "⚠️ هیچ تغییری اعمال نشد.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:plan_details:{plan_id}")))
        return

    async with db.get_session() as session:
        stmt = update(Plan).where(Plan.id == plan_id).values(**changes)
        await session.execute(stmt)
        await session.commit()
    
    await _safe_edit(uid, msg_id, "✅ پلن با موفقیت ویرایش شد.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:plan_details:{plan_id}")))


# ==========================================
# مدیریت دسته‌بندی‌ها (کشورها)
# ==========================================

async def handle_category_management_menu(call, params):
    """منوی لیست کشورها (دو ستونه)"""
    categories = await db.get_server_categories()
    
    text = "🌍 **مدیریت کشورها (لوکیشن‌ها)**\n\nبرای ویرایش یا حذف، روی نام کشور کلیک کنید:"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    for cat in categories:
        btn_text = f"{cat['emoji']} {cat['name']}"
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:cat_detail:{cat['code']}"))
    
    if buttons:
        kb.add(*buttons)
        
    kb.row(
        types.InlineKeyboardButton("➕ افزودن کشور", callback_data="admin:cat_add_start"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel_manage")
    )
    
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="Markdown")

async def handle_category_details(call, params):
    """منوی جزئیات کشور (ویرایش/حذف)"""
    code = params[0]
    
    # پیدا کردن اطلاعات کشور
    categories = await db.get_server_categories()
    cat = next((c for c in categories if c['code'] == code), None)
    
    if not cat:
        await bot.answer_callback_query(call.id, "❌ کشور یافت نشد.")
        return

    text = (
        f"🌍 **مدیریت لوکیشن: {cat['name']}**\n\n"
        f"📌 کد: `{cat['code']}`\n"
        f"🏳️ پرچم: {cat['emoji']}\n\n"
        f"لطفاً عملیات مورد نظر را انتخاب کنید:"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✏️ تغییر نام", callback_data=f"admin:cat_edit:{code}"),
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin:cat_delete:{code}")
    )
    kb.row(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:cat_manage"))
    
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode="Markdown")

async def handle_category_edit_start(call, params):
    """شروع تغییر نام کشور"""
    code = params[0]
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    # پیدا کردن نام فعلی
    categories = await db.get_server_categories()
    cat = next((c for c in categories if c['code'] == code), None)
    current_name = cat['name'] if cat else code

    admin_conversations[uid] = {
        'step': 'edit_cat_name',
        'msg_id': msg_id,
        'cat_code': code,
        'timestamp': time.time(),
        'next_handler': process_category_new_name
    }
    
    prompt = (
        f"✏️ **تغییر نام {current_name}**\n\n"
        f"لطفاً نام جدید را وارد کنید:"
    )
    
    # دکمه انصراف برمی‌گردد به منوی جزئیات همان کشور
    back_kb = await admin_menu.cancel_action(f"admin:cat_detail:{code}")
    await _safe_edit(uid, msg_id, prompt, reply_markup=back_kb, parse_mode="Markdown")

async def process_category_new_name(message: types.Message):
    """ذخیره نام جدید کشور"""
    uid, new_name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    code = data['cat_code']
    msg_id = data['msg_id']
    
    if await db.update_server_category_name(code, new_name):
        success_msg = f"✅ نام کشور با موفقیت به **{new_name}** تغییر کرد."
        
        # دکمه بازگشت به جزئیات
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:cat_detail:{code}"))
        
        await _safe_edit(uid, msg_id, success_msg, reply_markup=kb, parse_mode="Markdown")
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در ویرایش نام.", reply_markup=await admin_menu.cancel_action("admin:cat_manage"))

async def handle_category_delete(call, params):
    """مرحله اول: نمایش تاییدیه حذف کشور"""
    code = params[0]
        
    prompt = f"⚠️ *آیا مطمئن هستید که می‌خواهید کشور `{code}` را حذف کنید؟*\nبا این کار تمام پنل‌های متصل به این دسته بی‌نظم می‌شوند\."
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:cat_del_exec:{code}"),
        types.InlineKeyboardButton("✅ انصراف", callback_data=f"admin:cat_detail:{code}")
    )
    
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_category_delete_execute(call, params):
    """مرحله دوم: اجرای حذف"""
    code = params[0]
    await db.delete_server_category(code)
    await bot.answer_callback_query(call.id, "✅ کشور با موفقیت حذف شد.")
    await handle_category_management_menu(call, [])

# --- پروسه افزودن کشور ---
# ==========================================
# 1. بخش مدیریت دسته‌بندی‌ها (کشورها)
# ==========================================

async def handle_category_add_start(call, params):
    """شروع پروسه افزودن کشور"""
    uid = call.from_user.id
    
    admin_conversations[uid] = {
        'step': 'cat_code', 
        'msg_id': call.message.message_id, 
        'cat_data': {},
        'timestamp': time.time(),
        'next_handler': get_cat_code 
    }
    
    back_kb = await admin_menu.cancel_action("admin:cat_manage")
    
    # تغییر متن پیام برای راهنمایی کاربر
    msg_text = (
        "1️⃣ لطفاً *کد کوتاه* کشور را بفرستید \(مثلاً `nl`\)\.\n\n"
        "💡 *نکته هوشمند:* می‌توانید همین الان *ایموجی پرچم* \(مثلاً 🇳🇱\) را بفرستید تا کد و پرچم به صورت خودکار ثبت شوند\!"
    )
    
    await _safe_edit(uid, call.message.message_id, msg_text, reply_markup=back_kb)

async def get_cat_code(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    raw_text = message.text.strip()
    
    # استفاده از تابع هوشمند برای استخراج کد
    code = extract_country_code_from_flag(raw_text)
    
    # اعتبارسنجی طول کد
    if len(code) > 10: # کدهای کشور معمولا ۲ یا ۳ حرفی هستند
        await bot.send_message(uid, "❌ کد وارد شده نامعتبر یا خیلی طولانی است. لطفاً مجدد تلاش کنید.")
        return

    admin_conversations[uid]['cat_data']['code'] = code
    
    # --- قابلیت هوشمند: تشخیص پرچم ---
    # اگر ورودی کاربر واقعاً یک پرچم بود، آن را ذخیره می‌کنیم تا بعداً نپرسیم
    is_flag = len(raw_text) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in raw_text)
    if is_flag:
        admin_conversations[uid]['cat_data']['emoji'] = raw_text
        admin_conversations[uid]['has_flag'] = True # فلگ برای اسکیپ مرحله بعد
    else:
        admin_conversations[uid]['has_flag'] = False

    # رفتن به مرحله بعد (نام کشور)
    admin_conversations[uid]['step'] = 'cat_name'
    admin_conversations[uid]['next_handler'] = get_cat_name
    
    back_kb = await admin_menu.cancel_action("admin:cat_manage")
    
    msg_text = f"2️⃣ کد `{code}` ثبت شد\. حالا *نام فارسی* کشور را بفرستید \(مثلا `هلند`\):"
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=back_kb)

async def get_cat_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    name = message.text.strip()
    admin_conversations[uid]['cat_data']['name'] = name
    
    if admin_conversations[uid].get('has_flag'):
        admin_conversations[uid]['step'] = 'cat_desc'
        admin_conversations[uid]['next_handler'] = get_cat_description
        
        back_kb = await admin_menu.cancel_action("admin:cat_manage")
        
        saved_flag = admin_conversations[uid]['cat_data']['emoji']
        msg_text = (
            f"3️⃣ پرچم {saved_flag} قبلاً دریافت شد\.\n\n"
            "4️⃣ *توضیحات اختیاری* را بفرستید \(یا نقطه `.` برای رد کردن\):"
        )
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=back_kb)
        
    else:
        admin_conversations[uid]['step'] = 'cat_emoji'
        admin_conversations[uid]['next_handler'] = get_cat_emoji
        
        back_kb = await admin_menu.cancel_action("admin:cat_manage")
        msg_text = "3️⃣ حالا یک *ایموجی پرچم* بفرستید \(مثلا 🇳🇱\):"
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=back_kb)

# ==========================================
# 2. بخش افزودن پلن (Add Plan)
# ==========================================

async def handle_plan_add_start(call, params):
    """شروع افزودن پلن"""
    uid, msg_id = call.from_user.id, call.message.message_id
    pre_selected_cat = params[0] if params else None
    
    admin_conversations[uid] = {
        'step': 'plan_add_name', 
        'msg_id': msg_id, 
        'new_plan_data': {},
        'timestamp': time.time()  # ✅ افزودن timestamp
    }
    
    if pre_selected_cat:
        admin_conversations[uid]['new_plan_data']['allowed_categories'] = [pre_selected_cat]
        # ✅ تنظیم هندلر بعدی
        admin_conversations[uid]['next_handler'] = get_plan_add_name
        
        back_btn = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✖️ لغو", callback_data=f"admin:plan_show_category:{pre_selected_cat}")
        )
        
        await _safe_edit(uid, msg_id, "2️⃣ *نام پلن* را وارد کنید:", reply_markup=back_btn)
        
    else:
        admin_conversations[uid]['step'] = 'plan_add_type'
        # در اینجا چون دکمه اینلاین است، هندلر بعدی روی دکمه ست شده (plan_add_type) و نیاز به next_handler متنی نیست
        kb = types.InlineKeyboardMarkup(row_width=2)
        # دکمه‌ها را باید اینجا اضافه کنید یا اگر از قبل وجود دارند استفاده کنید. 
        # (فرض بر این است که این بخش فقط نمایش منو است و کالبک دکمه‌ها جداگانه هندل می‌شود)
        # برای جلوگیری از گیر کردن، اگر دکمه‌ها را ندارید باید اضافه کنید، اما طبق کد قبلی شما، اینجا فقط پیام ادیت می‌شود.
        await _safe_edit(uid, msg_id, "1️⃣ *نوع پلن* را انتخاب کنید:", reply_markup=kb)

async def get_plan_add_type(call, params):
    uid = call.from_user.id
    if uid not in admin_conversations: return
    
    plan_type = params[0]
    allowed_cats = []
    
    if plan_type == 'combined':
        async with db.get_session() as session:
            result = await session.execute(select(ServerCategory))
            allowed_cats = [c.code for c in result.scalars().all()]
            if not allowed_cats: allowed_cats = ['de', 'fr', 'tr', 'us']
    else:
        mapping = {'germany': ['de'], 'france': ['fr'], 'turkey': ['tr']}
        allowed_cats = mapping.get(plan_type, [])

    admin_conversations[uid]['new_plan_data']['allowed_categories'] = allowed_cats
    admin_conversations[uid]['step'] = 'plan_add_name'
    
    # ✅ تنظیم هندلر بعدی
    admin_conversations[uid]['next_handler'] = get_plan_add_name
    
    await _safe_edit(uid, call.message.message_id, "2️⃣ *نام پلن* را وارد کنید:", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_add_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    admin_conversations[uid]['new_plan_data']['name'] = message.text.strip()
    admin_conversations[uid]['step'] = 'plan_add_volume'
    
    # ✅ تنظیم هندلر بعدی
    admin_conversations[uid]['next_handler'] = get_plan_add_volume
    
    msg_text = "3️⃣ *حجم \(GB\)* را وارد کنید \(فقط عدد\):"
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

async def get_plan_add_volume(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        vol = float(message.text.strip())
        admin_conversations[uid]['new_plan_data']['volume_gb'] = vol
        admin_conversations[uid]['step'] = 'plan_add_days'
        
        # ✅ تنظیم هندلر بعدی
        admin_conversations[uid]['next_handler'] = get_plan_add_days
        
        msg_text = "4️⃣ *مدت زمان \(روز\)* را وارد کنید:"
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))
    except ValueError:
        await bot.send_message(uid, "❌ لطفاً عدد معتبر وارد کنید.")

async def get_plan_add_days(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        days = int(message.text.strip())
        admin_conversations[uid]['new_plan_data']['days'] = days
        admin_conversations[uid]['step'] = 'plan_add_price'
        
        # ✅ تنظیم هندلر بعدی
        admin_conversations[uid]['next_handler'] = get_plan_save
        
        msg_text = "5️⃣ *قیمت \(تومان\)* را وارد کنید:"
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:plan_manage"))
    except ValueError:
        await bot.send_message(uid, "❌ عدد صحیح وارد کنید.")

# ==========================================
# 3. بخش ویرایش پلن (Edit Plan)
# ==========================================

async def handle_plan_edit_start(call, params):
    """شروع ویرایش"""
    plan_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    async with db.get_session() as session:
        plan = await session.get(Plan, plan_id)
        if not plan: return
        
        safe_name = escape_markdown(plan.name)
        admin_conversations[uid] = {
            'step': 'edit_name',
            'msg_id': msg_id,
            'plan_id': plan_id,
            'edit_data': {},
            'timestamp': time.time(),  # ✅ افزودن timestamp
            'next_handler': get_plan_edit_name # ✅ تنظیم هندلر
        }
        
        prompt = f"نام فعلی: {safe_name}\n👇 *نام جدید* را وارد کنید \(یا \. بفرستید تا تغییر نکند\):"
        await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action(f"admin:plan_details:{plan_id}"))

async def get_cat_emoji(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    emoji = message.text.strip()
    admin_conversations[uid]['cat_data']['emoji'] = emoji
    
    # تنظیم مرحله بعدی: دریافت توضیحات
    admin_conversations[uid]['step'] = 'cat_desc'
    admin_conversations[uid]['next_handler'] = get_cat_description
    
    back_kb = await admin_menu.cancel_action("admin:cat_manage")
    
    msg_text = "4️⃣ \(اختیاری\) اگر توضیحی برای این کشور دارید بنویسید \(مثلا: *مخصوص همراه اول*\)\n\nاگر توضیحی ندارید نقطه `.` بفرستید:"
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], msg_text, reply_markup=back_kb)

async def get_cat_description(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    text = message.text.strip()
    description = None if text == '.' else text
    
    # دریافت داده‌ها و پایان مکالمه
    data = admin_conversations.pop(uid)
    cat = data['cat_data']
    msg_id = data['msg_id']
    
    # ذخیره در دیتابیس
    await db.add_server_category(cat['code'], cat['name'], cat['emoji'], description)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:cat_manage"))

    # ✅ اصلاح متن: نقطه پایان جمله اسکیپ شد
    await _safe_edit(uid, msg_id, "✅ کشور جدید با موفقیت اضافه شد\.", reply_markup=kb)

async def get_plan_save(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    data = admin_conversations.pop(uid)
    plan_data = data['new_plan_data']
    msg_id = data['msg_id']
    
    try:
        price = float(message.text.strip())
        async with db.get_session() as session:
            new_plan = Plan(
                name=plan_data['name'],
                volume_gb=plan_data['volume_gb'],
                days=plan_data['days'],
                price=price,
                allowed_categories=plan_data['allowed_categories'],
                is_active=True
            )
            session.add(new_plan)
            await session.commit()
            
        await _safe_edit(uid, msg_id, "✅ پلن جدید ساخته شد\.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:plan_manage")))
    except Exception as e:
        logger.error(f"Error saving plan: {e}")
        await _safe_edit(uid, msg_id, "❌ خطای سیستمی در ذخیره\.", reply_markup=await admin_menu.cancel_action("admin:plan_manage"))

