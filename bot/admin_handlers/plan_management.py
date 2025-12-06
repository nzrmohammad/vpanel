import logging
from telebot import types
from sqlalchemy import select, update
from bot.database import db
from bot.db.base import Plan, ServerCategory
from bot.keyboards import admin as admin_menu
from bot.utils import _safe_edit, escape_markdown

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
    """منوی اصلی مدیریت پلن‌ها."""
    uid, msg_id = call.from_user.id, call.message.message_id
    prompt = f"🗂️ *{escape_markdown('مدیریت پلن‌های فروش')}*\n\n{escape_markdown('لطفاً دسته‌بندی مورد نظر را انتخاب کنید:')}"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🇺🇸 پلن‌های آمریکا", callback_data="admin:plan_show_category:usa"),
        types.InlineKeyboardButton("🇩🇪 پلن‌های آلمان", callback_data="admin:plan_show_category:germany")
    )
    kb.add(
        types.InlineKeyboardButton("🇫🇷 پلن‌های فرانسه", callback_data="admin:plan_show_category:france"),
        types.InlineKeyboardButton("🇹🇷 پلن‌های ترکیه", callback_data="admin:plan_show_category:turkey")
    )
    kb.add(
        types.InlineKeyboardButton("🚀 پلن‌های ترکیبی (همه)", callback_data="admin:plan_show_category:combined"),
        types.InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="admin:plan_add_start")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin:panel"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_show_plans_by_category(call, params):
    """نمایش لیست پلن‌ها بر اساس دسته‌بندی."""
    plan_category_filter = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # نگاشت‌ها
    type_map = {"combined": "ترکیبی", "germany": "آلمان", "france": "فرانسه", "turkey": "ترکیه", "usa": "آمریکا"}
    db_code_map = {"germany": "de", "france": "fr", "turkey": "tr", "usa": "us"}
    
    category_name = type_map.get(plan_category_filter, plan_category_filter)
    
    async with db.get_session() as session:
        result = await session.execute(select(Plan).order_by(Plan.price))
        all_plans = result.scalars().all()

    filtered_plans = []
    for plan in all_plans:
        cats = plan.allowed_categories or []
        if plan_category_filter == "combined":
            if len(cats) > 1 or not cats: # ترکیبی یا عمومی
                filtered_plans.append(plan)
        else:
            target_code = db_code_map.get(plan_category_filter)
            if target_code and target_code in cats and len(cats) == 1:
                filtered_plans.append(plan)

    prompt = f"🗂️ *{escape_markdown(f'لیست پلن‌های {category_name}')}*"
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [types.InlineKeyboardButton(f"🔸 {p.name}", callback_data=f"admin:plan_details:{p.id}") for p in filtered_plans]
    
    for i in range(0, len(buttons), 2):
        kb.add(*buttons[i:i+2])
            
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:plan_manage"))
    
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
    uid, msg_id = call.from_user.id, call.message.message_id
    admin_conversations[uid] = {'step': 'plan_add_type', 'msg_id': msg_id, 'new_plan_data': {}}
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("ترکیبی", callback_data="admin:plan_add_type:combined"),
        types.InlineKeyboardButton("آلمان", callback_data="admin:plan_add_type:germany"),
        types.InlineKeyboardButton("فرانسه", callback_data="admin:plan_add_type:france"),
        types.InlineKeyboardButton("ترکیه", callback_data="admin:plan_add_type:turkey")
    )
    kb.add(types.InlineKeyboardButton("🔙 لغو", callback_data="admin:plan_manage"))
    await _safe_edit(uid, msg_id, "1️⃣ *نوع پلن* را انتخاب کنید:", reply_markup=kb)

async def get_plan_add_type(call, params):
    uid = call.from_user.id
    if uid not in admin_conversations: return
    
    plan_type = params[0]
    allowed_cats = []
    
    # تعیین دسترسی‌ها بر اساس نوع
    if plan_type == 'combined':
        async with db.get_session() as session:
            result = await session.execute(select(ServerCategory))
            allowed_cats = [c.code for c in result.scalars().all()]
            # اگر دسته‌ای نبود، پیش‌فرض‌ها را بگذار
            if not allowed_cats: allowed_cats = ['de', 'fr', 'tr', 'us']
    else:
        mapping = {'germany': ['de'], 'france': ['fr'], 'turkey': ['tr']}
        allowed_cats = mapping.get(plan_type, [])

    admin_conversations[uid]['new_plan_data']['allowed_categories'] = allowed_cats
    admin_conversations[uid]['step'] = 'plan_add_name'
    
    await _safe_edit(uid, call.message.message_id, "2️⃣ *نام پلن* را وارد کنید:", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
    bot.register_next_step_handler(call.message, get_plan_add_name)

async def get_plan_add_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    admin_conversations[uid]['new_plan_data']['name'] = message.text.strip()
    admin_conversations[uid]['step'] = 'plan_add_volume'
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "3️⃣ *حجم (GB)* را وارد کنید (فقط عدد):", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
    bot.register_next_step_handler(message, get_plan_add_volume)

async def get_plan_add_volume(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        vol = float(message.text.strip())
        admin_conversations[uid]['new_plan_data']['volume_gb'] = vol
        admin_conversations[uid]['step'] = 'plan_add_days'
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "4️⃣ *مدت زمان (روز)* را وارد کنید:", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
        bot.register_next_step_handler(message, get_plan_add_days)
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
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], "5️⃣ *قیمت (تومان)* را وارد کنید:", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
        bot.register_next_step_handler(message, get_plan_save)
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
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "👇 *حجم جدید (GB)* (یا . برای عدم تغییر):", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
    bot.register_next_step_handler(message, get_plan_edit_volume)

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
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], "👇 *مدت زمان جدید (روز)* (یا . برای عدم تغییر):", reply_markup=admin_menu.admin_cancel_action("admin:plan_manage"))
    bot.register_next_step_handler(message, get_plan_edit_days)

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