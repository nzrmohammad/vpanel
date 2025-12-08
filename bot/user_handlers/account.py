# bot/user_handlers/account.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot import combined_handler
from bot.language import get_string
from bot.utils import escape_markdown, _safe_edit
import logging
import asyncio

logger = logging.getLogger(__name__)

user_steps = {}

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
    """نمایش لیست اکانت‌های کاربر با محاسبه درصد مصرف"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    accounts = await db.uuids(user_id)
    
    if accounts:
        
        for acc in accounts:
            try:
                uuid_str = str(acc['uuid'])
                info = await combined_handler.get_combined_user_info(uuid_str)
                if info:
                    acc['usage_percentage'] = info.get('usage_percentage', 0)
                    acc['expire'] = info.get('expire')
                else:
                    acc['usage_percentage'] = 0
            except Exception as e:
                logger.error(f"Error fetching stats for list: {e}")
                acc['usage_percentage'] = 0
    
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
        
        uuid_str = account['uuid']
        info = await combined_handler.get_combined_user_info(str(uuid_str))
        
        if info:
            info['db_id'] = acc_id 
            text = await user_formatter.profile_info(info, lang)
            markup = await user_menu.account_menu(acc_id, lang)
            
            await bot.edit_message_text(
                text, user_id, call.message.message_id,
                reply_markup=markup, parse_mode='MarkdownV2'
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
    accounts = await db.uuids(user_id)
    
    text, menu_data = await user_formatter.quick_stats(accounts, page, lang)
    
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
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"Error in quick stats: {e}")
            await bot.answer_callback_query(call.id, "خطا در به‌روزرسانی آمار.")

# --- 2. جزئیات اکانت (Menu) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_'))
async def account_detail_handler(call: types.CallbackQuery):
    """جزئیات یک اکانت خاص + حل مشکل باز نشدن منو"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    try:
        acc_id = int(call.data.split('_')[1])
        account = await db.uuid_by_id(user_id, acc_id)
        
        if not account:
            await bot.answer_callback_query(call.id, "Account Not Found")
            return
                
        uuid_str = str(account['uuid'])
        
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if not info:
            info = {
                'name': account.get('name', 'Unknown'),
                'uuid': uuid_str,
                'is_active': account.get('is_active', False),
                'usage_limit_GB': 0,
                'current_usage_GB': 0,
                'expire': None,
                'breakdown': {}
            }
        
        info['db_id'] = acc_id 
        
        text = await user_formatter.profile_info(info, lang)
        markup = await user_menu.account_menu(acc_id, lang)
        
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Account Detail Error: {e}", exc_info=True)
        await bot.answer_callback_query(call.id, "Error fetching details")

# --- 3. دریافت لینک (Get Link) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('getlinks_'))
async def get_subscription_link(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[1])
    markup = await user_menu.get_links_menu(acc_id, lang)
    raw_text = get_string('prompt_get_links', lang)
    
    safe_text = escape_markdown(raw_text)
    
    await _safe_edit(user_id, call.message.message_id, safe_text, reply_markup=markup, parse_mode='MarkdownV2')

# --- 4. تغییر نام (Change Name) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('changename_'))
async def change_name_prompt(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[1])
    
    # ارسال پیام درخواست نام
    prompt_msg = await bot.send_message(
        user_id, 
        get_string('prompt_enter_new_name', lang), 
        reply_markup=types.ForceReply()
    )
    
    # ذخیره شناسه پیام‌ها برای حذف و ویرایش بعدی
    user_steps[user_id] = {
        'action': 'change_name',
        'acc_id': acc_id,
        'menu_msg_id': call.message.message_id,
        'prompt_msg_id': prompt_msg.message_id
    }

# این تابع جدید را برای مدیریت دریافت نام جدید اضافه کنید
@bot.message_handler(func=lambda m: m.from_user.id in user_steps and user_steps[m.from_user.id]['action'] == 'change_name')
async def process_change_name_step(message: types.Message):
    user_id = message.from_user.id
    step_data = user_steps.pop(user_id, None)
    
    if not step_data: return

    acc_id = step_data['acc_id']
    menu_msg_id = step_data.get('menu_msg_id')
    prompt_msg_id = step_data.get('prompt_msg_id')
    
    lang = await db.get_user_language(user_id)
    new_name = message.text.strip()
    
    # 1. حذف پیام ورودی کاربر (نامی که فرستاده)
    try:
        await bot.delete_message(user_id, message.message_id)
    except:
        pass

    # 2. حذف پیام درخواست (Prompt)
    if prompt_msg_id:
        try:
            await bot.delete_message(user_id, prompt_msg_id)
        except:
            pass

    # اعتبارسنجی نام
    if len(new_name) < 3:
        err = await bot.send_message(user_id, get_string('err_name_too_short', lang))
        await asyncio.sleep(3)
        try:
            await bot.delete_message(user_id, err.message_id)
        except:
            pass
        return

    # 3. آپدیت در دیتابیس
    await db.update_config_name(acc_id, new_name)
    
    # 4. ویرایش همان پیام قبلی (منوی اکانت) با اطلاعات جدید
    try:
        account = await db.uuid_by_id(user_id, acc_id)
        if account:
            uuid_str = str(account['uuid'])
            # دریافت اطلاعات تازه
            info = await combined_handler.get_combined_user_info(uuid_str)
            if info:
                info['db_id'] = acc_id
                info['name'] = new_name
                
                text = await user_formatter.profile_info(info, lang)
                markup = await user_menu.account_menu(acc_id, lang)
                
                # ویرایش پیام اصلی به جای ارسال پیام جدید
                await bot.edit_message_text(
                    text=text,
                    chat_id=user_id,
                    message_id=menu_msg_id,
                    reply_markup=markup,
                    parse_mode='MarkdownV2'
                )
                
                # نمایش تاییدیه کوتاه (Toast)
                await bot.answer_callback_query(callback_query_id=step_data.get('cb_id', '0'), text=get_string('msg_name_changed_success', lang))
                success_msg = await bot.send_message(user_id, get_string('msg_name_changed_success', lang), disable_notification=True)
                await asyncio.sleep(3)
                try:
                    await bot.delete_message(user_id, success_msg.message_id)
                except:
                    pass
    except Exception as e:
        logger.error(f"Change Name Refresh Error: {e}")

async def process_change_name(message: types.Message, acc_id: int, original_msg_id: int):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    new_name = message.text.strip()
    
    if len(new_name) < 3:
        await bot.send_message(user_id, get_string('err_name_too_short', lang))
        return

    # آپدیت در دیتابیس
    await db.update_config_name(acc_id, new_name)
    
    # بازگشت به منوی اکانت
    try:
        # شبیه‌سازی کلیک روی دکمه اکانت برای رفرش صفحه
        dummy_call = types.CallbackQuery(id='0', from_user=message.from_user, data=f'acc_{acc_id}', chat_instance='0', json_string='')
        dummy_call.message = message # ست کردن پیام برای ادیت
        await account_detail_handler(dummy_call)
        
        await bot.send_message(user_id, get_string('msg_name_changed_success', lang))
    except Exception as e:
        logger.error(f"Change Name Error: {e}")

# --- 5. حذف اکانت (Delete) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
async def delete_account_confirm(call: types.CallbackQuery):
    """تایید حذف"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[1])
    
    # منوی تایید ساده
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"confirm_del_{acc_id}"),
        types.InlineKeyboardButton("❌ خیر، پشیمون شدم", callback_data=f"acc_{acc_id}")
    )
    
    # متن فارسی شده
    warning_text = "⚠️ **آیا مطمئن هستید که می‌خواهید این اکانت را از لیست خود حذف کنید؟**\n\n(توجه: اکانت فقط از ربات حذف می‌شود و در سرور باقی می‌ماند)"
    
    await _safe_edit(user_id, call.message.message_id, warning_text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_del_'))
async def delete_account_execute(call: types.CallbackQuery):
    """اجرای حذف"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[2])
    
    # حذف از دیتابیس (فقط غیرفعال کردن)
    await db.deactivate_uuid(acc_id)
    
    await bot.answer_callback_query(call.id, get_string('msg_account_deleted', lang))
    # بازگشت به لیست
    await account_list_handler(call)

# --- 6. تاریخچه پرداخت (Payment History) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('payment_history_'))
async def payment_history_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    parts = call.data.split('_')
    acc_id = int(parts[2])
    
    history = await db.get_user_payment_history(acc_id)
    
    if not history:
        text = get_string('fmt_payment_history_no_info', lang)
    else:
        text = "📜 Payment History:\n\n"
        for h in history:
            # فرمت تاریخ
            dt_str = h['payment_date'].strftime("%Y-%m-%d %H:%M")
            text += f"📅 {dt_str}\n"
            
    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn(f"acc_{acc_id}", lang))
    
    # ✅ اصلاح مهم: متن باید escape شود
    safe_text = escape_markdown(text)
    await _safe_edit(user_id, call.message.message_id, safe_text, reply_markup=kb, parse_mode='MarkdownV2')


# --- 7. تاریخچه مصرف (Usage History) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('usage_history_'))
async def usage_history_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[2])
    
    stats = await db.get_user_daily_usage_history_by_panel(acc_id, days=7)
    
    if not stats:
        text = get_string('usage_history_no_data', lang)
    else:
        # پرانتزهای موجود در خط زیر باعث خطا می‌شدند
        text = "📊 Usage History (Last 7 Days):\n\n"
        for day in stats:
            d_str = day['date'].strftime("%Y-%m-%d")
            text += f"📅 {d_str}: {day['total_usage']} GB\n"
            
    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn(f"acc_{acc_id}", lang))
    
    # ✅ اصلاح مهم: متن باید escape شود تا پرانتزها درست ارسال شوند
    safe_text = escape_markdown(text)
    await _safe_edit(user_id, call.message.message_id, safe_text, reply_markup=kb, parse_mode='MarkdownV2')

# --- 8. افزودن اکانت (Add) ---
@bot.callback_query_handler(func=lambda call: call.data == "add")
async def add_account_prompt(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(user_menu.back_btn("manage", lang))
    
    await _safe_edit(user_id, call.message.message_id, get_string('prompt_add_uuid', lang), reply_markup=markup)

# --- 9. انتقال ترافیک (Transfer) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('transfer_start_'))
async def transfer_traffic_start(call: types.CallbackQuery):
    user_id = call.from_user.id
    acc_id = int(call.data.split('_')[2])
    # لاجیک انتقال ترافیک را اینجا اضافه کنید یا به هندلر مربوطه ارجاع دهید
    await bot.answer_callback_query(call.id, "این قابلیت به زودی فعال می‌شود.")

# --- 10. صفحه حساب کاربری (User Account) ---
@bot.callback_query_handler(func=lambda call: call.data == "user_account")
async def user_account_page_handler(call: types.CallbackQuery):
    """نمایش صفحه اطلاعات کاربری"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # دریافت متن فرمت شده از formatter
    text = await user_formatter.user_account_page(user_id, lang)
    
    # دکمه بازگشت
    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn("back", lang))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode='MarkdownV2')

# این تابع را اضافه کنید چون در کد شما وجود نداشت
@bot.callback_query_handler(func=lambda call: call.data.startswith('win_select_'))
async def periodic_usage_handler(call: types.CallbackQuery):
    """نمایش آمار مصرف بازه‌ای (هفتگی/ماهانه)"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[2])
    
    # دریافت آمار مصرف
    stats = await db.get_user_daily_usage_history_by_panel(acc_id, days=30)
    
    if not stats:
        text = get_string('usage_history_no_data', lang)
    else:
        total_month = sum(s['total_usage'] for s in stats)
        total_week = sum(s['total_usage'] for s in stats[:7])
        
        text = (
            f"📊 **آمار مصرف بازه‌ای**\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"📅 مصرف ۷ روز گذشته: `{total_week:.2f} GB`\n"
            f"📆 مصرف ۳۰ روز گذشته: `{total_month:.2f} GB`\n"
        )

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn(f"acc_{acc_id}", lang))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode="Markdown")

# این تابع را اضافه کنید چون در کد شما وجود نداشت
@bot.callback_query_handler(func=lambda call: call.data.startswith('win_select_'))
async def periodic_usage_handler(call: types.CallbackQuery):
    """نمایش آمار مصرف بازه‌ای (هفتگی/ماهانه)"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    acc_id = int(call.data.split('_')[2])
    
    # دریافت آمار مصرف
    stats = await db.get_user_daily_usage_history_by_panel(acc_id, days=30)
    
    if not stats:
        text = get_string('usage_history_no_data', lang)
    else:
        total_month = sum(s['total_usage'] for s in stats)
        total_week = sum(s['total_usage'] for s in stats[:7])
        
        text = (
            f"📊 **آمار مصرف بازه‌ای**\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"📅 مصرف ۷ روز گذشته: `{total_week:.2f} GB`\n"
            f"📆 مصرف ۳۰ روز گذشته: `{total_month:.2f} GB`\n"
        )

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn(f"acc_{acc_id}", lang))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode="Markdown")
