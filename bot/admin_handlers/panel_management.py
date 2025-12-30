# bot/admin_handlers/panel_management.py

import logging
import time
from telebot import types

# --- Imports ---
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.decorators import admin_only
from bot.services.admin.panel_service import panel_service 
from bot.database import db

logger = logging.getLogger(__name__)

# متغیرهای سراسری برای نگهداری وضعیت ربات و مکالمات
bot = None
admin_conversations = {}

def initialize_panel_management_handlers(b, conv_dict):
    """
    مقادیر bot و admin_conversations را از فایل اصلی (admin_router) دریافت می‌کند.
    """
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    """تابع کمکی برای حذف پیام کاربر"""
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. منوی لیست پنل‌ها (Main List)
# ==============================================================================

@admin_only
async def handle_panel_management_menu(call: types.CallbackQuery, params: list):
    """نمایش لیست تمام پنل‌های متصل"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # دریافت لیست پنل‌ها از سرویس
    panels = await panel_service.get_all_panels()
    
    prompt = (
        f"⚙️ *{escape_markdown('مدیریت پنل‌ها')}*\n\n"
        f"{escape_markdown('در این بخش می‌توانید سرورهای Hiddify، Marzban،Remnawave و Remnawave متصل به ربات را مدیریت کنید.')}"
    )
    
    markup = await admin_menu.panel_list_menu(panels)
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup, parse_mode="MarkdownV2")

# ==============================================================================
# 2. پروسه افزودن پنل جدید (Add Panel Wizard)
# ==============================================================================

@admin_only
async def handle_start_add_panel(call: types.CallbackQuery, params: list):
    """شروع پروسه افزودن پنل: انتخاب نوع پنل"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # شروع استیت مکالمه
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
        types.InlineKeyboardButton("Remnawave", callback_data="admin:panel_set_type:remnawave"),
        types.InlineKeyboardButton("Pasarguard", callback_data="admin:panel_set_type:pasarguard")
    )
    kb.row(types.InlineKeyboardButton("🔙 لغو", callback_data="admin:panel_manage"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

@admin_only
async def handle_set_panel_type(call: types.CallbackQuery, params: list):
    """مرحله ۲: دریافت نام پنل"""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_type = params[0]
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['data']['panel_type'] = panel_type
    admin_conversations[uid]['step'] = 'name'
    admin_conversations[uid]['next_handler'] = get_panel_name
    
    prompt = escape_markdown("2️⃣ یک نام منحصر به فرد برای این پنل انتخاب کنید (مثال: سرور آلمان):")
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

@admin_only
async def get_panel_name(message: types.Message):
    """مرحله ۳: دریافت آدرس URL"""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['name'] = name
    admin_conversations[uid]['step'] = 'url'
    msg_id = admin_conversations[uid]['msg_id']
    admin_conversations[uid]['next_handler'] = get_panel_url
    
    prompt = f"3️⃣ {escape_markdown('آدرس کامل پنل (با http/https):')}\n`https://mypanel.domain.com`"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

@admin_only
async def get_panel_url(message: types.Message):
    """مرحله ۴: دریافت توکن اول"""
    uid, url = message.from_user.id, message.text.strip().rstrip('/')
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_url'] = url
    admin_conversations[uid]['step'] = 'token1'
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']
    admin_conversations[uid]['next_handler'] = get_panel_token1

    # تعیین متن راهنما بر اساس نوع پنل
    if panel_type == 'hiddify': 
        msg = "لطفاً API Key (Admin Token) را از مسیر تنظیمات ادمین > ادمین‌ها کپی کنید:"
    elif panel_type == 'remnawave': 
        msg = "لطفاً API Token را وارد کنید:"
    else: 
        msg = "نام کاربری ادمین (Admin Username) را وارد کنید:"
        
    prompt = f"4️⃣ {escape_markdown(msg)}"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

@admin_only
async def get_panel_token1(message: types.Message):
    """مرحله ۵: دریافت توکن دوم (در صورت نیاز)"""
    uid, token1 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return

    admin_conversations[uid]['data']['api_token1'] = token1
    msg_id = admin_conversations[uid]['msg_id']
    panel_type = admin_conversations[uid]['data']['panel_type']

    if panel_type == 'remnawave':
        # رمناویو توکن دوم ندارد
        admin_conversations[uid]['data']['api_token2'] = None
        await _ask_category(uid, msg_id)
        return

    admin_conversations[uid]['step'] = 'token2'
    admin_conversations[uid]['next_handler'] = get_panel_token2

    if panel_type == 'hiddify': 
        # [MODIFIED] حذف قسمت اختیاری بودن (ندارم)
        prompt = "لطفاً Proxy Path را وارد کنید:"
    else: 
        prompt = "رمز عبور ادمین (Admin Password):"
    
    await _safe_edit(uid, msg_id, escape_markdown(f"5️⃣ {prompt}"), reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

@admin_only
async def get_panel_token2(message: types.Message):
    """مرحله ۶: انتخاب دسته‌بندی کشور"""
    uid, token2 = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return

    if admin_conversations[uid]['data']['panel_type'] == 'hiddify' and token2.lower() in ['ندارم', 'none', '-', '.']:
        admin_conversations[uid]['data']['api_token2'] = None
    else:
        admin_conversations[uid]['data']['api_token2'] = token2

    await _ask_category(uid, admin_conversations[uid]['msg_id'])

async def _ask_category(uid, msg_id):
    """نمایش کیبورد انتخاب کشور"""
    admin_conversations[uid]['step'] = 'select_category'
    admin_conversations[uid]['next_handler'] = None
    
    categories = await db.get_server_categories()
    
    prompt = f"6️⃣ {escape_markdown('لطفاً کشور این سرور را انتخاب کنید:')}"
    markup = await admin_menu.panel_category_selection_menu(categories)
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup)

@admin_only
async def handle_set_panel_category(call: types.CallbackQuery, params: list):
    """ذخیره نهایی پنل در دیتابیس"""
    uid = call.from_user.id
    category_code = params[0]
    
    if uid not in admin_conversations:
        await bot.answer_callback_query(call.id, "❌ نشست منقضی شد.", show_alert=True)
        return

    convo_data = admin_conversations.pop(uid)
    d = convo_data['data']
    msg_id = convo_data['msg_id']

    # فراخوانی سرویس برای افزودن
    res = await panel_service.add_new_panel(
        d['name'], d['panel_type'], d['api_url'], d['api_token1'], d['api_token2'], category_code
    )

    if res['success']:
        msg = escape_markdown(f"✅ پنل «{d['name']}» با موفقیت ثبت شد.")
        # بازگشت به لیست اصلی
        panels = await panel_service.get_all_panels()
        await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.panel_list_menu(panels))
    else:
        err_msg = res.get('error')
        if err_msg == 'duplicate_name':
            err_text = "نام انتخاب شده تکراری است."
        else:
            err_text = f"خطا: {err_msg}"
            
        err = escape_markdown(f"❌ {err_text}")
        await _safe_edit(uid, msg_id, err, reply_markup=await admin_menu.cancel_action("admin:panel_manage"))

# ==============================================================================
# 3. نمایش جزئیات و مدیریت پنل (Panel Details)
# ==============================================================================

@admin_only
async def handle_panel_details(call: types.CallbackQuery, params: list):
    """نمایش اطلاعات کامل یک پنل + لیست نودها"""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    # دریافت اطلاعات کامل (پنل + نودها) از سرویس
    data = await panel_service.get_panel_details_full(panel_id)
    if not data:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    panel = data['panel']
    nodes = data['nodes']
    
    status = "فعال ✅" if panel['is_active'] else "غیرفعال ❌"
    
    details = [
        f"⚙️ *جزئیات پنل: {escape_markdown(panel['name'])}*",
        f"`──────────────────`",
        f"🔸 *نوع:* {escape_markdown(panel['panel_type'])}",
        f"🔹 *وضعیت:* {status}",
        f"🔗 *آدرس:* `{escape_markdown(panel['api_url'])}`",
        f"📂 *کشور:* `{escape_markdown(panel.get('category') or 'general')}`"
    ]

    # استفاده از رشته خام (rf) برای جلوگیری از خطای Escape Sequence
    if nodes:
        details.append(rf"\n🌱 *نودها \({len(nodes)}\):*")
        for n in nodes:
            n_status = "✅" if n.get('is_active', True) else "❌"
            # استفاده از رشته خام (rf)
            details.append(rf"{n['flag']} {escape_markdown(n['name'])} `\({n['code']}\)` {n_status}")
    else:
        details.append(f"\n🌱 *نودها:* هیچ نودی تعریف نشده است")

    # ساخت دکمه‌ها (مدیریت، افزودن نود، حذف و...)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✏️ تغییر نام", callback_data=f"admin:panel_ch_ren:{panel_id}"),
        types.InlineKeyboardButton("➕ افزودن نود", callback_data=f"admin:panel_add_node_start:{panel_id}")
    )
    kb.add(
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin:panel_ch_del:{panel_id}"),
        types.InlineKeyboardButton("🔄 تغییر وضعیت", callback_data=f"admin:panel_ch_tog:{panel_id}"),
    )
    
    # اگر نود دارد، دکمه‌های مدیریت نودها را نمایش بده
    if nodes:
        kb.add(types.InlineKeyboardButton("⚙️ مدیریت نودها (حذف/تغییر)", callback_data=f"admin:panel_manage_nodes:{panel_id}"))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:panel_manage"))
    
    await _safe_edit(uid, msg_id, "\n".join(details), reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# 4. افزودن نود جدید (Add Node Flow)
# ==============================================================================

@admin_only
async def handle_panel_add_node_start(call: types.CallbackQuery, params: list):
    """شروع افزودن نود: دریافت نام"""
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
    
    # استفاده از رشته خام (rf)
    prompt = r"1️⃣ لطفاً *نام این نود* را وارد کنید:\n\(مثال: سرور دانلود، نود شماره 2\)"
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{panel_id}"))
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def get_node_name(message: types.Message):
    """انتخاب کشور/پرچم برای نود"""
    uid, name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['node_name'] = name
    admin_conversations[uid]['step'] = 'flag'
    admin_conversations[uid]['next_handler'] = None
    
    categories = await db.get_server_categories()
    
    prompt = f"2️⃣ نام نود: {escape_markdown(name)}\nحالا **کشور/پرچم** این نود را انتخاب کنید:"
    
    kb = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for c in categories:
        buttons.append(types.InlineKeyboardButton(f"{c['emoji']} {c['name']}", callback_data=f"admin:panel_node_save:{c['code']}"))
    
    kb.add(*buttons)
    kb.row(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{admin_conversations[uid]['panel_id']}"))

    await _safe_edit(uid, admin_conversations[uid]['msg_id'], prompt, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_panel_node_save(call: types.CallbackQuery, params: list):
    """ذخیره نهایی نود"""
    uid = call.from_user.id
    country_code = params[0]
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    categories = await db.get_server_categories()
    # پیدا کردن اموجی پرچم
    flag = next((c['emoji'] for c in categories if c['code'] == country_code), "🏳️")
            
    # ذخیره با استفاده از سرویس
    await panel_service.add_node(data['panel_id'], data['node_name'], country_code, flag)
    
    await bot.answer_callback_query(call.id, "✅ نود با موفقیت اضافه شد.")
    # بازگشت به جزئیات پنل
    await handle_panel_details(call, [data['panel_id']])

# ==============================================================================
# 5. مدیریت نودهای موجود (حذف / تغییر وضعیت)
# ==============================================================================

@admin_only
async def handle_panel_manage_nodes(call: types.CallbackQuery, params: list):
    """نمایش لیست نودها برای انتخاب عملیات"""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    data = await panel_service.get_panel_details_full(panel_id)
    if not data or not data['nodes']:
        await bot.answer_callback_query(call.id, "❌ نودی برای مدیریت وجود ندارد.")
        return
        
    nodes = data['nodes']
    kb = types.InlineKeyboardMarkup(row_width=1)
    
    for n in nodes:
        status_icon = "🟢" if n['is_active'] else "🔴"
        btn_text = f"{status_icon} {n['flag']} {n['name']} (حذف 🗑)"
        # کال‌بک: admin:node_delete_conf:NODE_ID
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:node_delete_conf:{n['id']}"))
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:panel_details:{panel_id}"))
    
    prompt = escape_markdown("برای **حذف** نود، روی آن کلیک کنید:")
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_node_delete_confirm(call: types.CallbackQuery, params: list):
    node_id = int(params[0])
    # مستقیم حذف می‌کنیم (یا می‌توان تاییدیه گرفت)
    node = await panel_service.get_node(node_id)
    if node:
        await panel_service.delete_node(node_id)
        await bot.answer_callback_query(call.id, "🗑 نود حذف شد.")
        # بازگشت به لیست نودها
        await handle_panel_manage_nodes(call, [node['panel_id']])

# ==============================================================================
# 6. عملیات‌های مدیریتی پنل (Rename, Delete, Toggle)
# ==============================================================================

# --- تغییر نام پنل ---
@admin_only
async def handle_panel_choice_rename(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    
    admin_conversations[uid] = {
        'action': 'rename_panel',
        'panel_id': panel_id,
        'msg_id': msg_id,
        'next_handler': do_rename_panel,
        'timestamp': time.time()
    }
    
    prompt = escape_markdown("✏️ لطفاً نام جدید پنل را وارد کنید:")
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"admin:panel_details:{panel_id}"))
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

@admin_only
async def do_rename_panel(message: types.Message):
    uid, new_name = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    
    await panel_service.update_panel_name(data['panel_id'], new_name)
    
    # ساختن یک کال‌بک مصنوعی برای بازگشت به صفحه پنل
    fake_call = types.CallbackQuery(id='0', from_user=message.from_user, data=f"admin:panel_details:{data['panel_id']}", message=message)
    fake_call.message.message_id = data['msg_id']
    
    await bot.send_message(message.chat.id, "✅ نام پنل تغییر کرد.", disable_notification=True)
    await handle_panel_details(fake_call, [data['panel_id']])

# --- تغییر وضعیت پنل (Toggle) ---
@admin_only
async def handle_panel_choice_toggle(call: types.CallbackQuery, params: list):
    panel_id = int(params[0])
    await panel_service.toggle_panel_status(panel_id)
    await bot.answer_callback_query(call.id, "✅ وضعیت پنل تغییر کرد.")
    await handle_panel_details(call, [panel_id])

# --- حذف پنل ---
@admin_only
async def handle_panel_choice_delete(call: types.CallbackQuery, params: list):
    """درخواست تایید حذف"""
    panel_id = int(params[0])
    prompt = "⚠️ *آیا از حذف کامل این پنل و نودهای آن اطمینان دارید؟*"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❌ بله، حذف کن", callback_data=f"admin:panel_del_exec:{panel_id}"),
        types.InlineKeyboardButton("✅ انصراف", callback_data=f"admin:panel_details:{panel_id}")
    )
    await _safe_edit(call.from_user.id, call.message.message_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_panel_delete_execute(call: types.CallbackQuery, params: list):
    """اجرای حذف"""
    panel_id = int(params[0])
    await panel_service.delete_panel(panel_id)
    await bot.answer_callback_query(call.id, "✅ پنل حذف شد.")
    await handle_panel_management_menu(call, [])

# ==============================================================================
# 7. Placeholder Handlers (برای جلوگیری از خطای AttributeError در Router)
# ==============================================================================

@admin_only
async def handle_panel_edit_start(call: types.CallbackQuery, params: list):
    """Placeholder for panel_edit_start"""
    await bot.answer_callback_query(call.id, "🚧 در حال توسعه...", show_alert=True)

@admin_only
async def handle_panel_node_selection(call: types.CallbackQuery, params: list):
    """Placeholder for panel_node_sel"""
    await bot.answer_callback_query(call.id, "🚧 در حال توسعه...", show_alert=True)

@admin_only
async def handle_node_rename_start(call: types.CallbackQuery, params: list):
    """Placeholder for p_node_ren_st"""
    await bot.answer_callback_query(call.id, "🚧 در حال توسعه...", show_alert=True)

@admin_only
async def handle_node_toggle(call: types.CallbackQuery, params: list):
    """Placeholder for p_node_tog"""
    await bot.answer_callback_query(call.id, "🚧 در حال توسعه...", show_alert=True)