# bot/admin_handlers/panel_management.py

import logging
import time
from telebot import types
from bot.database import db
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

logger = logging.getLogger(__name__)
bot = None
admin_conversations = {}

def initialize_panel_management_handlers(b, conv_dict):
    """مقادیر bot و admin_conversations را از فایل اصلی دریافت می‌کند."""
    global bot, admin_conversations
    bot = b
    # استفاده از دیکشنری مشترک برای مدیریت استیت‌ها در روتر
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
    
    # دریافت تمام پنل‌ها
    panels = await db.get_all_panels()
    
    prompt = (
        f"⚙️ *{escape_markdown('مدیریت پنل‌ها')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید سرورهای Hiddify، Marzban و Remnawave متصل به ربات را مدیریت کنید.')}"
    )
    
    markup = await admin_menu.panel_list_menu(panels)
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup, parse_mode="MarkdownV2")

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
        'data': {},
        'timestamp': time.time()
    }
    
    prompt = escape_markdown("1️⃣ لطفاً نوع پنلی که می‌خواهید اضافه کنید را انتخاب کنید:")
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Hiddify", callback_data="admin:panel_set_type:hiddify"),
        types.InlineKeyboardButton("Marzban", callback_data="admin:panel_set_type:marzban"),
        types.InlineKeyboardButton("Remnawave", callback_data="admin:panel_set_type:remnawave")
    )
    kb.row(types.InlineKeyboardButton("🔙 لغو", callback_data="admin:panel_manage"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_set_panel_type(call: types.CallbackQuery, params: list):
    """مرحله دوم: ذخیره نوع پنل و پرسیدن نام."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_type = params[0]
    
    if uid not in admin_conversations: return
    admin_conversations[uid]['data']['panel_type'] = panel_type
    admin_conversations[uid]['step'] = 'name'
    admin_conversations[uid]['timestamp'] = time.time()
    admin_conversations[uid]['next_handler'] = get_panel_name
    
    prompt = escape_markdown("2️⃣ یک نام منحصر به فرد برای این پنل انتخاب کنید (مثال: سرور آلمان):")
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

async def get_panel_name(message: types.Message):
    """مرحله سوم: دریافت نام و پرسیدن آدرس URL."""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['name'] = name
    admin_conversations[uid]['step'] = 'url'
    msg_id = admin_conversations[uid]['msg_id']
    admin_conversations[uid]['next_handler'] = get_panel_url
    
    prompt = (
        f"3️⃣ {escape_markdown('لطفاً آدرس کامل پنل را وارد کنید:')}\n\n"
        f"*{escape_markdown('مثال:')}*\n"
        f"`https://mypanel.domain.com`"
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

async def get_panel_url(message: types.Message):
    """مرحله چهارم: دریافت URL و پرسیدن توکن اول."""
    uid, url = message.from_user.id, message.text.strip().rstrip('/')
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_url'] = url
    admin_conversations[uid]['step'] = 'token1'
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']
    admin_conversations[uid]['next_handler'] = get_panel_token1

    prefix = "4️⃣ "
    if panel_type == 'hiddify':
        msg = f"{prefix}{escape_markdown('لطفاً')} `API Key` {escape_markdown('(توکن ادمین) هیدیفای را وارد کنید:')}"
    elif panel_type == 'remnawave':
        msg = f"{prefix}{escape_markdown('لطفاً')} `API Token` {escape_markdown('ادمین رمناویو را وارد کنید:')}"
    else: # Marzban
        msg = f"{prefix}{escape_markdown('لطفاً')} `Username` {escape_markdown('(نام کاربری) ادمین مرزبان را وارد کنید:')}"
        
    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

async def get_panel_token1(message: types.Message):
    """مرحله پنجم: دریافت توکن اول و تصمیم‌گیری برای مرحله بعد."""
    uid, token1 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_token1'] = token1
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']

    if panel_type == 'remnawave':
        admin_conversations[uid]['data']['api_token2'] = None
        admin_conversations[uid]['step'] = 'select_category'
        admin_conversations[uid]['next_handler'] = None
        
        categories = await db.get_server_categories()
        prompt = f"6️⃣ {escape_markdown('لطفاً')} *{escape_markdown('موقعیت (کشور)')}* {escape_markdown('این سرور را انتخاب کنید:')}"
        markup = await admin_menu.panel_category_selection_menu(categories)
        await _safe_edit(uid, msg_id, prompt, reply_markup=markup)
        return

    admin_conversations[uid]['step'] = 'token2'
    admin_conversations[uid]['next_handler'] = get_panel_token2

    if panel_type == 'hiddify':
        prompt = f"5️⃣ {escape_markdown('لطفاً')} `Proxy Path` {escape_markdown('را وارد کنید. اگر ندارید، کلمه')} `ندارم` {escape_markdown('را ارسال کنید:')}"
    else: # Marzban
        prompt = f"5️⃣ {escape_markdown('لطفاً')} `Password` {escape_markdown('(رمز عبور) ادمین مرزبان را وارد کنید:')}"
        
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

async def get_panel_token2(message: types.Message):
    """مرحله ششم: دریافت توکن دوم و نمایش منوی انتخاب کشور."""
    uid, token2 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return

    if admin_conversations[uid]['data']['panel_type'] == 'hiddify' and token2.lower() in ['ندارم', 'none', 'no', '-', '.']:
        admin_conversations[uid]['data']['api_token2'] = None
    else:
        admin_conversations[uid]['data']['api_token2'] = token2

    admin_conversations[uid]['step'] = 'select_category'
    msg_id = admin_conversations[uid]['msg_id']
    admin_conversations[uid]['next_handler'] = None

    categories = await db.get_server_categories()
    
    prompt = f"6️⃣ {escape_markdown('لطفاً')} *{escape_markdown('موقعیت (کشور)')}* {escape_markdown('این سرور را انتخاب کنید:')}"
    markup = await admin_menu.panel_category_selection_menu(categories)
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup)

async def handle_set_panel_category(call: types.CallbackQuery, params: list):
    """مرحله هفتم (نهایی): ذخیره پنل در دیتابیس."""
    uid = call.from_user.id
    category_code = params[0]
    
    if uid not in admin_conversations:
        await bot.answer_callback_query(call.id, "❌ نشست منقضی شد.", show_alert=True)
        return

    convo_data = admin_conversations.pop(uid)
    panel_data = convo_data['data']
    msg_id = convo_data['msg_id']

    success = await db.add_panel(
        name=panel_data['name'],
        panel_type=panel_data['panel_type'],
        api_url=panel_data['api_url'],
        token1=panel_data['api_token1'],
        token2=panel_data['api_token2'],
        category=category_code
    )

    if success:
        success_message = escape_markdown(f"✅ پنل «{panel_data['name']}» با موفقیت ثبت شد.")
        all_panels = await db.get_all_panels()
        await _safe_edit(uid, msg_id, success_message, reply_markup=await admin_menu.panel_list_menu(all_panels))
    else:
        error_message = escape_markdown("❌ خطا: نام پنل تکراری است.")
        await _safe_edit(uid, msg_id, error_message, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

# ==============================================================================
# مدیریت تکی پنل (نمایش جزئیات + نودها + منوهای هوشمند)
# ==============================================================================

async def handle_panel_details(call: types.CallbackQuery, params: list):
    """نمایش جزئیات پنل + لیست نودها + دکمه‌های دو ستونه."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    nodes = await db.get_panel_nodes(panel_id)
    display_url = panel['api_url']
    status = "فعال ✅" if panel['is_active'] else "غیرفعال ❌"
    
    # ساخت متن پیام با رعایت اسکیپ برای جلوگیری از Bad Request
    details = [
        f"⚙️ *جزئیات پنل: {escape_markdown(panel['name'])}*",
        f"`──────────────────`",
        f"🔸 *نوع:* {escape_markdown(panel['panel_type'])}",
        f"🔹 *وضعیت پنل:* {status}",
        f"🔗 *آدرس:* `{escape_markdown(display_url)}`",
        f"📂 *دسته‌بندی اصلی:* `{escape_markdown(panel.get('category') or 'general')}`"
    ]

    if nodes:
        # پرانتزها اسکیپ شدند: \( \)
        details.append(f"\n🌱 *نودهای متصل \({len(nodes)}\):*")
        for n in nodes:
            n_status = "✅" if n.get('is_active', True) else "❌"
            # نمایش: 🇩🇪 نام (کد) [وضعیت]
            details.append(f"{n['flag']} {escape_markdown(n['name'])} `\({n['code']}\)` {n_status}")
    else:
        details.append(f"\n🌱 *نودها:* هیچ نودی تعریف نشده است")

    # --- چیدمان دکمه‌ها ---
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # ردیف ۱: افزودن نود | تغییر نام
    kb.add(
        types.InlineKeyboardButton("✏️ تغییر نام", callback_data=f"admin:panel_ch_ren:{panel_id}"),
        types.InlineKeyboardButton("➕ افزودن نود", callback_data=f"admin:panel_add_node_start:{panel_id}")
    )
    
    # ردیف ۲: تغییر وضعیت | حذف
    kb.add(
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin:panel_ch_del:{panel_id}"),
        types.InlineKeyboardButton("🔄 تغییر وضعیت", callback_data=f"admin:panel_ch_tog:{panel_id}"),
        
    )
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:panel_manage"))
    
    await _safe_edit(uid, msg_id, "\n".join(details), reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# منوهای واسط (انتخاب بین پنل و نود)
# ==============================================================================

async def handle_choice_menu(call: types.CallbackQuery, params: list, action_type: str):
    """تابع عمومی برای نمایش منوی انتخاب (پنل یا نود)."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel: return

    action_texts = {
        "rename": "تغییر نام",
        "delete": "حذف",
        "toggle": "تغییر وضعیت"
    }
    act_name = action_texts.get(action_type, action_type)
    
    prompt = f"❓ *{act_name}* روی کدام مورد انجام شود؟"
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    # دکمه عملیات روی خود پنل
    if action_type == "rename":
        kb.add(types.InlineKeyboardButton(f"سرور اصلی ({panel['name']})", callback_data=f"admin:panel_edit_start:{panel_id}"))
    elif action_type == "delete":
        kb.add(types.InlineKeyboardButton(f"سرور اصلی ({panel['name']})", callback_data=f"admin:panel_delete_confirm:{panel_id}"))
    elif action_type == "toggle":
        kb.add(types.InlineKeyboardButton(f"سرور اصلی ({panel['name']})", callback_data=f"admin:panel_toggle:{panel_id}"))

    # دکمه عملیات روی نودها (لیست نودها را باز میکند)
    kb.add(types.InlineKeyboardButton("🌱 یکی از نودها", callback_data=f"admin:panel_node_sel:{panel_id}:{action_type}"))
    
    kb.add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{panel_id}"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_panel_choice_rename(call, params): await handle_choice_menu(call, params, "rename")
async def handle_panel_choice_delete(call, params): await handle_choice_menu(call, params, "delete")
async def handle_panel_choice_toggle(call, params): await handle_choice_menu(call, params, "toggle")

async def handle_panel_node_selection(call: types.CallbackQuery, params: list):
    """لیست نودها را برای انتخاب نشان می‌دهد."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    action_type = params[1] # rename, delete, toggle
    
    nodes = await db.get_panel_nodes(panel_id)
    if not nodes:
        await bot.answer_callback_query(call.id, "❌ هیچ نودی وجود ندارد.", show_alert=True)
        return

    prompt = "👇 لطفاً نود مورد نظر را انتخاب کنید:"
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    for n in nodes:
        # تعیین کال‌بک نهایی بر اساس نوع عملیات
        if action_type == "rename":
            cb = f"admin:p_node_ren_st:{n['id']}"
        elif action_type == "delete":
            cb = f"admin:p_node_del:{n['id']}"
        else: # toggle
            cb = f"admin:p_node_tog:{n['id']}"
            
        kb.add(types.InlineKeyboardButton(f"{n['flag']} {n['name']}", callback_data=cb))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:panel_details:{panel_id}"))
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

# ==============================================================================
# عملیات‌های مربوط به نود (Add, Rename, Toggle, Delete)
# ==============================================================================

# --- افزودن نود ---
async def handle_panel_add_node_start(call: types.CallbackQuery, params: list):
    """مرحله ۱: شروع افزودن نود."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    admin_conversations[uid] = {
        'action': 'add_node',
        'step': 'name',
        'panel_id': panel_id,
        'msg_id': msg_id,
        'next_handler': get_node_name,
        'timestamp': time.time()
    }
    
    # اسکیپ کردن پرانتزها برای جلوگیری از ارور
    prompt = (
        "1️⃣ لطفاً *نام این نود* را وارد کنید:\n"
        "\(مثال: سرور دانلود، نود شماره 2\)"
    )
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{panel_id}"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def get_node_name(message: types.Message):
    """مرحله ۲: دریافت نام نود و نمایش پرچم‌ها."""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['node_name'] = name
    admin_conversations[uid]['step'] = 'flag'
    panel_id = admin_conversations[uid]['panel_id']
    msg_id = admin_conversations[uid]['msg_id']
    admin_conversations[uid]['next_handler'] = None
    
    categories = await db.get_server_categories()
    
    prompt = (
        f"2️⃣ نام نود: {escape_markdown(name)}\n"
        f"حالا **کشور/پرچم** این نود را انتخاب کنید:"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cat in categories:
        btn_text = f"{cat['emoji']} {cat['name']}"
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:panel_node_save:{cat['code']}"))
    kb.add(*buttons)
    kb.row(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{panel_id}"))

    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_panel_node_save(call: types.CallbackQuery, params: list):
    """مرحله ۳: ذخیره نود در دیتابیس."""
    uid = call.from_user.id
    country_code = params[0]
    
    if uid not in admin_conversations: return
    
    data = admin_conversations.pop(uid)
    panel_id = data['panel_id']
    name = data['node_name']
    
    categories = await db.get_server_categories()
    flag = "🏳️"
    for c in categories:
        if c['code'] == country_code:
            flag = c['emoji']
            break
            
    await db.add_panel_node(panel_id, name, country_code, flag)
    await bot.answer_callback_query(call.id, "✅ نود با موفقیت اضافه شد.")
    await handle_panel_details(call, [panel_id])

# --- تغییر نام نود ---
async def handle_node_rename_start(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    node_id = int(params[0])
    
    node = await db.get_panel_node_by_id(node_id)
    if not node: return
    
    admin_conversations[uid] = {
        'action': 'edit_node_name',
        'node_id': node_id,
        'panel_id': node['panel_id'],
        'msg_id': msg_id,
        'next_handler': get_new_node_name,
        'timestamp': time.time()
    }
    
    prompt = f"نام فعلی نود: {escape_markdown(node['name'])}\nلطفاً نام جدید را وارد کنید:"
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{node['panel_id']}"))
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def get_new_node_name(message: types.Message):
    uid, new_name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in admin_conversations: return
    
    data = admin_conversations.pop(uid)
    if await db.update_panel_node_name(data['node_id'], new_name):
        await bot.send_message(message.chat.id, "✅ نام نود تغییر کرد.")
    
    # بازگشت به منوی پنل (با ساخت یک کال‌بک ساختگی برای استفاده مجدد از تابع)
    fake_call = types.CallbackQuery(id='0', from_user=message.from_user, data='fake', message=message)
    fake_call.message.message_id = data['msg_id']
    await handle_panel_details(fake_call, [data['panel_id']])

# --- تغییر وضعیت و حذف نود ---
async def handle_node_toggle(call: types.CallbackQuery, params: list):
    node_id = int(params[0])
    node = await db.get_panel_node_by_id(node_id)
    if node and await db.toggle_panel_node_status(node_id):
        await bot.answer_callback_query(call.id, "✅ وضعیت نود تغییر کرد.")
        await handle_panel_details(call, [node['panel_id']])

async def handle_node_delete(call: types.CallbackQuery, params: list):
    node_id = int(params[0])
    node = await db.get_panel_node_by_id(node_id)
    if node:
        await db.delete_panel_node(node_id)
        await bot.answer_callback_query(call.id, "🗑 نود حذف شد.")
        await handle_panel_details(call, [node['panel_id']])

# ==============================================================================
# عملیات‌های مربوط به پنل اصلی (تغییر نام، وضعیت، حذف)
# ==============================================================================

async def handle_panel_toggle_status(call: types.CallbackQuery, params: list):
    """تغییر وضعیت فعال/غیرفعال پنل."""
    panel_id = int(params[0])
    if await db.toggle_panel_status(panel_id):
        await bot.answer_callback_query(call.id, "✅ وضعیت پنل تغییر کرد.")
        await handle_panel_details(call, params)
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در تغییر وضعیت.", show_alert=True)

async def handle_panel_delete_confirm(call: types.CallbackQuery, params: list):
    """نمایش پیام تایید برای حذف پنل."""
    panel_id = int(params[0])
    prompt = "⚠️ *آیا از حذف این پنل اطمینان دارید؟*\nاین کار باعث حذف دسترسی ربات به سرور می‌شود \(کاربران در سرور باقی می‌مانند\)\."
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:panel_delete_execute:{panel_id}"),
        types.InlineKeyboardButton("✅ انصراف", callback_data=f"admin:panel_details:{panel_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_panel_delete_execute(call: types.CallbackQuery, params: list):
    """حذف نهایی پنل."""
    panel_id = int(params[0])
    if await db.delete_panel(panel_id):
        await bot.answer_callback_query(call.id, "✅ پنل با موفقیت حذف شد.")
        await handle_panel_management_menu(call, [])
    else:
        await bot.answer_callback_query(call.id, "❌ خطا در حذف پنل.", show_alert=True)

async def handle_panel_edit_start(call: types.CallbackQuery, params: list):
    """مرحله اول ویرایش نام پنل."""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    admin_conversations[uid] = {
        'action': 'edit_panel_name',
        'msg_id': msg_id, 
        'panel_id': panel_id,
        'next_handler': get_new_panel_name,
        'timestamp': time.time()
    }
    
    prompt = f"نام فعلی: {escape_markdown(panel['name'])}\nلطفاً نام جدید را وارد کنید:"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:panel_details:{panel_id}"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def get_new_panel_name(message: types.Message):
    """مرحله دوم ویرایش نام پنل."""
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