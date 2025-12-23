# bot/admin_handlers/shop_management.py

from telebot import types
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import admin as admin_kb
from bot.config import ADMIN_IDS

# دیکشنری برای ذخیره وضعیت مراحل ساخت محصول برای هر ادمین
# ساختار: {admin_id: {"step": "STEP_NAME", "data": {...}, "msg_id": 123}}
SHOP_CREATION_STATES = {}

# ============================================================================
# 1. Entry Point (اتصال به admin_router)
# ============================================================================

async def handle_shop_callbacks(call: types.CallbackQuery):
    """
    این تابع توسط admin_router صدا زده می‌شود.
    فرمت کال‌بک: admin:shop:ACTION:ARGS...
    """
    parts = call.data.split(':')
    # parts[0]=admin, parts[1]=shop
    sub_action = parts[2] if len(parts) > 2 else "main"

    if sub_action == "main":
        await open_shop_management(call)
    
    elif sub_action == "add":
        await start_add_product(call)
    
    elif sub_action == "del":
        await delete_shop_item(call)
    
    elif sub_action == "cancel":
        await cancel_shop_creation(call)

# ============================================================================
# 2. Logic Functions (منطق دکمه‌ها)
# ============================================================================

async def open_shop_management(call: types.CallbackQuery):
    """نمایش لیست محصولات فروشگاه"""
    # دریافت لیست محصولات فعال از دیتابیس
    addons = await db.get_all_addons(active_only=True)
    
    # ساخت کیبورد (مطمئن شوید متد shop_management_menu در admin_kb وجود دارد)
    markup = await admin_kb.shop_management_menu(addons)
    
    text = (
        "🏪 **مدیریت فروشگاه امتیاز**\n\n"
        "لیست محصولات فعلی در زیر نمایش داده شده است.\n"
        "می‌توانید محصولات را حذف کنید یا محصول جدیدی اضافه نمایید."
    )
    
    await bot.edit_message_text(
        text, 
        call.message.chat.id, 
        call.message.message_id, 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

async def start_add_product(call: types.CallbackQuery):
    """شروع پروسه ساخت محصول جدید"""
    admin_id = call.from_user.id
    
    # ارسال پیام پرسش اول
    msg = await bot.send_message(
        call.message.chat.id,
        "📝 **قدم اول:**\n\nلطفاً **نام محصول** را وارد کنید:\n(مثال: 15 گیگ آلمان - 1 ماهه)",
        reply_markup=await admin_kb.shop_cancel_menu(),
        parse_mode="Markdown"
    )
    
    # ذخیره وضعیت ادمین
    SHOP_CREATION_STATES[admin_id] = {
        "step": "WAIT_NAME",
        "data": {},
        "msg_id": msg.message_id
    }

async def delete_shop_item(call: types.CallbackQuery):
    """حذف یک محصول"""
    try:
        # فرمت: admin:shop:del:ID
        addon_id = int(call.data.split(":")[3])
        
        success = await db.delete_addon(addon_id)
        if success:
            await bot.answer_callback_query(call.id, "✅ محصول با موفقیت حذف شد.")
            # رفرش کردن لیست
            await open_shop_management(call)
        else:
            await bot.answer_callback_query(call.id, "❌ خطا: محصول یافت نشد.", show_alert=True)
            
    except Exception as e:
        print(f"Error removing addon: {e}")
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی.", show_alert=True)

async def cancel_shop_creation(call: types.CallbackQuery):
    """لغو عملیات ساخت"""
    uid = call.from_user.id
    if uid in SHOP_CREATION_STATES:
        del SHOP_CREATION_STATES[uid]
    
    # حذف پیام پرسش و بازگشت به منوی شاپ
    try:
        await bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
        
    await bot.answer_callback_query(call.id, "عملیات لغو شد.")
    # اختیاری: بازگشت به منوی اصلی شاپ
    # await open_shop_management(call)

# ============================================================================
# 3. Message Handler (مدیریت ورودی‌های متنی مراحل ساخت)
# ============================================================================

@bot.message_handler(content_types=['text'], func=lambda m: m.from_user.id in SHOP_CREATION_STATES)
async def process_shop_steps(message: types.Message):
    """
    این تابع پیام‌های متنی ادمین را چک می‌کند.
    اگر ادمین در حال ساخت محصول باشد، ورودی‌ها را پردازش می‌کند.
    """
    admin_id = message.from_user.id
    state = SHOP_CREATION_STATES[admin_id]
    step = state["step"]
    chat_id = message.chat.id

    # حذف پیام ارسالی ادمین برای تمیز ماندن چت
    try:
        await bot.delete_message(chat_id, message.message_id)
    except:
        pass

    # --- مرحله ۱: دریافت نام ---
    if step == "WAIT_NAME":
        state["data"]["name"] = message.text
        state["step"] = "WAIT_PRICE"
        
        await bot.edit_message_text(
            f"✅ نام: {message.text}\n\n💰 **قدم دوم:**\nقیمت محصول (به امتیاز) را وارد کنید:\n(مثال: 150)",
            chat_id, state["msg_id"],
            reply_markup=await admin_kb.shop_cancel_menu(),
            parse_mode="Markdown"
        )

    # --- مرحله ۲: دریافت قیمت ---
    elif step == "WAIT_PRICE":
        if not message.text.isdigit():
            err = await bot.send_message(chat_id, "❌ لطفاً فقط عدد وارد کنید.")
            # می‌توانید یک تایمر برای حذف پیام خطا بگذارید
            return

        state["data"]["price"] = float(message.text)
        state["step"] = "WAIT_GB"
        
        await bot.edit_message_text(
            f"✅ قیمت: {message.text}\n\n💾 **قدم سوم:**\nمقدار حجم اضافه (به گیگابایت) را وارد کنید:\n(اگر فقط تمدید زمانی است، 0 بگذارید)",
            chat_id, state["msg_id"],
            reply_markup=await admin_kb.shop_cancel_menu(),
            parse_mode="Markdown"
        )

    # --- مرحله ۳: دریافت حجم ---
    elif step == "WAIT_GB":
        try:
            val = float(message.text)
            state["data"]["gb"] = val
            state["step"] = "WAIT_DAYS"
            
            await bot.edit_message_text(
                f"✅ حجم: {val} GB\n\n📅 **قدم آخر:**\nتعداد روز اضافه را وارد کنید:\n(اگر فقط حجم است، 0 بگذارید)",
                chat_id, state["msg_id"],
                reply_markup=await admin_kb.shop_cancel_menu(),
                parse_mode="Markdown"
            )
        except ValueError:
            await bot.send_message(chat_id, "❌ لطفاً عدد معتبر (مثلاً 1.5 یا 2) وارد کنید.")

    # --- مرحله ۴: دریافت روز و ذخیره نهایی ---
    elif step == "WAIT_DAYS":
        if not message.text.isdigit():
            await bot.send_message(chat_id, "❌ لطفاً عدد صحیح وارد کنید.")
            return

        state["data"]["days"] = int(message.text)
        
        # ذخیره نهایی در دیتابیس
        d = state["data"]
        try:
            await db.create_addon(
                name=d["name"],
                price=d["price"],
                gb=d["gb"],
                days=d["days"]
            )
            final_msg = (
                f"✅ **محصول جدید با موفقیت ساخته شد!**\n\n"
                f"📦 {d['name']}\n"
                f"💰 {int(d['price'])} امتیاز\n"
                f"📊 {d['gb']} GB | ⏳ {d['days']} روز"
            )
        except Exception as e:
            final_msg = f"❌ خطا در ذخیره محصول: {e}"

        # پایان کار و پاک کردن استیت
        del SHOP_CREATION_STATES[admin_id]
        
        await bot.edit_message_text(
            final_msg,
            chat_id, state["msg_id"],
            parse_mode="Markdown"
        )
        
        # بازگشت به لیست محصولات (فراخوانی مجدد لیست)
        # یک آبجکت کال‌بک ساختگی می‌سازیم
        dummy_call = types.CallbackQuery(
            id='0', from_user=message.from_user, data='admin:shop:main', 
            message=message, chat_instance='0'
        )
        await open_shop_management(dummy_call)