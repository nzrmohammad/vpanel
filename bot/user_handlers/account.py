# bot/user_handlers/account.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot import combined_handler
from bot.language import get_string
import logging

logger = logging.getLogger(__name__)

@bot.callback_query_handler(func=lambda call: call.data == "add")
async def add_account_prompt(call: types.CallbackQuery):
    """درخواست ارسال UUID از کاربر"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(user_menu.back_btn("manage", lang))
    
    await bot.edit_message_text(
        get_string('prompt_add_uuid', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "manage")
async def account_list_handler(call: types.CallbackQuery):
    """نمایش لیست اکانت‌های کاربر"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # دریافت اکانت‌ها
    accounts = await db.uuids(user_id)
    
    markup = await user_menu.accounts(accounts, lang)
    
    if not accounts:
        text = get_string('fmt_no_account_registered', lang)
    else:
        text = get_string('account_list_title', lang)

    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_'))
async def account_detail_handler(call: types.CallbackQuery):
    """جزئیات یک اکانت خاص"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    try:
        acc_id = int(call.data.split('_')[1])
        account = await db.uuid_by_id(user_id, acc_id)
        
        if not account:
            await bot.answer_callback_query(call.id, "Account Not Found")
            return

        await bot.answer_callback_query(call.id, "🔄 Updating...")
        
        # دریافت اطلاعات ترکیبی از همه پنل‌ها
        uuid_str = account['uuid']
        # توجه: در دیتابیس uuid آبجکت است، باید به رشته تبدیل شود
        info = await combined_handler.get_combined_user_info(str(uuid_str))
        
        if info:
            # اضافه کردن ID دیتابیس برای استفاده در دکمه‌ها
            info['db_id'] = acc_id 
            text = await user_formatter.profile_info(info, lang)
            markup = await user_menu.account_menu(acc_id, lang)
            
            await bot.edit_message_text(
                text, user_id, call.message.message_id,
                reply_markup=markup, parse_mode='Markdown'
            )
        else:
            await bot.edit_message_text("❌ اطلاعات اکانت یافت نشد.", user_id, call.message.message_id)
            
    except Exception as e:
        logger.error(f"Account Detail Error: {e}")
        await bot.answer_callback_query(call.id, "Error fetching details")

# --- بخش هندلر آمار فوری (Quick Stats) ---

@bot.callback_query_handler(func=lambda call: call.data == "quick_stats")
async def quick_stats_init(call: types.CallbackQuery):
    """
    نمایش آمار فوری برای اولین اکانت (صفحه ۰)
    """
    await _show_quick_stats(call, page=0)


@bot.callback_query_handler(func=lambda call: call.data.startswith("qstats_acc_page_"))
async def quick_stats_pagination(call: types.CallbackQuery):
    """
    مدیریت دکمه‌های بعدی و قبلی در آمار فوری
    """
    try:
        # استخراج شماره صفحه از کال‌بک دیتا (مثلاً qstats_acc_page_1 -> 1)
        page = int(call.data.split("_")[-1])
        await _show_quick_stats(call, page)
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "خطا در صفحه‌بندی.", show_alert=True)


async def _show_quick_stats(call: types.CallbackQuery, page: int):
    """
    تابع کمکی برای تولید محتوا و ویرایش پیام
    """
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # ۱. دریافت لیست تمام اکانت‌های فعال کاربر
    accounts = await db.uuids(user_id)
    
    # ۲. استفاده از متد آماده در user_formatter پروژه برای تولید متن و دیتای منو
    # این متد خودش به combined_handler وصل می‌شود و اطلاعات لایو را می‌گیرد
    text, menu_data = await user_formatter.quick_stats(accounts, page, lang)
    
    # ۳. ساخت دکمه‌های شیشه‌ای (بعدی/قبلی) با استفاده از user_menu
    markup = await user_menu.quick_stats_menu(
        num_accounts=menu_data['num_accounts'], 
        current_page=menu_data['current_page'], 
        lang_code=lang
    )
    
    # ۴. نمایش خروجی نهایی به کاربر
    try:
        await bot.edit_message_text(
            text=text,
            chat_id=user_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='MarkdownV2'  # فرمتر شما خروجی MarkdownV2 می‌دهد
        )
    except Exception as e:
        # هندل کردن خطای "پیام تغییر نکرده است"
        if "message is not modified" not in str(e).lower():
            logger.error(f"Error in quick stats: {e}")
            await bot.answer_callback_query(call.id, "خطا در به‌روزرسانی آمار.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('getlinks_'))
async def get_subscription_link(call: types.CallbackQuery):
    """منوی دریافت لینک"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[1])
    
    markup = await user_menu.get_links_menu(acc_id, lang)
    await bot.edit_message_text(
        get_string('prompt_get_links', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
    )