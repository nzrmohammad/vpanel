# bot/admin_handlers/user_management/actions.py

import time
import logging
from telebot import types

from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot import combined_handler
from bot.services.panels import PanelFactory

# ایمپورت‌های ماژولار
from bot.bot_instance import bot  # ایمپورت بات اصلی
from bot.admin_handlers.user_management import state  # ایمپورت ماژول state
from bot.admin_handlers.user_management.helpers import _delete_user_message
from bot.admin_handlers.user_management.profile import show_user_summary

logger = logging.getLogger(__name__)

# --- Reset Menus ---
async def handle_user_reset_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("🎂 حذف تاریخ تولد", callback_data=f"admin:us_rb:{target_id}")
    )
    kb.row(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
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


# --- Warnings ---
async def handle_user_warning_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🚨 هشدار نهایی", callback_data=f"admin:us_sdw:{target_id}"),
        types.InlineKeyboardButton("🔔 هشدار اولیه", callback_data=f"admin:us_spn:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, "⚠️ ارسال هشدار:", reply_markup=kb)

# --- تابع مشترک برای ارسال هشدار (جلوگیری از تکرار کد) ---
async def _send_warning_generic(call, target_id, message_key, success_message):
    """این تابع کار اصلی ارسال پیام و مدیریت خطا را انجام می‌دهد"""
    from bot.language import get_string
    
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    msg_text = get_string(message_key, lang)
    
    try:
        # 1. ارسال پیام به کاربر
        await bot.send_message(target_id, msg_text)
        # 2. بستن لودینگ دکمه شیشه‌ای
        await bot.answer_callback_query(call.id)
        
        await show_user_summary(
            call.from_user.id, 
            call.message.message_id, 
            target_id, 
            extra_message=success_message
        )
    except Exception as e:
        logger.error(f"Failed to send warning ({message_key}): {e}")
        await bot.answer_callback_query(call.id, "❌ خطا در ارسال (شاید کاربر ربات را بلاک کرده است).", show_alert=True)

# --- هندلرها (فقط تابع مشترک را صدا می‌زنند) ---

async def handle_send_payment_reminder(call, params):
    """دکمه هشدار اولیه"""
    await _send_warning_generic(
        call, 
        int(params[0]), 
        'payment_reminder_message', 
        r"✅ هشدار اولیه یادآوری عدم پرداخت با موفقیت ارسال شد\." 
    )

async def handle_send_disconnection_warning(call, params):
    """دکمه هشدار نهایی"""
    await _send_warning_generic(
        call, 
        int(params[0]), 
        'disconnection_warning_message', 
        r"✅ هشدار نهایی یادآوری عدم پرداخت با موفقیت ارسال شد\." 
    )

# --- Notes ---
async def handle_ask_for_note(call, params):
    target_id = params[0]
    context_code = params[1] if len(params) > 1 else None
    uid, msg_id = call.from_user.id, call.message.message_id
    
    state.admin_conversations[uid] = {
        'step': 'save_note', 
        'msg_id': msg_id, 
        'target_id': int(target_id),
        'context': context_code,
        'timestamp': time.time(),
        'next_handler': process_save_note
    }
    
    prompt = r"📝 یادداشت خود را بنویسید \(برای حذف، *پاک* بفرستید\):"
    await _safe_edit(uid, msg_id, prompt,
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}:{context_code}"),
                     parse_mode="MarkdownV2")

async def process_save_note(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in state.admin_conversations: return
    data = state.admin_conversations.pop(uid)
    target_id = data['target_id']
    msg_id = data['msg_id']
    context_code = data.get('context')
    
    note_val = None if text == 'پاک' else text
    await db.update_user_note(target_id, note_val)
    
    status_msg = r"🗑 *یادداشت حذف شد\.*" if text == 'پاک' else r"✅ *یادداشت ذخیره شد\.*"
    await show_user_summary(uid, msg_id, target_id, context=context_code, extra_message=status_msg)

# --- Delete User ---
async def handle_delete_user_confirm(call, params):
    target_id = params[0]
    markup = await admin_menu.confirm_delete(target_id, 'both')
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

# --- Delete Devices ---
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

# --- Renew Subscription ---
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


# ==============================================================================
# بخش تمدید اشتراک (Renew Subscription) - اصلاح شده
# ==============================================================================

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
    """
    مرحله ۱: نمایش پیش‌نمایش دقیق با فیلتر پنل‌های هدف
    """
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    uuids = await db.uuids(target_id)
    if not uuids: return
    
    uuid_str = str(uuids[0]['uuid'])
    user_info = await combined_handler.get_combined_user_info(uuid_str)
    
    # اگر اطلاعات کاربر یافت نشد (مشکل Aggregator)
    if not user_info:
        await _safe_edit(uid, msg_id, "❌ اطلاعات کاربر از پنل‌ها دریافت نشد (خطا در ارتباط یا یافت نشد).", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
        return

    # استخراج پنل‌ها
    all_active_panels = await db.get_active_panels()
    panel_cat_map = {p['name']: p.get('category') for p in all_active_panels}
    
    user_panels_names = set()
    target_panels_names = set()
    
    raw_panels = user_info.get('panels', [])
    allowed_cats = plan.get('allowed_categories', [])
    
    for p in raw_panels:
        p_name = p.get('name', 'Unknown') if isinstance(p, dict) else str(p)
        user_panels_names.add(p_name)
        p_cat = panel_cat_map.get(p_name)
        if not allowed_cats or (p_cat in allowed_cats):
            target_panels_names.add(p_name)
            
    sorted_all = sorted(list(user_panels_names))
    sorted_target = sorted(list(target_panels_names))

    str_all_panels = ", ".join(sorted_all) if sorted_all else "---"
    str_target_panels = ", ".join(sorted_target) if sorted_target else "❌ هیچکدام (هشدار)"

    # محاسبات حجم
    old_gb = 0.0
    breakdown = user_info.get('breakdown', {})
    
    if breakdown:
        for p_name in sorted_target:
            if p_name in breakdown:
                panel_limit = breakdown[p_name].get('data', {}).get('usage_limit_GB', 0)
                old_gb += panel_limit
    else:
        old_gb = round(user_info.get('usage_limit_GB', 0), 2)

    old_gb = round(old_gb, 2)
    expire_date_ts = user_info.get('expire', 0)

    # محاسبه تغییرات
    add_gb = plan['volume_gb']
    count_targets = len(target_panels_names)
    added_total_gb = add_gb * count_targets if count_targets > 0 else add_gb
    new_gb_total = round(old_gb + added_total_gb, 2)

    import time
    now_ts = int(time.time())
    
    remaining_days = 0
    if expire_date_ts and expire_date_ts > 1600000000 and expire_date_ts > now_ts:
        remaining_days = int((expire_date_ts - now_ts) / 86400)
    
    add_days = plan['days']
    new_days = remaining_days + add_days
    price = plan['price']

    # --- ایمن‌سازی متغیرها برای MarkdownV2 (رفع باگ نقطه و کاراکترهای خاص) ---
    safe_all_panels = escape_markdown(str_all_panels)
    safe_target_panels = escape_markdown(str_target_panels)
    safe_plan_name = escape_markdown(plan['name'])
    
    safe_add_gb = escape_markdown(str(add_gb))
    safe_old_gb = escape_markdown(str(old_gb))
    safe_added_total_gb = escape_markdown(str(added_total_gb))
    safe_new_gb_total = escape_markdown(str(new_gb_total))
    safe_price = escape_markdown(f"{price:,.0f}")
    
    safe_add_days = str(add_days)
    safe_remaining_days = str(remaining_days)
    safe_new_days = str(new_days)

    msg_final = (
        f"🔄 پیش‌نمایش تمدید سرویس\n"
        f"پنل‌های کاربر : {safe_all_panels}\n"
        f"✅ *اعمال به :* {safe_target_panels}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🏷 پلن انتخابی\n"
        f"{safe_plan_name}\n"
        f"📊 {safe_add_gb} GB\n"
        f"⏳ {safe_add_days} Day\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"📦 تغییرات حجم \(پنل‌های هدف\)\n"
        f"{safe_old_gb}GB ➔ \+{safe_added_total_gb} GB ➔ {safe_new_gb_total} GB\n"
        f"⏳ تغییرات زمان\n"
        f"{safe_remaining_days} ➔ \+{safe_add_days} ➔ {safe_new_days}\n"
        f"➖➖➖➖➖\n"
        f"💰 مبلغ قابل پرداخت : {safe_price} تومان\n"
        f"❓ آیا عملیات تایید است؟"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ تایید نهایی", callback_data=f"admin:renew_exec:{plan_id}:{target_id}"),
        types.InlineKeyboardButton("❌ انصراف", callback_data=f"admin:us:{target_id}")
    )
    
    await _safe_edit(uid, msg_id, msg_final, reply_markup=kb, parse_mode="MarkdownV2")

async def handle_renew_confirm_exec(call, params):
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    await _safe_edit(uid, msg_id, escape_markdown("⏳ در حال انجام عملیات..."), reply_markup=None)
    
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    uuids = await db.uuids(target_id)
    if not uuids: return
    
    allowed_cats = plan.get('allowed_categories', [])
    success = await combined_handler.modify_user_on_all_panels(
        identifier=str(uuids[0]['uuid']),
        add_gb=plan['volume_gb'],
        add_days=plan['days'],
        limit_categories=allowed_cats
    )
    
    if success:
        await db.add_payment_record(uuids[0]['id'])
        try:
            user_msg = (
                f"✅ کاربر گرامی، سرویس شما با موفقیت تمدید شد.\n\n"
                f"📦 حجم اضافه شده: {plan['volume_gb']} گیگابایت\n"
                f"⏳ زمان اضافه شده: {plan['days']} روز\n\n"
                f"از همراهی شما سپاسگزاریم. 🌹"
            )
            await bot.send_message(target_id, user_msg)
        except Exception as e:
            logger.error(f"Failed to send renewal notification to user {target_id}: {e}")

        success_msg = escape_markdown("✅ سرویس تمدید شد و پیام فعال‌سازی برای کاربر ارسال گردید.")
        await show_user_summary(uid, msg_id, target_id, extra_message=success_msg)
    else:
        error_msg = escape_markdown("❌ خطا در انجام عملیات تمدید.")
        await _safe_edit(uid, msg_id, error_msg, 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

        
# --- Churn / Contact ---
async def handle_churn_contact_user(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    state.admin_conversations[uid] = {
        'step': 'send_msg_to_user',
        'target_id': int(target_id),
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_send_msg_to_user
    }
    await _safe_edit(uid, msg_id, "📝 لطفاً پیام خود را برای ارسال به کاربر بنویسید:", 
                     reply_markup=await admin_menu.cancel_action(f"admin:us:{target_id}"))

async def process_send_msg_to_user(message: types.Message):
    uid, text = message.from_user.id, message.text
    await _delete_user_message(message)
    
    if uid not in state.admin_conversations: return
    data = state.admin_conversations.pop(uid)
    target_id = data['target_id']
    msg_id = data['msg_id']
    
    try:
        await bot.send_message(target_id, f"📩 پیام از پشتیبانی:\n\n{text}")
        await _safe_edit(uid, msg_id, "✅ پیام شما با موفقیت برای کاربر ارسال شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'hiddify'))
    except Exception as e:
        logger.error(f"Error sending msg to user {target_id}: {e}")
        await _safe_edit(uid, msg_id, "❌ ارسال ناموفق (ممکن است ربات بلاک شده باشد).", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'hiddify'))

async def handle_churn_send_offer(call, params):
    await manual_winback_handler(call, params)

async def manual_winback_handler(call, params):
    target_id = int(params[0])
    msg = "👋 سلام! دلمون برات تنگ شده. 🌹\nخیلی وقته سری به ما نزدی. یه کد تخفیف ویژه برات داریم:\n🎁 Code: `WELCOME_BACK`"
    try:
        await bot.send_message(target_id, msg, parse_mode="Markdown")
        await bot.answer_callback_query(call.id, "✅ پیام ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ ارسال ناموفق.", show_alert=True)