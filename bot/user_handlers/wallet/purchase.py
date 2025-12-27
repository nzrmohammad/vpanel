# bot/user_handlers/wallet/purchase.py

import logging
import uuid as uuid_lib
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot.language import get_string
from bot.services.panels import PanelFactory
from bot.utils.formatters import escape_markdown

logger = logging.getLogger(__name__)

# --- مشاهده دسته‌بندی‌ها ---
@bot.callback_query_handler(func=lambda call: call.data == "view_plans")
async def view_plans_categories(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    markup = await user_menu.plan_categories_menu(lang)
    await bot.edit_message_text(get_string('prompt_select_plan_category', lang), user_id, call.message.message_id, reply_markup=markup)

# --- نمایش لیست پلن‌ها ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("show_plans:"))
async def show_plans_list(call: types.CallbackQuery):
    category = call.data.split(":")[1]
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # 1. دریافت اطلاعات دسته‌بندی
    categories = await db.get_server_categories()
    selected_cat = next((c for c in categories if c['code'] == category), None)
    
    cat_name = selected_cat['name'] if selected_cat else category
    cat_emoji = selected_cat['emoji'] if selected_cat else ""
    cat_desc = selected_cat.get('description') if selected_cat else None
    
    # --- درخواست ۱: نمایش پاپ‌آپ (Alert) ---
    # اگر توضیحات وجود دارد، به صورت هشدار هم نمایش داده شود
    if cat_desc:
        await bot.answer_callback_query(call.id, cat_desc, show_alert=True)
    
    # 2. دریافت و فیلتر پلن‌ها
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0)
    all_plans = await db.get_all_plans(active_only=True)
    
    filtered_plans = []
    for plan in all_plans:
        cats = plan.get('allowed_categories') or []
        if category == 'combined':
            if len(cats) > 1 or not cats: filtered_plans.append(plan)
        else:
            if category in cats and len(cats) == 1: filtered_plans.append(plan)
    
    if not filtered_plans:
        try: await bot.answer_callback_query(call.id, get_string('fmt_plans_none_in_category', lang), show_alert=True)
        except: pass
        return

    # 3. ساخت متن پیام
    header_title = f"🚀 *پلن‌های فروش سرویس \({escape_markdown(cat_name)}\)*"
    text = f"{header_title}\n"
    
    # --- درخواست ۱: اضافه شدن توضیحات به متن ---
    if cat_desc:
        text += f"💡 {escape_markdown(cat_desc)}\n"
    
    line = "────────────────────"
    text += f"{line}\n"

    for plan in filtered_plans:
        p_name = escape_markdown(plan['name'])
        
        raw_vol = plan['volume_gb']
        vol_str = f"{int(raw_vol)}" if raw_vol == int(raw_vol) else f"{raw_vol}"
        p_vol = escape_markdown(vol_str)
        
        p_days = plan['days']
        price_comma = f"{int(plan['price']):,}"
        p_price = escape_markdown(price_comma)
        
        # --- درخواست ۲: حذف پرچم تکراری ---
        # اینجا cat_emoji را حذف کردیم چون معمولاً در نام پلن یا هدر هست
        text += (
            f"{p_name}\n"  # قبلاً اینجا {cat_emoji} بود که حذف شد
            f"حجم: {p_vol} گیگابایت\n"
            f"مدت زمان: {p_days} روز\n"
            f"قیمت: {p_price} تومان\n"
            f"{line}\n"
        )

    text += "\nبرای مشاوره، با پشتیبانی در تماس باشید\."

    markup = await user_menu.plan_category_menu(lang, balance, filtered_plans)
    
    try:
        await bot.edit_message_text(
            text, 
            user_id, 
            call.message.message_id, 
            reply_markup=markup, 
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"Error displaying plans text: {e}")
        # هندل کردن خطای احتمالی Markdown
        fallback_text = text.replace('*', '').replace('\\', '').replace('(', '').replace(')', '')
        await bot.edit_message_text(fallback_text, user_id, call.message.message_id, reply_markup=markup)

# --- تایید خرید ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:buy_confirm:'))
async def buy_plan_confirm(call: types.CallbackQuery):
    plan_id = int(call.data.split(':')[2])
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)

    selected_plan = await db.get_plan_by_id(plan_id)
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0)
    
    text = user_formatter.purchase_confirmation(
        plan_name=selected_plan['name'],
        price=selected_plan['price'],
        current_balance=balance,
        lang_code=lang
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ تایید و پرداخت", callback_data=f"wallet:do_buy:{selected_plan['id']}"))
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="view_plans"))
    
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='HTML')

# --- اجرای خرید (Connect to Panel) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:do_buy:'))
async def execute_purchase(call: types.CallbackQuery):
    try:
        plan_id = int(call.data.split(':')[2])
        user_id = call.from_user.id
        lang = await db.get_user_language(user_id)
        
        plan = await db.get_plan_by_id(plan_id)
        if not plan: return
        
        user_data = await db.user(user_id)
        balance = user_data.get('wallet_balance', 0)
        
        if balance < plan['price']:
            await bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
            return

        await bot.edit_message_text("⏳ در حال فعال‌سازی سرویس...", user_id, call.message.message_id)
        
        # لاجیک ساخت سرویس در پنل
        target_panel_name = "server1" # بهتر است هوشمند انتخاب شود
        panel_api = await PanelFactory.get_panel(target_panel_name)
        
        if not panel_api:
             await bot.send_message(user_id, "❌ خطای اتصال به سرور.")
             return

        random_suffix = str(uuid_lib.uuid4())[:8]
        username = f"u{user_id}_{random_suffix}"
        
        new_service = await panel_api.add_user(username, plan['volume_gb'], plan['days'])
        
        if new_service:
            # کسر موجودی و ثبت
            await db.update_wallet_balance(user_id, -plan['price'], 'purchase', f"خرید پلن {plan['name']}")
            service_uuid = new_service.get('uuid') or username 
            await db.add_uuid(user_id=user_id, uuid_str=service_uuid, name=username)
            
            uuid_id = await db.get_uuid_id_by_uuid(service_uuid)
            if uuid_id and plan.get('allowed_categories'):
                await db.grant_access_by_category(uuid_id, plan['allowed_categories'])

            markup = await user_menu.post_charge_menu(lang) 
            await bot.edit_message_text(
                f"✅ <b>خرید موفقیت‌آمیز بود!</b>\n\nنام کاربری: <code>{username}</code>",
                user_id, call.message.message_id, reply_markup=markup, parse_mode='HTML'
            )
        else:
            await bot.send_message(user_id, "❌ خطا در ساخت سرویس در پنل.")
            
    except Exception as e:
        logger.error(f"Purchase Error: {e}")
        await bot.send_message(user_id, "❌ خطای غیرمنتظره.")