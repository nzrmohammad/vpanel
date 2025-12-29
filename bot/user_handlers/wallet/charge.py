# bot/user_handlers/wallet/charge.py

import logging
from telebot import types
from bot.bot_instance import bot
from bot.keyboards.user import user_keyboard as user_menu
from bot.database import db
from bot.language import get_string
from bot.formatters import user_formatter
from bot.utils.formatters import escape_markdown
from .states import user_payment_states

logger = logging.getLogger(__name__)

# --- 1. هندلر ورودی‌های متنی و عکس (Dispatcher) ---
@bot.message_handler(content_types=['text', 'photo'], func=lambda m: m.from_user.id in user_payment_states)
async def wallet_input_handler(message: types.Message):
    user_id = message.from_user.id
    state = user_payment_states.get(user_id)
    if not state: return

    step = state.get('step')
    if step == 'waiting_amount':
        await process_charge_amount(message)
    elif step == 'waiting_receipt':
        await process_receipt_upload(message)

# --- 2. شروع پروسه شارژ ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:charge")
async def wallet_charge_start(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    methods = await db.get_payment_methods(active_only=True)
    if not methods:
        await bot.answer_callback_query(call.id, "❌ روش پرداختی فعال نیست.", show_alert=True)
        return

    text = "💰 *شارژ کیف پول*\n\nلطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\nمثال: `50000`"
    kb = types.InlineKeyboardMarkup()
    kb = await user_menu.user_cancel_action("wallet:main", lang)
    
    msg = await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=kb, parse_mode='MarkdownV2')
    user_payment_states[user_id] = {'step': 'waiting_amount', 'msg_id': msg.message_id}

# --- 3. پردازش مبلغ وارد شده ---
async def process_charge_amount(message: types.Message):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    state = user_payment_states[user_id]
    prev_msg_id = state['msg_id']

    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    if not message.text or not message.text.replace(',', '').isdigit():
        # خطا: فرمت نامعتبر
        # (برای خلاصه شدن کد خطا را ساده کردم، می‌توانید متن کامل را از قبل کپی کنید)
        return

    amount = int(message.text.replace(',', ''))
    if amount < 5000:
        # خطا: حداقل مبلغ
        return

    state['amount'] = amount
    state['step'] = 'select_method'
    
    methods = await db.get_payment_methods(active_only=True)
    markup = await user_menu.payment_options_menu(lang, methods, back_callback="wallet:charge")
    text = f"💳 مبلغ قابل پرداخت: *{amount:,} تومان*\n\nلطفاً روش پرداخت را انتخاب کنید:"
    await bot.edit_message_text(text, user_id, prev_msg_id, reply_markup=markup, parse_mode='MarkdownV2')

# --- 4. انتخاب روش پرداخت و نمایش اطلاعات ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("payment:select:"))
async def show_payment_details(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    if user_id not in user_payment_states:
        await bot.answer_callback_query(call.id, "نشست منقضی شده.")
        return

    method_id = int(call.data.split(":")[2])
    methods = await db.get_payment_methods(active_only=True)
    selected = next((m for m in methods if m['id'] == method_id), None)
    
    if not selected:
        await bot.answer_callback_query(call.id, "روش پرداخت یافت نشد.", show_alert=True)
        return

    text = user_formatter.payment_details_text(selected)
    kb = await user_menu.user_cancel_action("wallet:main", lang)

    try:
        await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=kb, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error in show_payment_details: {e}")
        # در صورت خطا، فرمت‌دهی را حذف کن تا پیام حداقل ارسال شود
        fallback_text = text.replace('*', '').replace('\\', '').replace('`', '')
        await bot.edit_message_text(fallback_text, user_id, call.message.message_id, reply_markup=kb)
        
    user_payment_states[user_id]['step'] = 'waiting_receipt'

# --- 5. پردازش رسید و ارسال به ادمین (تاپیک دار) ---
async def process_receipt_upload(message: types.Message):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    state = user_payment_states.get(user_id)
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass

    if message.content_type != 'photo':
        await bot.send_message(user_id, "⚠️ لطفاً فقط تصویر رسید را ارسال کنید.")
        return

    amount = state['amount']
    wait_text = "✅ رسید شما دریافت شد\\. پس از تایید توسط ادمین، حساب شما شارژ خواهد شد\\."
    kb = await user_menu.simple_back_menu("wallet:main", lang)
    
    try: await bot.edit_message_text(wait_text, user_id, state['msg_id'], reply_markup=kb, parse_mode='MarkdownV2')
    except: await bot.send_message(user_id, wait_text, reply_markup=kb, parse_mode='MarkdownV2')
    
    # ثبت در دیتابیس
    req_id = await db.create_charge_request(user_id, amount, state['msg_id'])
    
    # دریافت تنظیمات کانال و تاپیک
    main_group_id = await db.get_config('main_group_id')
    topic_id_proof = await db.get_config('topic_id_proof')
    
    if main_group_id and str(main_group_id) != '0':
        chat_id = int(main_group_id)
        thread_id = int(topic_id_proof) if topic_id_proof and str(topic_id_proof) != '0' else None
        
        await send_receipt_to_admin(message, req_id, amount, user_id, chat_id, thread_id)
    
    # پایان: حذف استیت
    del user_payment_states[user_id]

async def send_receipt_to_admin(message, req_id, amount, user_id, chat_id, thread_id):
    user_data = await db.user(user_id)
    caption = (
        f"💸 *درخواست شارژ جدید*\n"
        f"🆔 شناسه: `{req_id}`\n"
        f"👤 کاربر: {escape_markdown(user_data.get('first_name', 'Unknown'))}\n"
        f"💰 مبلغ: *{amount:,} تومان*"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin:charge_req:confirm:{req_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin:charge_req:reject:{req_id}")
    )
    await bot.send_photo(
        chat_id=chat_id, 
        message_thread_id=thread_id, # ارسال به تاپیک
        photo=message.photo[-1].file_id, 
        caption=caption, 
        reply_markup=markup, 
        parse_mode='MarkdownV2'
    )