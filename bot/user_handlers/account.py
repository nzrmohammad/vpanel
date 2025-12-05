# bot/user_handlers/account.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.formatters import user_formatter
from bot.services.panels import PanelFactory
from bot.database import db
from bot.language import get_string
from bot.config import ENABLE_TRAFFIC_TRANSFER
import logging

logger = logging.getLogger(__name__)

@bot.callback_query_handler(func=lambda call: call.data == "manage")
async def account_list_handler(call: types.CallbackQuery):
    """نمایش لیست اکانت‌های کاربر"""
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    # دریافت اکانت‌های کاربر از دیتابیس لوکال
    accounts = db.get_users_by_telegram_id(user_id)
    
    if not accounts:
        await bot.edit_message_text(
            get_string('fmt_no_account_registered', lang),
            user_id,
            call.message.message_id,
            reply_markup=user.back_btn("back", lang)
        )
        return

    # بروزرسانی سریع دیتا (اختیاری - اگر کش ندارید)
    # برای سرعت بیشتر، معمولا فقط لیست دیتابیس را نشان می‌دهیم
    # و جزئیات دقیق را وقتی کاربر روی اکانت کلیک کرد می‌گیریم
    
    markup = user.accounts(accounts, lang)
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
    lang = db.get_user_lang(user_id)
    acc_id = int(call.data.split('_')[1])
    
    account = db.get_account_by_id(acc_id)
    if not account:
        await bot.answer_callback_query(call.id, "Not Found")
        return

    await bot.answer_callback_query(call.id, "🔄 Updating...")
    
    try:
        panel = await PanelFactory.get_panel(account['server_type'])
        identifier = account['uuid'] if account['server_type'] == 'hiddify' else account['username']
        remote_data = await panel.get_user(identifier)
        
        if remote_data:
            text = user_formatter.profile_info(remote_data, lang)
            markup = user.account_menu(acc_id, lang)
            
            await bot.edit_message_text(
                text, user_id, call.message.message_id,
                reply_markup=markup, parse_mode='HTML'
            )
        else:
            await bot.edit_message_text("❌ اکانت در سرور یافت نشد.", user_id, call.message.message_id)
            
    except Exception as e:
        logger.error(f"Account Error: {e}")
        await bot.answer_callback_query(call.id, "Connection Error")

# --- دریافت لینک اشتراک ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('getlinks_'))
async def get_subscription_link(call: types.CallbackQuery):
    acc_id = int(call.data.split('_')[1])
    # پیاده‌سازی دریافت لینک از پنل و نمایش آن
    # ... (مشابه منطق بالا)
    await bot.answer_callback_query(call.id, "لینک کپی شد (مثال)")