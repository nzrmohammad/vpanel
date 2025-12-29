# bot/admin_handlers/user_mgmt/access.py

import time
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.database import db
from bot import combined_handler 

bot = None
admin_conversations = {}

def init(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

# ==============================================================================
# 1. مدیریت نودها (Access Panel List)
# ==============================================================================

@admin_only
async def handle_user_access_panel_list(call: types.CallbackQuery, params: list):
    """لیست سرورها برای مدیریت دسترسی نودها"""
    target_id = int(params[0])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    data = await admin_user_service.get_node_access_matrix(target_id)
    if not data:
        await bot.answer_callback_query(call.id, "کاربر یافت نشد.")
        return

    # ساخت کیبورد ماتریسی
    kb = types.InlineKeyboardMarkup()
    cat_map = data['categories']
    allowed = data['allowed_ids']
    
    # گروه‌بندی نودها بر اساس پنل
    nodes_map = {}
    for n in data['nodes']:
        nodes_map.setdefault(n.panel_id, []).append(n)
        
    for p in data['panels']:
        is_active = p.id in allowed
        mark = "✅" if is_active else "❌"
        action = "disable" if is_active else "enable"
        flag = cat_map.get(p.category, "🏳️")
        
        # ردیف پنل
        header = f"{flag} {p.name} ({p.panel_type})"
        kb.add(types.InlineKeyboardButton(header, callback_data="noop"))
        
        # دکمه‌های کنترلی (سرور اصلی + نودها)
        btns = [types.InlineKeyboardButton(f"سرور اصلی {mark}", callback_data=f"admin:ptgl:{data['uuid_obj'].id}:{p.id}:{action}")]
        for n in nodes_map.get(p.id, []):
            n_flag = cat_map.get(n.country_code, "🏳️")
            btns.append(types.InlineKeyboardButton(f"{n_flag} {mark}", callback_data=f"admin:ptgl:{data['uuid_obj'].id}:{p.id}:{action}"))
        kb.row(*btns)
        
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{data['uuid_obj'].user_id}"))
    
    text = (
        f"⚙️ *مدیریت دسترسی سرورها*\n"
        f"👤 کانفیگ: `{escape_markdown(data['uuid_obj'].name)}`\n\n"
        "برای قطع یا وصل دسترسی، روی دکمه‌ها کلیک کنید."
    )
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@admin_only
async def handle_user_access_toggle(call: types.CallbackQuery, params: list):
    """تغییر دسترسی"""
    uuid_db_id, panel_id, action = int(params[0]), int(params[1]), params[2]
    enable = (action == 'enable')
    
    if await admin_user_service.toggle_node_access(uuid_db_id, panel_id, enable):
        await bot.answer_callback_query(call.id, "✅ انجام شد.")
    else:
        await bot.answer_callback_query(call.id, "❌ خطا.")
        
    # رفرش کردن لیست (چون ID کاربر را نداریم، اینجا هندل نمی‌شود، کاربر باید دستی رفرش کند یا ما ID را پاس بدهیم)
    # برای سادگی فقط پیام می‌دهیم

# ==============================================================================
# 2. ریست‌ها و ابزارها (Reset & Tools)
# ==============================================================================

@admin_only
async def handle_user_reset_menu(call: types.CallbackQuery, params: list):
    """منوی عملیات ریست"""
    target_id = params[0]
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("📱 حذف دستگاه‌های متصل", callback_data=f"admin:us_ddev:{target_id}"),
        types.InlineKeyboardButton("🎂 حذف تاریخ تولد", callback_data=f"admin:us_rb:{target_id}"),
        types.InlineKeyboardButton("⏳ ریست محدودیت انتقال", callback_data=f"admin:us_rtr:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(call.from_user.id, call.message.message_id, "♻️ عملیات ویژه:", reply_markup=kb)

@admin_only
async def handle_reset_usage_action(call: types.CallbackQuery, params: list):
    """ریست حجم مصرفی"""
    target_id = int(params[1])
    uuids = await db.uuids(target_id)
    if uuids:
        await bot.answer_callback_query(call.id, "⏳ در حال ریست...")
        try:
            await combined_handler.reset_user_usage(str(uuids[0]['uuid']))
            await bot.answer_callback_query(call.id, "✅ مصرف ریست شد.")
        except:
            await bot.answer_callback_query(call.id, "❌ خطا در عملیات.")
    else:
        await bot.answer_callback_query(call.id, "❌ کاربر یافت نشد.")

@admin_only
async def handle_delete_devices_action(call: types.CallbackQuery, params: list):
    """حذف دستگاه‌های متصل"""
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_user_agents_by_uuid_id(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ دستگاه‌ها پاک شدند.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ دستگاه‌ها با موفقیت حذف شدند.", 
                     reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

@admin_only
async def handle_reset_birthday(call: types.CallbackQuery, params: list):
    target_id = int(params[0])
    await db.reset_user_birthday(target_id)
    await bot.answer_callback_query(call.id, "✅ انجام شد.")

@admin_only
async def handle_reset_transfer_cooldown(call: types.CallbackQuery, params: list):
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_transfer_history(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ انجام شد.")

# ==============================================================================
# 3. هشدارها (Warnings)
# ==============================================================================

@admin_only
async def handle_user_warning_menu(call: types.CallbackQuery, params: list):
    """منوی ارسال هشدار"""
    target_id = params[0]
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔔 یادآوری پرداخت", callback_data=f"admin:us_spn:{target_id}"),
        types.InlineKeyboardButton("🚨 هشدار قطع سرویس", callback_data=f"admin:us_sdw:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ ارسال هشدار:", reply_markup=kb)

@admin_only
async def handle_send_payment_reminder(call: types.CallbackQuery, params: list):
    target_id = int(params[0])
    try:
        await bot.send_message(target_id, "🔔 یادآوری: لطفاً نسبت به تمدید سرویس خود اقدام کنید.")
        await bot.answer_callback_query(call.id, "✅ ارسال شد.")
    except:
        await bot.answer_callback_query(call.id, "❌ کاربر ربات را بلاک کرده است.")

@admin_only
async def handle_send_disconnection_warning(call: types.CallbackQuery, params: list):
    target_id = int(params[0])
    try:
        await bot.send_message(target_id, "🚨 هشدار: سرویس شما به زودی قطع خواهد شد.")
        await bot.answer_callback_query(call.id, "✅ ارسال شد.")
    except:
        await bot.answer_callback_query(call.id, "❌ ارسال ناموفق.")