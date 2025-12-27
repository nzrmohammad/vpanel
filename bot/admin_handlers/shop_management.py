import logging
import time
from telebot import types
from bot.database import db
from bot.keyboards import admin as admin_kb
from bot.utils.network import _safe_edit

logger = logging.getLogger(__name__)

# متغیرهای سراسری برای نگهداری وضعیت و نمونه ربات
bot = None
admin_conversations = {}

def initialize_shop_management_handlers(bot_instance, state_dict):
    """
    این تابع توسط admin_router صدا زده می‌شود تا وضعیت‌ها یکپارچه شوند.
    """
    global bot, admin_conversations
    bot = bot_instance
    admin_conversations = state_dict

async def _delete_user_message(msg: types.Message):
    """پیام کاربر را برای تمیز ماندن چت حذف می‌کند."""
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception:
        pass

async def handle_shop_callbacks(call: types.CallbackQuery, params: list):
    """مدیریت دکمه‌های منوی فروشگاه"""
    sub_action = params[0] if params else "main"

    if sub_action == "main":
        await open_shop_management(call)
    elif sub_action == "detail":
        await show_shop_item_details(call, params)
    elif sub_action == "toggle":
        await toggle_shop_item_status(call, params)
    elif sub_action == "del":
        await delete_shop_item(call, params)
    elif sub_action == "add":
        await start_add_product(call)
    elif sub_action == "cancel":
        await cancel_shop_creation(call)

# ============================================================================
# 1. مدیریت نمایش و لیست محصولات
# ============================================================================

async def open_shop_management(call: types.CallbackQuery):
    """نمایش لیست محصولات"""
    uid, msg_id = call.from_user.id, call.message.message_id
    try:
        addons = await db.get_all_addons(active_only=False)
        markup = await admin_kb.shop_management_menu(addons)
        
        text = (
            "🏪 **مدیریت فروشگاه امتیاز**\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "لیست بسته‌های قابل خرید برای کاربران:\n\n"
            "🟢 = فعال (قابل خرید)\n"
            "🔴 = غیرفعال (مخفی)\n\n"
            "👇 __برای مدیریت هر محصول روی نام آن کلیک کنید.__"
        )
        
        await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error opening shop: {e}")
        await bot.answer_callback_query(call.id, "خطا در بارگذاری.")

async def show_shop_item_details(call: types.CallbackQuery, params: list):
    """نمایش جزئیات یک محصول"""
    uid, msg_id = call.from_user.id, call.message.message_id
    try:
        addon_id = int(params[1])
        addon = await db.get_addon_by_id(addon_id)
        
        if not addon:
            await bot.answer_callback_query(call.id, "❌ محصول یافت نشد.")
            await open_shop_management(call)
            return

        status_icon = "✅ فعال" if addon['is_active'] else "❌ غیرفعال"
        
        text = (
            f"📦 **مدیریت محصول**\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"🏷 **نام:** `{addon['name']}`\n"
            f"💎 **قیمت:** `{int(addon['price']):,}` امتیاز\n"
            f"📥 **حجم:** `{addon['extra_gb']}` گیگابایت\n"
            f"📅 **زمان:** `{addon['extra_days']}` روز\n\n"
            f"📡 **وضعیت:** {status_icon}"
        )
        
        markup = await admin_kb.shop_item_detail_menu(addon)
        await _safe_edit(uid, msg_id, text, reply_markup=markup, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error showing details: {e}")

# ============================================================================
# 2. عملیات (تغییر وضعیت / حذف)
# ============================================================================

async def toggle_shop_item_status(call: types.CallbackQuery, params: list):
    try:
        addon_id = int(params[1])
        addon = await db.get_addon_by_id(addon_id)
        if addon:
            new_status = not addon['is_active']
            await db.update_addon_status(addon_id, new_status)
            msg = "فعال شد 🟢" if new_status else "غیرفعال شد 🔴"
            await bot.answer_callback_query(call.id, msg)
            await show_shop_item_details(call, params)
    except Exception as e:
        logger.error(f"Error toggle: {e}")

async def delete_shop_item(call: types.CallbackQuery, params: list):
    try:
        addon_id = int(params[1])
        if await db.delete_addon(addon_id):
            await bot.answer_callback_query(call.id, "🗑 محصول حذف شد.")
            await open_shop_management(call)
        else:
            await bot.answer_callback_query(call.id, "خطا در حذف.")
    except Exception as e:
        logger.error(f"Error delete: {e}")

# ============================================================================
# 3. پروسه افزودن محصول (State-Based)
# ============================================================================

async def start_add_product(call: types.CallbackQuery):
    """شروع پروسه افزودن محصول"""
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # تنظیم وضعیت در دیکشنری اصلی ربات
    admin_conversations[uid] = {
        'step': 'shop_add_name',
        'msg_id': msg_id,
        'new_shop_data': {},
        'timestamp': time.time(),
        'next_handler': get_shop_add_name  # اشاره‌گر به تابع مرحله بعد
    }
    
    text = (
        "🛍 **افزودن محصول جدید** (مرحله 1/4)\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "1️⃣ **نام محصول** را وارد کنید:\n"
        "_(مثال: 10 گیگابایت - یک ماهه)_"
    )
    
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_kb.shop_cancel_menu(), parse_mode="Markdown")

async def cancel_shop_creation(call: types.CallbackQuery):
    """انصراف از ساخت"""
    uid = call.from_user.id
    if uid in admin_conversations:
        del admin_conversations[uid]
    
    await bot.answer_callback_query(call.id, "عملیات لغو شد.")
    await open_shop_management(call)

# --- هندلرهای مراحل (Step Handlers) ---

async def get_shop_add_name(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    name = message.text.strip()
    admin_conversations[uid]['new_shop_data']['name'] = name
    admin_conversations[uid]['step'] = 'shop_add_price'
    admin_conversations[uid]['next_handler'] = get_shop_add_price
    
    msg_id = admin_conversations[uid]['msg_id']
    text = (
        f"🛍 **افزودن محصول جدید** (مرحله 2/4)\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🏷 نام: **{name}**\n\n"
        f"2️⃣ **قیمت** را وارد کنید (تعداد امتیاز):\n"
        f"_(فقط عدد وارد کنید، مثلا: 500)_"
    )
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_kb.shop_cancel_menu(), parse_mode="Markdown")

async def get_shop_add_price(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        price = float(message.text.strip())
        admin_conversations[uid]['new_shop_data']['price'] = price
        admin_conversations[uid]['step'] = 'shop_add_gb'
        admin_conversations[uid]['next_handler'] = get_shop_add_gb
        
        msg_id = admin_conversations[uid]['msg_id']
        name = admin_conversations[uid]['new_shop_data']['name']
        
        text = (
            f"🛍 **افزودن محصول جدید** (مرحله 3/4)\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🏷 نام: **{name}**\n"
            f"💎 قیمت: `{int(price)}` امتیاز\n\n"
            f"3️⃣ **حجم اضافه (گیگابایت)** را وارد کنید:\n"
            f"_(اگر این بسته حجم ندارد، عدد 0 را بفرستید)_"
        )
        await _safe_edit(uid, msg_id, text, reply_markup=await admin_kb.shop_cancel_menu(), parse_mode="Markdown")
    except ValueError:
        # در صورت خطا در فرمت، پیامی ارسال نمی‌کنیم یا می‌توانیم یک نوتیفیکیشن موقت بدهیم
        pass

async def get_shop_add_gb(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        gb = float(message.text.strip())
        admin_conversations[uid]['new_shop_data']['gb'] = gb
        admin_conversations[uid]['step'] = 'shop_add_days'
        admin_conversations[uid]['next_handler'] = get_shop_add_days
        
        msg_id = admin_conversations[uid]['msg_id']
        data = admin_conversations[uid]['new_shop_data']
        
        text = (
            f"🛍 **افزودن محصول جدید** (مرحله 4/4)\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🏷 نام: **{data['name']}**\n"
            f"💎 قیمت: `{int(data['price'])}`\n"
            f"📥 حجم: `{gb}` GB\n\n"
            f"4️⃣ **تعداد روز اضافه** را وارد کنید:\n"
            f"_(اگر این بسته تمدید زمانی ندارد، عدد 0 را بفرستید)_"
        )
        await _safe_edit(uid, msg_id, text, reply_markup=await admin_kb.shop_cancel_menu(), parse_mode="Markdown")
    except ValueError:
        pass

async def get_shop_add_days(message: types.Message):
    uid = message.from_user.id
    if uid not in admin_conversations: return
    await _delete_user_message(message)
    
    try:
        days = int(message.text.strip())
        
        # دریافت داده‌ها و ذخیره نهایی
        data = admin_conversations.pop(uid) # پاک کردن استیت
        shop_data = data['new_shop_data']
        msg_id = data['msg_id']
        
        await db.add_addon(
            name=shop_data['name'],
            price=shop_data['price'],
            extra_gb=shop_data['gb'],
            extra_days=days
        )
        
        final_text = (
            "✅ **محصول با موفقیت ساخته شد!**\n"
            "➖➖➖➖➖➖➖➖➖➖\n\n"
            f"🏷 **{shop_data['name']}**\n"
            f"💎 قیمت: {int(shop_data['price']):,} امتیاز\n"
            f"📦 مشخصات: {shop_data['gb']} GB | {days} روز"
        )
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin:shop:main"))
        
        await _safe_edit(uid, msg_id, final_text, reply_markup=kb, parse_mode="Markdown")
        
    except ValueError:
        pass
    except Exception as e:
        logger.error(f"Error saving shop item: {e}")
        # اگر خطایی رخ داد، استیت را پاک می‌کنیم تا ادمین گیر نکند
        if uid in admin_conversations: del admin_conversations[uid]