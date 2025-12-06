# bot/admin_handlers/panel_management.py

import logging
from telebot import types
from bot.database import db
from bot.keyboards import admin as admin_menu
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)
bot = None
admin_conversations = {}

def initialize_panel_management_handlers(b, conv_dict):
    """مقادیر bot و admin_conversations را از فایل اصلی دریافت می‌کند."""
    global bot, admin_conversations
    bot = b
    # استفاده از دیکشنری مشترک یا داخلی (اگر مشترک نیست، همینجا مدیریت می‌شود)
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    """پیام کاربر را برای تمیز ماندن چت حذف می‌کند."""
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass

async def handle_panel_management_menu(call: types.CallbackQuery, params: list):
    """منوی اصلی مدیریت پنل‌ها را نمایش می‌دهد."""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # دریافت تمام پنل‌ها (حتی غیرفعال)
    panels = await db.get_all_panels()
    
    prompt = (
        f"⚙️ *{escape_markdown('مدیریت پنل‌ها')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید سرورهای Hiddify و Marzban متصل به ربات را مدیریت کنید.')}"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    for p in panels:
        # p یک دیکشنری است چون get_all_panels دیکشنری برمی‌گرداند
        status_emoji = "✅" if p['is_active'] else "❌"
        panel_type_fa = "Hiddify" if p['panel_type'] == 'hiddify' else "Marzban"
        btn_text = f"{status_emoji} {p['name']} ({panel_type_fa})"
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:panel_details:{p['id']}"))
    
    # چینش دکمه‌ها
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            kb.add(buttons[i], buttons[i+1])
        else:
            kb.add(buttons[i])
    
    kb.add(types.InlineKeyboardButton("➕ افزودن پنل جدید", callback_data="admin:panel_add_start"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# افزودن پنل جدید (Add Panel Flow)
# ==============================================================================

async def handle_start_add_panel(call: types.CallbackQuery, params: list):
    """مرحله اول: شروع مکالمه و پرسیدن نوع پنل."""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'action': 'add_panel',
        'step': 'type', 
        'msg_id': msg_id, 
        'data': {}
    }
    
    prompt = escape_markdown("1️⃣ لطفاً نوع پنلی که می‌خواهید اضافه کنید را انتخاب کنید:")
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Hiddify", callback_data="admin:panel_set_type:hiddify"),
        types.InlineKeyboardButton("Marzban", callback_data="admin:panel_set_type:marzban")
    )
    kb.add(types.InlineKeyboardButton("🔙 لغو", callback_data="admin:panel_manage"))
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_set_panel_type(call: types.CallbackQuery, params: list):
    """مرحله دوم: ذخیره نوع پنل و پرسیدن نام."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_type = params[0]
    
    if uid not in admin_conversations: return
    admin_conversations[uid]['data']['panel_type'] = panel_type
    admin_conversations[uid]['step'] = 'name'
    
    prompt = escape_markdown("2️⃣ یک نام منحصر به فرد برای این پنل انتخاب کنید (مثال: سرور آلمان):")
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
    admin_conversations[uid]['next_handler'] = get_panel_url

async def get_panel_name(message: types.Message):
    """مرحله سوم: دریافت نام و پرسیدن آدرس URL."""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['name'] = name
    admin_conversations[uid]['step'] = 'url'
    msg_id = admin_conversations[uid]['msg_id']
    
    prompt = escape_markdown(f"3️⃣ لطفاً آدرس کامل پنل را وارد کنید:\n\n*مثال:*\n`https://mypanel.domain.com`")
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
    bot.register_next_step_handler(message, get_panel_url)

async def get_panel_url(message: types.Message):
    """مرحله چهارم: دریافت URL و پرسیدن توکن اول."""
    uid, url = message.from_user.id, message.text.strip().rstrip('/')
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_url'] = url
    admin_conversations[uid]['step'] = 'token1'
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']

    prompt_text = "4️⃣ "
    if panel_type == 'hiddify':
        prompt_text += "لطفاً `API Key` (توکن ادمین) هیدیفای را وارد کنید:"
    else: # Marzban
        prompt_text += "لطفاً `Username` (نام کاربری) ادمین مرزبان را وارد کنید:"
        
    await _safe_edit(uid, msg_id, escape_markdown(prompt_text), reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
    bot.register_next_step_handler(message, get_panel_token1)

async def get_panel_token1(message: types.Message):
    """مرحله پنجم: دریافت توکن اول و پرسیدن توکن دوم (در صورت نیاز)."""
    uid, token1 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_token1'] = token1
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']

    admin_conversations[uid]['step'] = 'token2'
    if panel_type == 'hiddify':
        prompt = escape_markdown("5️⃣ (اختیاری) لطفاً `Proxy Path` را وارد کنید. اگر ندارید، کلمه `ندارم` را ارسال کنید:")
        await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
        bot.register_next_step_handler(message, get_panel_token2)
    else: # Marzban
        prompt = escape_markdown("5️⃣ لطفاً `Password` (رمز عبور) ادمین مرزبان را وارد کنید:")
        await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
        bot.register_next_step_handler(message, get_panel_token2)

async def get_panel_token2(message: types.Message):
    """مرحله ششم (آخر): دریافت توکن دوم و ذخیره پنل."""
    uid, token2 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    convo_data = admin_conversations.pop(uid) # پایان مکالمه
    panel_data = convo_data['data']
    msg_id = convo_data['msg_id']

    if panel_data['panel_type'] == 'hiddify' and token2.lower() in ['ندارم', 'none', 'no', '-']:
        panel_data['api_token2'] = None
    else:
        panel_data['api_token2'] = token2

    # استفاده از متد PanelDB
    success = await db.add_panel(
        name=panel_data['name'],
        panel_type=panel_data['panel_type'],
        api_url=panel_data['api_url'],
        token1=panel_data['api_token1'],
        token2=panel_data['api_token2']
    )

    if success:
        success_message = escape_markdown(f"✅ پنل «{panel_data['name']}» با موفقیت اضافه شد.")
        await _safe_edit(uid, msg_id, success_message, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))
    else:
        error_message = escape_markdown("❌ خطا: پنلی با این نام از قبل وجود دارد. لطفاً دوباره تلاش کنید.")
        await _safe_edit(uid, msg_id, error_message, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

# ==============================================================================
# مدیریت تکی پنل (نمایش، حذف، ویرایش، وضعیت)
# ==============================================================================

async def handle_panel_details(call: types.CallbackQuery, params: list):
    """نمایش جزئیات پنل و گزینه‌های مدیریت."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.", show_alert=True)
        return

    # ساخت URL برای نمایش (بدون نمایش کامل رمز عبور)
    display_url = panel['api_url']
    status = "فعال ✅" if panel['is_active'] else "غیرفعال ❌"
    
    details = [
        f"⚙️ *جزئیات پنل: {escape_markdown(panel['name'])}*",
        f"`──────────────────`",
        f"🔸 *نوع:* {escape_markdown(panel['panel_type'])}",
        f"🔹 *وضعیت:* {status}",
        f"🔗 *آدرس:* `{escape_markdown(display_url)}`",
        f"📂 *دسته‌بندی:* `{escape_markdown(panel.get('category') or 'general')}`"
    ]
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    toggle_text = "غیرفعال کردن" if panel['is_active'] else "فعال کردن"
    
    kb.add(
        types.InlineKeyboardButton(f"🗑 حذف", callback_data=f"admin:panel_delete_confirm:{panel_id}"),
        types.InlineKeyboardButton(f"🔄 {toggle_text}", callback_data=f"admin:panel_toggle:{panel_id}")
    )
    kb.add(types.InlineKeyboardButton(f"✏️ تغییر نام", callback_data=f"admin:panel_edit_start:{panel_id}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:panel_manage"))
    
    await _safe_edit(uid, msg_id, "\n".join(details), reply_markup=kb)

async def handle_panel_toggle_status(call: types.CallbackQuery, params: list):
    """تغییر وضعیت فعال/غیرفعال پنل."""
    panel_id = int(params[0])
    
    if await db.toggle_panel_status(panel_id):
        await bot.answer_callback_query(call.id, "✅ وضعیت پنل تغییر کرد.")
        # رفرش صفحه جزئیات
        await handle_panel_details(call, params)
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در تغییر وضعیت.", show_alert=True)

async def handle_panel_delete_confirm(call: types.CallbackQuery, params: list):
    """نمایش پیام تایید برای حذف پنل."""
    panel_id = int(params[0])
    prompt = "⚠️ *آیا از حذف این پنل اطمینان دارید؟*\nاین کار باعث حذف دسترسی ربات به سرور می‌شود (کاربران در سرور باقی می‌مانند)."
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:panel_delete_execute:{panel_id}"),
        types.InlineKeyboardButton("✅ انصراف", callback_data=f"admin:panel_details:{panel_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=kb)

async def handle_panel_delete_execute(call: types.CallbackQuery, params: list):
    """حذف نهایی پنل."""
    panel_id = int(params[0])
    if await db.delete_panel(panel_id):
        await bot.answer_callback_query(call.id, "✅ پنل با موفقیت حذف شد.")
        await handle_panel_management_menu(call, [])
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در حذف پنل.", show_alert=True)

# ==============================================================================
# ویرایش نام پنل
# ==============================================================================

async def handle_panel_edit_start(call: types.CallbackQuery, params: list):
    """مرحله اول ویرایش: پرسیدن نام جدید."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    admin_conversations[uid] = {
        'action': 'edit_panel_name',
        'msg_id': msg_id, 
        'panel_id': panel_id
    }
    
    prompt = f"نام فعلی: {escape_markdown(panel['name'])}\nلطفاً نام جدید را وارد کنید:"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:panel_details:{panel_id}"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)
    bot.register_next_step_handler(call.message, get_new_panel_name)

async def get_new_panel_name(message: types.Message):
    """مرحله دوم ویرایش: دریافت و ذخیره نام جدید."""
    uid, new_name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    convo = admin_conversations.pop(uid)
    panel_id = convo['panel_id']
    msg_id = convo['msg_id']

    if await db.update_panel_name(panel_id, new_name):
        success_msg = escape_markdown(f"✅ نام پنل به «{new_name}» تغییر کرد.")
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت به جزئیات", callback_data=f"admin:panel_details:{panel_id}"))
        await _safe_edit(uid, msg_id, success_msg, reply_markup=kb)
    else:
        error_msg = escape_markdown("❌ خطا: نام تکراری یا نامعتبر.")
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"admin:panel_edit_start:{panel_id}"))
        await _safe_edit(uid, msg_id, error_msg, reply_markup=kb)