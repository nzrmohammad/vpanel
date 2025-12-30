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
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 ریست حجم مصرفی", callback_data=f"admin:us_rusg:{target_id}"),
        types.InlineKeyboardButton("🎂 حذف تاریخ تولد", callback_data=f"admin:us_rb:{target_id}"),
        types.InlineKeyboardButton("⏳ ریست محدودیت انتقال", callback_data=f"admin:us_rtr:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
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

async def handle_reset_transfer_cooldown(call, params):
    target_id = int(params[0])
    uuids = await db.uuids(target_id)
    if uuids:
        await db.delete_transfer_history(uuids[0]['id'])
        await bot.answer_callback_query(call.id, "✅ محدودیت انتقال ریست شد.")
    else:
        await bot.answer_callback_query(call.id, "سرویسی یافت نشد.")
    await handle_user_reset_menu(call, params)

# --- Warnings ---
async def handle_user_warning_menu(call, params):
    target_id = params[0]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔔 یادآوری پرداخت", callback_data=f"admin:us_spn:{target_id}"),
        types.InlineKeyboardButton("🚨 هشدار قطع سرویس", callback_data=f"admin:us_sdw:{target_id}")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:us:{target_id}"))
    await _safe_edit(uid, msg_id, "⚠️ ارسال هشدار:", reply_markup=kb)

async def handle_send_payment_reminder(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    msg = get_string('payment_reminder_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا (شاید بلاک).", show_alert=True)

async def handle_send_disconnection_warning(call, params):
    target_id = int(params[0])
    from bot.language import get_string
    user = await db.user(target_id)
    lang = user.get('lang_code', 'fa')
    msg = get_string('disconnection_warning_message', lang)
    try:
        await bot.send_message(target_id, msg)
        await bot.answer_callback_query(call.id, "✅ ارسال شد.", show_alert=True)
    except:
        await bot.answer_callback_query(call.id, "❌ خطا.", show_alert=True)

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

async def handle_renew_apply_plan(call, params):
    plan_id, target_id = int(params[0]), int(params[1])
    uid, msg_id = call.from_user.id, call.message.message_id
    
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    uuids = await db.uuids(target_id)
    if not uuids: return
    
    await _safe_edit(uid, msg_id, "⏳ در حال تمدید...", reply_markup=None)
    success = await combined_handler.modify_user_on_all_panels(
        identifier=str(uuids[0]['uuid']),
        add_gb=plan['volume_gb'],
        add_days=plan['days']
    )
    
    if success:
        await db.add_payment_record(uuids[0]['id'])
        await _safe_edit(uid, msg_id, f"✅ تمدید شد.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))
    else:
        await _safe_edit(uid, msg_id, "❌ خطا در تمدید.", 
                         reply_markup=await admin_menu.user_interactive_menu(str(target_id), True, 'both'))

# --- Badges & Achievements ---
async def handle_award_badge_menu(call, params):
    target_id = params[0]
    markup = await admin_menu.award_badge_menu(target_id, "")
    await _safe_edit(call.from_user.id, call.message.message_id, "🏅 انتخاب نشان:", reply_markup=markup)

async def handle_award_badge(call, params):
    badge_code, target_id = params[0], int(params[1])
    if await db.add_achievement(target_id, badge_code):
        await bot.answer_callback_query(call.id, "✅ اهدا شد.")
    else:
        await bot.answer_callback_query(call.id, "قبلاً داشته است.")
    await handle_award_badge_menu(call, [str(target_id)])

async def handle_achievement_request_callback(call, params):
    action = call.data.split(':')[1]
    req_id = int(params[0])
    status = 'approved' if 'approve' in action else 'rejected'
    await db.update_achievement_request_status(req_id, status, call.from_user.id)
    req = await db.get_achievement_request(req_id)
    if req and status == 'approved':
        await db.add_achievement(req['user_id'], req['badge_code'])
        await db.add_achievement_points(req['user_id'], 50)
        try: await bot.send_message(req['user_id'], "✅ درخواست نشان تایید شد!")
        except: pass
    await bot.edit_message_caption(f"{call.message.caption}\n\nوضعیت: {status}", call.from_user.id, call.message.message_id)

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