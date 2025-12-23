# bot/user_handlers/shop_actions.py

import logging
import random
import time
import copy
from telebot import types

from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.formatters import user_formatter
from bot.config import ADMIN_IDS
from bot import combined_handler

# تنظیمات لاگ
logger = logging.getLogger(__name__)

# =============================================================================
# 1. ابزارهای کمکی (Helpers)
# =============================================================================

async def _get_shop_item(item_id: str):
    """
    دریافت اطلاعات محصول از دیتابیس بر اساس ID.
    این تابع پیشوند 'db_' را (اگر باشد) حذف کرده و در دیتابیس جستجو می‌کند.
    """
    try:
        # حذف پیشوند احتمالی برای اطمینان
        clean_id = str(item_id).replace("db_", "")
        
        if clean_id.isdigit():
            real_id = int(clean_id)
            addon = await db.get_addon_by_id(real_id)
            
            if addon:
                # تبدیل فرمت دیتابیس به فرمت استاندارد دیکشنری برای استفاده در هندلرها
                return {
                    "id": str(addon['id']),
                    "name": addon['name'],
                    "cost": int(addon['price']),
                    "gb": addon.get('extra_gb', 0),
                    "days": addon.get('extra_days', 0),
                    "target": "all"  # فرض بر این است که محصولات دیتابیس روی همه سرویس‌ها اعمال می‌شوند
                }
    except Exception as e:
        logger.error(f"Error looking up shop item {item_id}: {e}")
    
    return None

# =============================================================================
# 2. نمایش فروشگاه (Shop Display)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "shop:main")
async def shop_main_handler(call: types.CallbackQuery):
    """نمایش منوی اصلی فروشگاه و لیست محصولات فعال"""
    uid = call.from_user.id
    
    # دریافت اطلاعات کاربر و موجودی
    user_data = await db.user(uid)
    points = user_data.get('achievement_points', 0) if user_data else 0
    access = await db.get_user_access_rights(uid)
    
    final_items = []
    
    # دریافت محصولات فعال از دیتابیس
    try:
        db_addons = await db.get_all_addons(active_only=True)
        for addon in db_addons:
            final_items.append({
                "id": str(addon['id']),
                "name": addon['name'],
                "cost": int(addon['price']),
                "gb": addon.get('extra_gb', 0),
                "days": addon.get('extra_days', 0),
                "target": "all"
            })
    except Exception as e:
        logger.error(f"Error loading DB addons: {e}")
        await bot.answer_callback_query(call.id, "خطا در بارگذاری محصولات.", show_alert=True)
        return
    
    # آماده‌سازی متن و کیبورد
    text = f"🛍️ *فروشگاه امتیاز*\nموجودی شما: *{points} امتیاز*\n\nمحصول مورد نظر را انتخاب کنید:"
    markup = await user_menu.achievement_shop_menu(points, access, final_items)
    
    await _safe_edit(uid, call.message.message_id, text, reply_markup=markup, parse_mode="MarkdownV2")

# =============================================================================
# 3. منطق خرید (Purchase Logic: Confirm & Execute)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop:confirm:"))
async def shop_confirm_handler(call: types.CallbackQuery):
    """نمایش صفحه تایید خرید و پیش‌نمایش تغییرات سرویس"""
    try:
        item_id = call.data.split(":")[2]
        item = await _get_shop_item(item_id)
        
        if not item: 
            await bot.answer_callback_query(call.id, "❌ آیتم یافت نشد یا حذف شده است.", show_alert=True)
            # رفرش کردن صفحه شاپ برای حذف آیتم نامعتبر از دید کاربر
            await shop_main_handler(call)
            return

        uid = call.from_user.id
        lang = await db.get_user_language(uid)
        
        # بررسی اینکه آیا کاربر سرویسی دارد که محصول روی آن اعمال شود؟
        user_uuids = await db.uuids(uid)
        if not user_uuids:
            await bot.answer_callback_query(call.id, "❌ شما هیچ سرویس فعالی برای اعمال این بسته ندارید.", show_alert=True)
            return
        
        # دریافت اطلاعات فعلی سرویس (برای نمایش قبل/بعد)
        # فعلاً اولین سرویس کاربر را به عنوان هدف در نظر می‌گیریم
        main_uuid = str(user_uuids[0]['uuid'])
        info_before = await combined_handler.get_combined_user_info(main_uuid)
        
        if not info_before:
             await bot.answer_callback_query(call.id, "❌ خطا در دریافت اطلاعات سرویس.", show_alert=True)
             return

        # شبیه‌سازی وضعیت بعد از خرید (فقط برای نمایش)
        info_after = copy.deepcopy(info_before)
        add_gb = item.get('gb', 0)
        add_days = item.get('days', 0)
        
        if 'usage_limit_GB' in info_after:
            info_after['usage_limit_GB'] += add_gb
        if info_after.get('expire') and add_days:
            # نکته: محاسبه دقیق تاریخ در بک‌اند انجام می‌شود، اینجا فقط نمایشی اضافه می‌کنیم
            info_after['expire'] += add_days

        summary = await user_formatter.purchase_summary(info_before, info_after, {"name": item['name']}, lang)
        
        text = (
            f"❓ *تایید نهایی خرید*\n\n"
            f"📦 بسته: {escape_markdown(item['name'])}\n"
            f"💰 قیمت: {item['cost']} امتیاز\n\n"
            f"{summary}\n\n"
            "آیا از خرید اطمینان دارید؟"
        )
        
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ بله، خرید شود", callback_data=f"shop:exec:{item['id']}"),
            types.InlineKeyboardButton("❌ خیر، بازگشت", callback_data="shop:main")
        )
        
        await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")
        
    except Exception as e:
        logger.error(f"Error in shop confirm: {e}")
        await bot.answer_callback_query(call.id, "خطای سیستمی رخ داد.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("shop:exec:"))
async def shop_execute_handler(call: types.CallbackQuery):
    """اجرای نهایی تراکنش: کسر امتیاز و اعمال تغییرات روی پنل"""
    try:
        item_id = call.data.split(":")[2]
        uid = call.from_user.id
        
        item = await _get_shop_item(item_id)
        if not item:
            await bot.answer_callback_query(call.id, "❌ خطا: آیتم نامعتبر.", show_alert=True)
            return

        # 1. تلاش برای کسر امتیاز
        if await db.spend_achievement_points(uid, item['cost']):
            
            # 2. پیدا کردن سرویس کاربر
            user_uuids = await db.uuids(uid)
            if user_uuids:
                uuid = str(user_uuids[0]['uuid'])
                
                # 3. اعمال تغییرات روی تمام پنل‌های متصل
                success = await combined_handler.modify_user_on_all_panels(
                    identifier=uuid,
                    add_gb=item.get('gb', 0),
                    add_days=item.get('days', 0),
                    target_panel_type=None # None = همه پنل‌ها
                )
                
                if success:
                    # موفقیت: ثبت لاگ و اطلاع به کاربر
                    await db.log_shop_purchase(uid, item['id'], item['cost'])
                    await bot.answer_callback_query(call.id, "✅ خرید با موفقیت انجام شد.", show_alert=True)
                    
                    # بازگشت به صفحه اول شاپ
                    await shop_main_handler(call)
                    
                    # اطلاع به ادمین (اختیاری)
                    try:
                        msg = f"🛍 کاربر {uid} بسته {item['name']} را به قیمت {item['cost']} امتیاز خرید."
                        for aid in ADMIN_IDS:
                            await bot.send_message(aid, msg)
                    except: pass
                    return
            
            # اگر به هر دلیلی (نبود سرویس یا خطای پنل) اعمال نشد، پول را پس بده
            await db.add_achievement_points(uid, item['cost'])
            await bot.answer_callback_query(call.id, "❌ خطا در اعمال بسته روی سرور. امتیاز شما بازگشت داده شد.", show_alert=True)
            
        else:
            await bot.answer_callback_query(call.id, "❌ موجودی امتیاز کافی نیست.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in shop execute: {e}")
        await bot.answer_callback_query(call.id, "خطای غیرمنتظره رخ داد.", show_alert=True)

# =============================================================================
# 4. گردونه شانس (Lucky Spin)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "lucky_spin_menu")
async def lucky_spin_menu_handler(call: types.CallbackQuery):
    """منوی شروع گردونه شانس"""
    uid = call.from_user.id
    user_data = await db.user(uid)
    current_points = user_data.get('achievement_points', 0) if user_data else 0
    SPIN_COST = 50
    
    msg = (
        f"🎰 **گردونه شانس**\n\n"
        f"💰 موجودی شما: *{current_points} امتیاز*\n"
        f"💎 هزینه هر چرخش: *{SPIN_COST} امتیاز*\n\n"
        f"🎁 **جوایز احتمالی:**\n"
        f"▫️ حجم اضافه\n"
        f"▫️ امتیاز رایگان\n"
        f"▫️ یا شاید هم هیچ!\n\n"
        f"شانست رو امتحان می‌کنی؟"
    )
    
    kb = types.InlineKeyboardMarkup()
    if current_points >= SPIN_COST:
        kb.add(types.InlineKeyboardButton(f"🎲 بچرخان! (-{SPIN_COST})", callback_data="do_spin"))
    else:
        kb.add(types.InlineKeyboardButton("❌ موجودی کافی نیست", callback_data="shop:main"))
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop:main"))
    
    await _safe_edit(uid, call.message.message_id, msg, reply_markup=kb, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "do_spin")
async def do_spin_handler(call: types.CallbackQuery):
    """اجرای منطق چرخش گردونه"""
    uid = call.from_user.id
    SPIN_COST = 50
    
    # پیکربندی جوایز (اینجا هاردکد است چون منطق شانس است، اما می‌شود به دیتابیس برد)
    REWARDS_CONFIG = [
        {"name": "پوچ 😢",           "weight": 40, "type": "none"},
        {"name": "۲۰ امتیاز 🪙", "weight": 30, "type": "points", "value": 20},
        {"name": "۵۰۰ مگابایت 🎁", "weight": 20, "type": "volume", "value": 0.5},
        {"name": "۱ گیگابایت 🔥",  "weight": 10, "type": "volume", "value": 1.0},
    ]
    
    # کسر هزینه ورودی
    if not await db.spend_achievement_points(uid, SPIN_COST):
        await bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
        return

    # نمایش افکت چرخیدن
    try:
        await bot.edit_message_text("🎰 در حال چرخش... 🎲", call.message.chat.id, call.message.message_id)
        time.sleep(1.0) 
    except: pass

    # انتخاب جایزه
    reward = random.choices(REWARDS_CONFIG, weights=[r['weight'] for r in REWARDS_CONFIG], k=1)[0]
    result_msg = ""
    
    # پردازش جایزه
    if reward['type'] == "none":
        result_msg = f"😢 اوه! {reward['name']}\nشاید دفعه بعد."
        
    elif reward['type'] == "points":
        await db.add_achievement_points(uid, reward['value'])
        result_msg = f"🎉 تبریک! برنده شدید:\n**{reward['name']}**"
        
    elif reward['type'] == "volume":
        user_uuids = await db.uuids(uid)
        if user_uuids:
            first_uuid = str(user_uuids[0]['uuid'])
            success = await combined_handler.modify_user_on_all_panels(first_uuid, add_gb=reward['value'], add_days=0)
            if success:
                result_msg = f"🔥 عالی! برنده شدید:\n**{reward['name']}**\n(به سرویس شما اضافه شد)"
            else:
                # برگشت پول در صورت خطا
                await db.add_achievement_points(uid, SPIN_COST)
                result_msg = "❌ خطا در افزودن حجم. امتیاز برگشت داده شد."
        else:
            await db.add_achievement_points(uid, SPIN_COST)
            result_msg = "❌ سرویس فعالی برای دریافت جایزه ندارید. امتیاز برگشت داده شد."

    # نمایش نتیجه
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎲 چرخش مجدد", callback_data="lucky_spin_menu"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop:main"))
    
    await _safe_edit(uid, call.message.message_id, result_msg, reply_markup=kb, parse_mode="Markdown")