# bot/admin_handlers/user_mgmt/create.py

import uuid as uuid_lib
import time
import random
import string
from telebot import types
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.utils.parsers import validate_uuid
from bot.utils.decorators import admin_only
from bot.services.admin.user_service import admin_user_service
from bot.services.admin.panel_service import panel_service
from bot.database import db
from bot.services.panels.factory import PanelFactory

# متغیرهای گلوبال ماژول
bot = None
admin_conversations = {}

def init(b, conv_dict):
    """مقداردهی اولیه متغیرهای ماژول"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. نقاط شروع (Entry Points)
# ==============================================================================

@admin_only
async def handle_add_user_menu(call: types.CallbackQuery, params: list):
    """منوی انتخاب پنل برای افزودن کاربر (متد جدید)"""
    # هدایت به متد اصلی انتخاب پنل
    await handle_add_user_select_panel(call)

@admin_only
async def handle_start_add_user(call: types.CallbackQuery, params: list):
    """متد قدیمی شروع ساخت کاربر (جهت سازگاری با کدهای قدیمی)"""
    # هدایت به متد اصلی
    await handle_add_user_select_panel(call)

@admin_only
async def handle_add_user_select_panel(call: types.CallbackQuery):
    """شروع پروسه افزودن: انتخاب پنل یا دریافت پنل از کال‌بک"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # فرمت دیتا: admin:add_user:panel_name
    parts = call.data.split(':')
    panel_name = parts[2] if len(parts) > 2 else "all"
    
    # شروع استیت مکالمه
    admin_conversations[uid] = {
        'action': 'add_user', 
        'step': 'get_name', 
        'msg_id': msg_id,
        'data': {'panel_name': panel_name}, 
        'next_handler': get_new_user_name,
        'timestamp': time.time()
    }
    
    msg = f"👤 سرور انتخابی: *{escape_markdown(panel_name)}*\n\nلطفاً **نام کاربر جدید** را وارد کنید:"
    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.cancel_action("admin:management_menu"))

# ==============================================================================
# 2. ویزارد دریافت اطلاعات (Wizard Steps)
# ==============================================================================

@admin_only
async def get_new_user_name(message: types.Message):
    """دریافت نام کاربر"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    admin_conversations[uid]['data']['name'] = text
    admin_conversations[uid]['step'] = 'get_uuid'
    admin_conversations[uid]['next_handler'] = get_new_user_uuid
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                     "🔑 لطفاً **UUID** را وارد کنید (یا `.` برای تولید خودکار):", 
                     reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_uuid(message: types.Message):
    """دریافت یا تولید UUID"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    if text == '.' or text.lower() == 'random':
        final_uuid = str(uuid_lib.uuid4())
    else:
        if not validate_uuid(text):
            await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                             "❌ فرمت UUID نامعتبر است. مجدد تلاش کنید:", 
                             reply_markup=await admin_menu.cancel_action())
            return
        final_uuid = text

    admin_conversations[uid]['data']['uuid'] = final_uuid
    admin_conversations[uid]['step'] = 'get_limit'
    admin_conversations[uid]['next_handler'] = get_new_user_limit
    
    await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                     "📦 **حجم محدودیت (GB)** را وارد کنید:\n(عدد `0` به معنی نامحدود)", 
                     reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_limit(message: types.Message):
    """دریافت محدودیت حجمی"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    try:
        val = float(text)
        if val < 0: raise ValueError
        admin_conversations[uid]['data']['limit'] = val
        
        admin_conversations[uid]['step'] = 'get_days'
        admin_conversations[uid]['next_handler'] = get_new_user_days
        
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "📅 **مدت اعتبار (روز)** را وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())
    except ValueError:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "❌ لطفاً یک عدد معتبر وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())

@admin_only
async def get_new_user_days(message: types.Message):
    """دریافت روز و پایان عملیات"""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    
    try:
        days = int(text)
        if days < 0: raise ValueError
        admin_conversations[uid]['data']['days'] = days
        
        # پایان ویزارد و ساخت کاربر
        await _finalize_user_creation(uid)
        
    except ValueError:
        await _safe_edit(uid, admin_conversations[uid]['msg_id'], 
                         "❌ لطفاً یک عدد صحیح وارد کنید:", 
                         reply_markup=await admin_menu.cancel_action())

async def _finalize_user_creation(uid):
    """ارسال درخواست نهایی به سرویس"""
    if uid not in admin_conversations: return
    
    data_pack = admin_conversations.pop(uid)
    user_data = data_pack['data']
    msg_id = data_pack['msg_id']
    
    await _safe_edit(uid, msg_id, "⏳ در حال ساخت کاربر در پنل‌ها...", reply_markup=None)
    
    # فراخوانی سرویس
    result = await admin_user_service.create_user(user_data)
    
    # نمایش گزارش
    final_uuid = result.get('uuid') or user_data.get('uuid')
    
    success_list = []
    # اصلاح بافر برای پنل‌های موفق (برای جلوگیری از ارور دیکشنری)
    if result.get('success'):
        for p in result.get('success'):
            if isinstance(p, dict) and 'name' in p:
                success_list.append(f"✅ {escape_markdown(p['name'])}")
            else:
                success_list.append(f"✅ {escape_markdown(str(p))}")

    fail_list = []
    if result.get('fail'):
        for p in result.get('fail'):
            if isinstance(p, dict) and 'name' in p:
                fail_list.append(f"❌ {escape_markdown(p['name'])}")
            else:
                fail_list.append(f"❌ {escape_markdown(str(p))}")
    
    limit_display = f"{user_data['limit']} GB"
    days_display = f"{user_data['days']} روز"

    report_text = (
        f"👤 کاربر جدید: `{escape_markdown(user_data['name'])}`\n"
        f"🔑 UUID: `{final_uuid}`\n"
        f"📦 حجم: `{limit_display}` | 📅 مدت: `{days_display}`\n"
        f"──────────────────\n"
    )
    
    if success_list: report_text += "\n".join(success_list) + "\n"
    if fail_list: report_text += "\n⚠️ ناموفق در:\n" + "\n".join(fail_list)
    if not success_list and fail_list: report_text += "\n🛑 عملیات در هیچ پنلی موفق نبود!"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به مدیریت", callback_data="admin:management_menu"))
    
    await _safe_edit(uid, msg_id, report_text, reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# 3. قابلیت‌های خاص (Remnawave Squads & Random User)
# ==============================================================================

@admin_only
async def handle_squad_callback(call: types.CallbackQuery, params: list):
    """هندلر انتخاب اسکواد داخلی (Remnawave)"""
    uid = call.from_user.id
    squad_id = params[0]
    
    if uid in admin_conversations:
        admin_conversations[uid]['data']['squad_uuid'] = squad_id
        await bot.answer_callback_query(call.id, "✅ اسکواد انتخاب شد.")
    else:
        await bot.answer_callback_query(call.id, "❌ نشست منقضی شده است.")

@admin_only
async def handle_external_squad_callback(call: types.CallbackQuery, params: list):
    """هندلر انتخاب اسکواد خارجی (Remnawave)"""
    uid = call.from_user.id
    ext_squad_id = params[0]
    
    if uid in admin_conversations:
        admin_conversations[uid]['data']['external_squad_uuid'] = ext_squad_id
        await bot.answer_callback_query(call.id, "✅ اسکواد خارجی انتخاب شد.")
    else:
        await bot.answer_callback_query(call.id, "❌ نشست منقضی شده است.")

@admin_only
async def handle_random_user_generation(call: types.CallbackQuery, params: list):
    """ساخت سریع کاربر رندوم (Quick Create)"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # تولید اطلاعات رندوم
    rand_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    name = f"User_{rand_suffix}"
    uuid_str = str(uuid_lib.uuid4())
    
    # تنظیمات پیش‌فرض (قابل تغییر در کانفیگ)
    default_limit = 0 # نامحدود
    default_days = 30
    
    # دیتای ساخت
    user_data = {
        'name': name,
        'uuid': uuid_str,
        'limit': default_limit,
        'days': default_days,
        'panel_name': 'all' # پیش‌فرض روی همه پنل‌ها
    }
    
    await _safe_edit(uid, msg_id, f"🎲 در حال ساخت کاربر رندوم:\n`{name}`...", reply_markup=None)
    
    # فراخوانی مستقیم سرویس
    result = await admin_user_service.create_user(user_data)
    
    # نمایش نتیجه کوتاه
    status = "✅ موفق" if result.get('success') else "❌ ناموفق"
    msg = (
        f"{status}\n"
        f"👤 {name}\n"
        f"🔑 `{uuid_str}`\n"
        f"📅 {default_days} روز"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:management_menu"))
    
    await _safe_edit(uid, msg_id, msg, reply_markup=kb, parse_mode="Markdown")

    # --- این کد را به انتهای فایل create.py اضافه کنید ---

@admin_only
async def handle_cancel_process(call: types.CallbackQuery, params: list):
    """لغو عملیات و بازگشت به منوی اصلی"""
    uid = call.from_user.id
    if uid in admin_conversations:
        del admin_conversations[uid]
    
    await bot.answer_callback_query(call.id, "❌ عملیات لغو شد.")
    
    # تلاش برای نمایش منوی اصلی مدیریت
    try:
        # ایمپورت داخلی برای جلوگیری از چرخه ایمپورت
        from .search import handle_management_menu
        await handle_management_menu(call, [])
    except Exception:
        # اگر مشکلی بود، فقط پیام را ویرایش کن
        await _safe_edit(uid, call.message.message_id, "❌ عملیات لغو شد.", reply_markup=None)

    # --- این بخش را به انتهای فایل create.py اضافه کنید ---

@admin_only
async def handle_add_user_to_panel_start(call: types.CallbackQuery, params: list):
    """
    شروع فرآیند افزودن کاربر به یک پنل خاص (از طریق منوی مدیریت پنل).
    """
    panel_id = int(params[0])
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    # دریافت اطلاعات پنل برای ذخیره در استیت و دکمه بازگشت
    panel = await db.get_panel_by_id(panel_id)
    if not panel:
        await bot.answer_callback_query(call.id, "❌ پنل یافت نشد.")
        return

    # تنظیم استیت برای دریافت نام
    admin_conversations[uid] = {
        'action': 'add_user',
        'step': 'get_name',
        'data': {'panel_name': panel['name']}, # نام پنل از اینجا خوانده می‌شود
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': get_new_user_name
    }
    
    # ساخت دکمه بازگشت به منوی همان پنل
    back_kb = types.InlineKeyboardMarkup()
    back_kb.add(types.InlineKeyboardButton(
        "🔙 بازگشت", 
        callback_data=f"admin:manage_single_panel:{panel['id']}:{panel['panel_type']}"
    ))
    
    text = f"👤 سرور انتخاب شد: *{escape_markdown(panel['name'])}*\n\nلطفاً *نام کاربر* جدید را وارد کنید:"
    
    await _safe_edit(uid, msg_id, text, reply_markup=back_kb)