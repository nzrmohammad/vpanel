# bot/admin_handlers/user_mgmt/search.py

from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.formatters import user_formatter
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.services.admin.panel_service import panel_service
from bot.database import db

# متغیرهای سراسری ماژول
bot = None
admin_conversations = {}

def init(b, conv_dict):
    """مقداردهی اولیه متغیرهای ماژول"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    """حذف پیام کاربر برای تمیز ماندن چت"""
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. منوی اصلی مدیریت کاربران
# ==============================================================================

@admin_only
async def handle_management_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی مدیریت کاربران (انتخاب پنل یا عملیات کلی)"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    panels = await panel_service.get_all_panels()
    
    prompt = (
        "👥 *مدیریت کاربران*\n\n"
        "برای مشاهده کاربران، یک سرور انتخاب کنید یا از جستجو استفاده نمایید."
    )
    
    markup = await admin_menu.management_menu(panels)
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup, parse_mode="MarkdownV2")

# ==============================================================================
# 2. جستجو (Search)
# ==============================================================================

@admin_only
async def handle_search_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی انتخاب روش جستجو"""
    uid, msg_id = call.from_user.id, call.message.message_id
    prompt = "🔍 لطفاً روش جستجو را انتخاب کنید:"
    markup = await admin_menu.search_menu()
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup)

@admin_only
async def handle_global_search_convo(call: types.CallbackQuery, params: list):
    """شروع جستجوی متنی (نام، یوزرنیم، UUID)"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'global_search', 
        'msg_id': msg_id, 
        'next_handler': process_search_input
    }
    
    prompt = "🔎 لطفاً نام، یوزرنیم یا بخشی از UUID را وارد کنید:"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

@admin_only
async def handle_search_by_telegram_id_convo(call: types.CallbackQuery, params: list):
    """شروع جستجو با آیدی عددی تلگرام"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'tid_search', 
        'msg_id': msg_id, 
        'next_handler': process_search_input
    }
    
    prompt = "🆔 لطفاً آیدی عددی تلگرام کاربر را وارد کنید:"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

@admin_only
async def process_search_input(message: types.Message):
    """پردازش ورودی جستجو و نمایش نتایج"""
    uid, query = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations.pop(uid)
    msg_id = data['msg_id']
    
    search_type = 'telegram_id' if data['step'] == 'tid_search' else 'global'
    
    await _safe_edit(uid, msg_id, "⏳ در حال جستجو...", reply_markup=None)
    
    users = await admin_user_service.search_users(query, search_type)

    if not users:
        await _safe_edit(uid, msg_id, f"❌ کاربری با مشخصات «{escape_markdown(query)}» یافت نشد.", 
                         reply_markup=await admin_menu.search_menu(), parse_mode="MarkdownV2")
        return
    
    if len(users) == 1:
        await show_user_summary(uid, msg_id, users[0].user_id)
    else:
        text = f"🔍 نتایج جستجو ({len(users)} مورد):"
        kb = types.InlineKeyboardMarkup(row_width=1)
        
        for u in users[:15]: 
            display = f"👤 {u.first_name or 'NoName'} | 🆔 {u.user_id}"
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:us:{u.user_id}:s"))
        
        kb.add(types.InlineKeyboardButton("🔙 جستجوی مجدد", callback_data="admin:search_menu"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb)

# ==============================================================================
# 3. پروفایل کاربر (User Profile & Interactive Menu)
# ==============================================================================

@admin_only
async def handle_show_user_summary(call: types.CallbackQuery, params: list):
    """هندلر نمایش پروفایل کاربر"""
    target = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    if not str(target).isdigit():
        real_id = await db.get_user_id_by_uuid(target)
        if real_id: target = real_id
    
    context = params[1] if len(params) > 1 else None
    await show_user_summary(uid, msg_id, int(target), context)

async def show_user_summary(admin_id, msg_id, target_user_id, context=None, extra_message=None):
    """تابع اصلی ساخت و نمایش پروفایل کاربر"""
    data = await admin_user_service.get_user_profile_data(target_user_id)
    
    if not data or not data['user']:
        await _safe_edit(admin_id, msg_id, "❌ کاربر یافت نشد.", reply_markup=await admin_menu.management_menu([]))
        return

    user = data['user']
    info = data['combined_info']
    safe_name = escape_markdown(user.first_name or 'Unknown')
    
    if info:
        formatted_body = await user_formatter.profile_info(info, 'fa')
        lines = formatted_body.split('\n')
        
        status_emoji = "✅" if info.get('is_active') else "❌"
        lines[0] = f"👤 نام: {safe_name} ({status_emoji})"
        
        lines.append("──────────────────")
        if user.admin_note:
            lines.append(f"📝 یادداشت: {escape_markdown(user.admin_note)}")
        
        lines.append(f"🆔 آیدی تلگرام: `{target_user_id}`")
        lines.append(f"💰 موجودی کیف: `{int(user.wallet_balance or 0):,} تومان`")
        lines.append(f"💳 تعداد تراکنش: {data['payment_count']}")
        
        text = "\n".join(lines)
    else:
        text = (
            f"👤 کاربر: {safe_name}\n"
            f"🔴 وضعیت: غیرفعال (بدون سرویس فعال)\n"
            f"🆔 `{target_user_id}`\n"
            f"💰 موجودی: `{int(user.wallet_balance or 0):,} تومان`"
        )

    if extra_message: text += f"\n\n{extra_message}"

    back_cb = "admin:search_menu" if context == 's' else "admin:management_menu"
    panel_type = 'hiddify' 

    markup = await admin_menu.user_interactive_menu(
        str(target_user_id), 
        bool(data['active_uuids']), 
        panel_type, 
        back_callback=back_cb
    )
    
    await _safe_edit(admin_id, msg_id, text, reply_markup=markup, parse_mode="MarkdownV2")

@admin_only
async def handle_user_interactive_menu(call: types.CallbackQuery, params: list):
    """رفرش کردن منوی دکمه‌ها"""
    await handle_show_user_summary(call, params)

# ==============================================================================
# 4. لیست کاربران پنل (Panel Users List)
# ==============================================================================

@admin_only
async def handle_manage_single_panel_menu(call: types.CallbackQuery, params: list):
    """منوی مدیریت یک پنل خاص (اصلاح شده برای هماهنگی با روتر)"""
    uid, msg_id = call.from_user.id, call.message.message_id
    panel_id = int(params[0])
    panel_type = params[1] if len(params) > 1 else 'unknown'
    
    panel_info = await panel_service.get_panel_details_full(panel_id)
    if not panel_info:
        await bot.answer_callback_query(call.id, "پنل یافت نشد.")
        return
        
    p_name = panel_info['panel']['name']
    
    markup = await admin_menu.manage_single_panel_menu(panel_id, panel_type, p_name)
    msg = f"⚙️ مدیریت سرور: *{escape_markdown(p_name)}*\n\nیک عملیات انتخاب کنید:"
    
    await _safe_edit(uid, msg_id, msg, reply_markup=markup, parse_mode="MarkdownV2")

@admin_only
async def handle_panel_users_list(call: types.CallbackQuery, params: list):
    """نمایش لیست کاربران یک پنل با صفحه‌بندی"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # اصلاح نحوه دریافت پارامترها (گاهی روتر پارامتر اضافی می‌فرستد)
    if params[0] == 'panel_users':
        panel_id = int(params[1])
        page = int(params[2]) if len(params) > 2 else 0
        filter_mode = params[3] if len(params) > 3 else "all"
    else:
        panel_id = int(params[0])
        page = int(params[1]) if len(params) > 1 else 0
        filter_mode = params[2] if len(params) > 2 else "all"
    
    limit = 10
    offset = page * limit
    
    users, total = await db.get_users_by_panel(panel_id, offset, limit, filter_mode)
    
    panel_info = await panel_service.get_panel_details_full(panel_id)
    p_name = panel_info['panel']['name']
    
    text = f"📋 لیست کاربران سرور *{escape_markdown(p_name)}*:\n"
    text += f"وضعیت: {filter_mode}\n\n"
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    for u in users:
        name = u.get('name') or "بی‌نام"
        usage = f"{u.get('usage_percentage', 0)}%"
        btn_text = f"{name} ({usage})"
        kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:us:{u['user_id']}:p{panel_id}"))
        
    nav_btns = []
    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin:p_users:{panel_id}:{page-1}:{filter_mode}"))
    if offset + limit < total:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin:p_users:{panel_id}:{page+1}:{filter_mode}"))
    
    if nav_btns: kb.row(*nav_btns)
    
    kb.row(types.InlineKeyboardButton(f"🔍 فیلتر: {filter_mode}", callback_data=f"admin:filter_users:{panel_id}:{filter_mode}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:manage_single_panel:{panel_id}:x"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_filter_users(call: types.CallbackQuery, params: list):
    """تغییر مود فیلتر لیست کاربران"""
    panel_id = params[0]
    current_mode = params[1]
    
    modes = ['all', 'online', 'expired', 'active']
    try:
        next_index = (modes.index(current_mode) + 1) % len(modes)
    except:
        next_index = 0
    next_mode = modes[next_index]
    
    new_params = [panel_id, 0, next_mode]
    await handle_panel_users_list(call, new_params)