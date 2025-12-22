# bot/admin_handlers/group_actions.py

import asyncio
import logging
from telebot import types

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.services.panels import PanelFactory
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# استیت برای ذخیره مراحل مکالمه ادمین
admin_conversations = {}

def initialize_group_actions_handlers(b, conv_dict):
    """دریافت مقادیر سراسری از فایل اصلی"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. منوها و انتخاب‌های اولیه
# ==============================================================================

async def handle_select_plan_for_action(call: types.CallbackQuery, params: list):
    """نمایش لیست پلن‌ها برای انتخاب هدف عملیات گروهی."""
    plans = await db.get_all_plans(active_only=True)
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "👥 *عملیات گروهی*\n\nلطفاً **پلن مورد نظر** را انتخاب کنید (عملیات روی تمام کاربران این پلن انجام می‌شود):",
        reply_markup=await admin_menu.select_plan_for_group_action(plans),
        parse_mode="Markdown"
    )

async def handle_select_action_type(call: types.CallbackQuery, params: list):
    """انتخاب نوع عملیات (تمدید روز، حجم، حذف و ...)."""
    uid = call.from_user.id
    plan_id = params[0] # می‌تواند 'all' یا عدد باشد
    
    # ذخیره پلن انتخاب شده
    if uid not in admin_conversations:
        admin_conversations[uid] = {}
    admin_conversations[uid]['target_plan_id'] = int(plan_id) if plan_id != 'all' else 'all'
    
    # منوی انتخاب نوع عملیات
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⏳ افزایش روز (تمدید)", callback_data="admin:ga_type:add_days"),
        types.InlineKeyboardButton("📦 افزایش حجم (گیگابایت)", callback_data="admin:ga_type:add_gb"),
        # types.InlineKeyboardButton("🗑 حذف کاربران (خطرناک)", callback_data="admin:ga_type:delete"), # فعلاً غیرفعال برای امنیت
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:group_actions")
    )
    
    await _safe_edit(
        uid,
        call.message.message_id,
        "⚙️ *نوع عملیات را انتخاب کنید:*",
        reply_markup=kb,
        parse_mode="Markdown"
    )

async def handle_get_action_value(call: types.CallbackQuery, params: list):
    """دریافت مقدار (تعداد روز یا گیگابایت)."""
    uid, msg_id = call.from_user.id, call.message.message_id
    action_type = params[0]
    
    if uid not in admin_conversations:
        await bot.answer_callback_query(call.id, "نشست منقضی شد.")
        return

    admin_conversations[uid]['action_type'] = action_type
    admin_conversations[uid]['step'] = 'get_ga_value'
    admin_conversations[uid]['msg_id'] = msg_id
    admin_conversations[uid]['next_handler'] = process_action_value_input
    
    unit = "روز" if action_type == 'add_days' else "گیگابایت"
    prompt = (
        f"🔢 لطفاً مقدار **{unit}** را وارد کنید:\n\n"
        f"_(مثلاً برای افزودن 10 {unit}، عدد 10 را ارسال کنید)_"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 انصراف", callback_data="admin:main"))
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="Markdown")

async def process_action_value_input(message: types.Message):
    """پردازش مقدار وارد شده توسط ادمین."""
    uid = message.from_user.id
    text = message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    if not text.isdigit() and not text.replace('.', '', 1).isdigit():
        msg = await bot.send_message(message.chat.id, "❌ لطفاً فقط عدد وارد کنید.")
        await asyncio.sleep(2)
        await _delete_user_message(msg)
        return

    admin_conversations[uid]['action_value'] = float(text)
    
    # نمایش تاییدیه نهایی
    await handle_confirm_group_action(uid)

async def handle_confirm_group_action(uid):
    """نمایش خلاصه عملیات و دکمه تایید نهایی."""
    data = admin_conversations.get(uid)
    if not data: return
    
    plan_id = data.get('target_plan_id')
    action = data.get('action_type')
    value = data.get('action_value')
    msg_id = data.get('msg_id')
    
    plan_name = "همه کاربران"
    if plan_id != 'all':
        plan = await db.get_plan_by_id(plan_id)
        if plan: plan_name = plan['name']
        
    action_str = "افزایش اعتبار زمانی" if action == 'add_days' else "افزایش حجم"
    unit = "روز" if action == 'add_days' else "GB"
    
    text = (
        f"⚠️ *تایید عملیات گروهی*\n\n"
        f"👥 گروه هدف: `{plan_name}`\n"
        f"⚙️ عملیات: `{action_str}`\n"
        f"🔢 مقدار: `{value} {unit}`\n\n"
        f"آیا از انجام این عملیات اطمینان دارید؟"
    )
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ بله، انجام شود", callback_data="admin:ga_exec"),
        types.InlineKeyboardButton("❌ لغو", callback_data="admin:main")
    )
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")

# ==============================================================================
# 2. اجرای عملیات (بهینه شده و همزمان)
# ==============================================================================

async def handle_start_group_action_execution(call: types.CallbackQuery, params: list):
    """
    اجرای نهایی عملیات به صورت همزمان (Concurrent).
    🚀 سرعت بالا + مدیریت خطا
    """
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    if uid not in admin_conversations:
        await bot.answer_callback_query(call.id, "نشست منقضی شده است.")
        return

    data = admin_conversations.pop(uid)
    plan_id = data.get('target_plan_id')
    action = data.get('action_type')
    value = data.get('action_value')

    await _safe_edit(uid, msg_id, "🚀 *عملیات گروهی آغاز شد...*\nلطفاً تا پایان عملیات صبر کنید (این فرآیند همزمان انجام می‌شود).", parse_mode="Markdown")

    # 1. دریافت کاربران هدف
    if plan_id == 'all':
        users = await db.get_all_users_with_panels() # باید متدی باشد که آبجکت‌های UserUUID را برگرداند
    else:
        users = await db.get_users_by_plan(plan_id)

    if not users:
        await _safe_edit(uid, msg_id, "❌ کاربری برای این عملیات یافت نشد.", reply_markup=await admin_menu.main_menu())
        return

    total_count = len(users)
    
    # 2. تنظیمات همزمانی (جلوگیری از DDOS شدن سرورهای خودی)
    # حداکثر 20 درخواست همزمان به پنل‌ها
    sem = asyncio.Semaphore(20)

    # --- تابع داخلی پردازش تکی ---
    async def process_single_user(user_obj):
        async with sem: # ورود به صف محدود شده
            user_success = False
            # دریافت پنل‌های کاربر
            # فرض بر این است که user_obj ویژگی allowed_panels دارد (lazy load شده یا join شده)
            panels_to_update = user_obj.allowed_panels if hasattr(user_obj, 'allowed_panels') else []
            
            if not panels_to_update:
                return False

            for panel_db in panels_to_update:
                try:
                    # دریافت هندلر پنل
                    panel_api = await PanelFactory.get_panel(panel_db.name)
                    if not panel_api: continue

                    identifier = user_obj.uuid
                    
                    # لاجیک خاص مرزبان (تبدیل UUID به Username در صورت نیاز)
                    if panel_db.panel_type == 'marzban':
                        mapping = await db.get_marzban_username_by_uuid(user_obj.uuid)
                        identifier = mapping if mapping else user_obj.uuid 
                        # فال‌بک: اگر نگاشت نبود، شاید خود یوزرنیم ذخیره شده باشد یا UUID کار کند

                    # اعمال تغییرات
                    if action == 'add_gb':
                        if await panel_api.modify_user(identifier, add_gb=float(value)):
                            user_success = True
                    elif action == 'add_days':
                        if await panel_api.modify_user(identifier, add_days=int(value)):
                             user_success = True
                    # elif action == 'delete': ...
                    
                except Exception as e:
                    logger.error(f"Group Action Error for user {user_obj.id} on {panel_db.name}: {e}")
            
            return user_success

    # 3. ایجاد و اجرای تسک‌ها
    tasks = [process_single_user(u) for u in users]
    
    # دریافت نتایج
    results = await asyncio.gather(*tasks)

    success_count = results.count(True)
    fail_count = results.count(False)

    report = (
        f"✅ *پایان عملیات گروهی*\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"👥 کل کاربران هدف: `{total_count}`\n"
        f"✅ موفق: `{success_count}`\n"
        f"❌ ناموفق: `{fail_count}`\n\n"
        f"⚠️ _نکته: موارد ناموفق ممکن است مربوط به کاربرانی باشند که در هیچ پنلی فعال نبودند._"
    )
    
    await _safe_edit(uid, msg_id, report, reply_markup=await admin_menu.main_menu(), parse_mode="Markdown")