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

@bot.callback_query_handler(func=lambda call: call.data == "manage")
async def account_list_handler(call: types.CallbackQuery):
    """نمایش لیست اکانت‌های کاربر"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # دریافت اکانت‌ها (UUIDها) به صورت Async
    accounts = await db.uuids(user_id)
    
    if not accounts:
        await bot.edit_message_text(
            get_string('fmt_no_account_registered', lang),
            user_id,
            call.message.message_id,
            reply_markup=user_menu.back_btn("back", lang)
        )
        return

    markup = await user_menu.accounts(accounts, lang)
    await bot.edit_message_text(
        get_string('account_list_title', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
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