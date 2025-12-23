# bot/admin_handlers/shop_management.py

import logging
from telebot import types
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import admin as admin_kb

# تنظیمات لاگ
logger = logging.getLogger(__name__)

# دیکشنری برای ذخیره وضعیت‌های مکالمه ساخت محصول
# Format: {admin_id: {'step': 'STEP_NAME', 'data': {...}, 'msg_id': 123}}
SHOP_CREATION_STATES = {}

async def handle_shop_callbacks(call: types.CallbackQuery, params: list):
    """
    توزیع‌کننده کال‌بک‌های مربوط به فروشگاه.
    فرمت: admin:shop:ACTION:ARGS...
    """
    sub_action = params[0] if params else "main"

    if sub_action == "main":
        await open_shop_management(call)
        
    elif sub_action == "detail":
        # نمایش صفحه جزئیات محصول (برای حذف یا تغییر وضعیت)
        await show_shop_item_details(call, params)
        
    elif sub_action == "toggle":
        # تغییر وضعیت فعال/غیرفعال
        await toggle_shop_item_status(call, params)
        
    elif sub_action == "del":
        # حذف محصول
        await delete_shop_item(call, params)
        
    elif sub_action == "add":
        # شروع افزودن محصول
        await start_add_product(call)
        
    elif sub_action == "cancel":
        # انصراف از افزودن
        await cancel_shop_creation(call)

# ============================================================================
# 1. مدیریت نمایش و لیست محصولات
# ============================================================================

async def open_shop_management(call: types.CallbackQuery):
    """نمایش لیست تمام محصولات فروشگاه"""
    try:
        # دریافت همه محصولات (فعال و غیرفعال)
        addons = await db.get_all_addons(active_only=False)
        
        # ساخت کیبورد لیست
        markup = await admin_kb.shop_management_menu(addons)
        
        text = (
            "🏪 **مدیریت فروشگاه امتیاز**\n\n"
            "لیست محصولات فعلی در زیر نمایش داده شده است.\n"
            "🟢 = فعال | 🔴 = غیرفعال\n\n"
            "💡 **برای ویرایش (فعال/غیرفعال) یا حذف، روی نام محصول کلیک کنید.**"
        )
        
        await bot.edit_message_text(
            text, 
            call.message.chat.id, 
            call.message.message_id, 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error opening shop management: {e}")
        await bot.answer_callback_query(call.id, "خطا در بارگذاری فروشگاه.")

async def show_shop_item_details(call: types.CallbackQuery, params: list):
    """نمایش صفحه جزئیات یک محصول خاص"""
    try:
        addon_id = int(params[1])
        addon = await db.get_addon_by_id(addon_id)
        
        if not addon:
            await bot.answer_callback_query(call.id, "❌ محصول یافت نشد.")
            await open_shop_management(call)
            return

        status_text = "فعال ✅" if addon['is_active'] else "غیرفعال ❌"
        
        text = (
            f"📦 **جزئیات محصول**\n\n"
            f"🏷 **نام:** `{addon['name']}`\n"
            f"💰 **قیمت:** `{int(addon['price']):,}` امتیاز\n"
            f"📊 **حجم اضافه:** `{addon['extra_gb']}` GB\n"
            f"⏳ **روز اضافه:** `{addon['extra_days']}` روز\n"
            f"📡 **وضعیت فعلی:** {status_text}\n\n"
            f"👇 عملیات مورد نظر را انتخاب کنید:"
        )
        
        # استفاده از کیبورد جزئیات (که دکمه‌های تغییر وضعیت و حذف دارد)
        markup = await admin_kb.shop_item_detail_menu(addon)
        
        await bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error showing details: {e}")
        await bot.answer_callback_query(call.id, "خطا در نمایش جزئیات.")

# ============================================================================
# 2. عملیات روی محصولات (تغییر وضعیت / حذف)
# ============================================================================

async def toggle_shop_item_status(call: types.CallbackQuery, params: list):
    """تغییر وضعیت (Active/Inactive)"""
    try:
        addon_id = int(params[1])
        addon = await db.get_addon_by_id(addon_id)
        
        if addon:
            new_status = not addon['is_active']
            await db.update_addon_status(addon_id, new_status)
            
            msg = "فعال شد ✅" if new_status else "غیرفعال شد ❌"
            await bot.answer_callback_query(call.id, f"محصول {msg}")
            
            # بازگشت به صفحه جزئیات برای دیدن تغییر
            await show_shop_item_details(call, params)
        else:
            await bot.answer_callback_query(call.id, "محصول یافت نشد.")
    except Exception as e:
        logger.error(f"Error toggling status: {e}")

async def delete_shop_item(call: types.CallbackQuery, params: list):
    """حذف محصول"""
    try:
        addon_id = int(params[1])
        
        if await db.delete_addon(addon_id):
            await bot.answer_callback_query(call.id, "✅ محصول با موفقیت حذف شد.")
            # بازگشت به لیست اصلی
            await open_shop_management(call)
        else:
            await bot.answer_callback_query(call.id, "❌ خطا: محصول یافت نشد.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error deleting addon: {e}")
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی.", show_alert=True)

# ============================================================================
# 3. پروسه افزودن محصول جدید (Add Product Flow)
# ============================================================================

async def start_add_product(call: types.CallbackQuery):
    """شروع ویزارد افزودن محصول"""
    admin_id = call.from_user.id
    
    # تنظیم وضعیت اولیه
    msg = await bot.edit_message_text(
        text="📝 **قدم اول:**\n\nلطفاً **نام محصول** را وارد کنید:\n(مثال: 15 گیگ آلمان - 1 ماهه)",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=await admin_kb.shop_cancel_menu(),
        parse_mode="Markdown"
    )
    
    SHOP_CREATION_STATES[admin_id] = {
        "step": "WAIT_NAME",
        "data": {},
        "msg_id": msg.message_id
    }

async def cancel_shop_creation(call: types.CallbackQuery):
    """لغو عملیات ساخت محصول"""
    uid = call.from_user.id
    if uid in SHOP_CREATION_STATES:
        del SHOP_CREATION_STATES[uid]
    
    await bot.answer_callback_query(call.id, "عملیات لغو شد.")
    # بازگشت به لیست محصولات
    await open_shop_management(call)

async def process_shop_steps(message: types.Message):
    """
    هندلر مراحل متنی (Text Step Handler).
    این تابع باید از طریق یک مسیج هندلر کلی در admin_router صدا زده شود.
    """
    admin_id = message.from_user.id
    if admin_id not in SHOP_CREATION_STATES:
        return

    state = SHOP_CREATION_STATES[admin_id]
    step = state["step"]
    chat_id = message.chat.id
    
    # حذف پیام کاربر برای تمیز ماندن چت
    try:
        await bot.delete_message(chat_id, message.message_id)
    except: pass

    # --- مرحله ۱: دریافت نام ---
    if step == "WAIT_NAME":
        name = message.text.strip()
        state["data"]["name"] = name
        state["step"] = "WAIT_PRICE"
        
        await bot.edit_message_text(
            f"✅ نام: **{name}**\n\n💰 **قدم دوم:**\nلطفاً **قیمت (امتیاز مورد نیاز)** را وارد کنید:\n(فقط عدد)",
            chat_id, state["msg_id"],
            reply_markup=await admin_kb.shop_cancel_menu(),
            parse_mode="Markdown"
        )

    # --- مرحله ۲: دریافت قیمت ---
    elif step == "WAIT_PRICE":
        if not message.text.isdigit():
            # نمایش خطا موقت (یا ادیت پیام اصلی)
            # اینجا برای سادگی پیام خطا نمیفرستیم تا فلو به هم نریزد، فقط نادیده میگیریم
            # یا می توانیم پیام اصلی را ادیت کنیم که "عدد وارد کن"
            return 

        state["data"]["price"] = float(message.text)
        state["step"] = "WAIT_GB"
        
        await bot.edit_message_text(
            f"✅ قیمت: {message.text}\n\n📊 **قدم سوم:**\nلطفاً **حجم اضافه (گیگابایت)** را وارد کنید:\n(عدد 0 اگر حجم ندارد)",
            chat_id, state["msg_id"],
            reply_markup=await admin_kb.shop_cancel_menu(),
            parse_mode="Markdown"
        )

    # --- مرحله ۳: دریافت حجم ---
    elif step == "WAIT_GB":
        try:
            val = float(message.text)
        except: return 

        state["data"]["gb"] = val
        state["step"] = "WAIT_DAYS"
        
        await bot.edit_message_text(
            f"✅ حجم: {val} GB\n\n⏳ **قدم آخر:**\nلطفاً **تعداد روز اضافه** را وارد کنید:\n(عدد 0 اگر روز ندارد)",
            chat_id, state["msg_id"],
            reply_markup=await admin_kb.shop_cancel_menu(),
            parse_mode="Markdown"
        )

    # --- مرحله ۴: دریافت روز و ذخیره نهایی ---
    elif step == "WAIT_DAYS":
        if not message.text.isdigit():
            return

        state["data"]["days"] = int(message.text)
        
        # ذخیره در دیتابیس
        d = state["data"]
        try:
            await db.add_addon(
                name=d["name"],
                price=d["price"],
                extra_gb=d["gb"],
                extra_days=d["days"]
            )
            
            final_msg = (
                f"✅ **محصول جدید با موفقیت ساخته شد!**\n\n"
                f"📦 {d['name']}\n"
                f"💰 {int(d['price'])} امتیاز\n"
                f"📊 {d['gb']} GB | ⏳ {d['days']} روز"
            )
        except Exception as e:
            logger.error(f"Error saving addon: {e}")
            final_msg = f"❌ خطا در ذخیره محصول."

        # پایان کار: حذف استیت
        del SHOP_CREATION_STATES[admin_id]
        
        # ساخت دکمه بازگشت دستی
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="admin:shop:main"))
        
        # نمایش پیام نهایی
        await bot.edit_message_text(
            final_msg,
            chat_id, state["msg_id"],
            reply_markup=kb,
            parse_mode="Markdown"
        )