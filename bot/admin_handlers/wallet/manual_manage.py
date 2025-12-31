# bot/admin_handlers/wallet/manual_manage.py

import logging
from telebot import types
from sqlalchemy import select

from bot.database import db
from bot.db.base import User, UserUUID
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

# ✅ ایمپورت صحیح
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.bot_instance import bot
from .states import admin_conversations

logger = logging.getLogger(__name__)

# ==============================================================================
# 💰 بخش اول: شارژ دستی (Manual Charge)
# ==============================================================================

async def handle_manual_charge_request(call: types.CallbackQuery, params: list):
    """شروع پروسه شارژ دستی: درخواست مبلغ"""
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    
    # 1. پاکسازی اجباری وضعیت‌های قبلی
    if uid in admin_conversations:
        del admin_conversations[uid]
    
    # 2. تنظیم وضعیت جدید
    admin_conversations[uid] = {
        'action_type': 'manual_charge',
        'msg_id': msg_id,
        'identifier': identifier,
        'step': 'get_amount',
        'next_handler': process_charge_amount_step
    }
    
    # تعیین دکمه بازگشت
    back_cb = f"admin:wallet_menu:{identifier}"
    
    msg_text = escape_markdown("💰 لطفاً مبلغ شارژ دستی (تومان) را وارد کنید:")
    
    await _safe_edit(uid, msg_id, msg_text, reply_markup=await admin_menu.cancel_action(back_cb))


async def process_charge_amount_step(message: types.Message):
    """مرحله دریافت مبلغ و درخواست توضیحات"""
    uid, text = message.from_user.id, message.text.strip()
    
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    if uid not in admin_conversations: return
    convo = admin_conversations[uid]
    
    if convo.get('step') != 'get_amount':
        return

    try:
        amount = int(text)
        convo['amount'] = amount
        convo['step'] = 'get_reason'
        convo['next_handler'] = process_charge_reason_step # ارجاع به مرحله بعد
        
        admin_conversations[uid] = convo

        msg_text = escape_markdown("📝 توضیحات تراکنش را وارد کنید:\n(می‌توانید نقطه . بفرستید تا پیش‌فرض ثبت شود)")
        
        await _safe_edit(uid, convo['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:cancel_wallet_action"))

    except ValueError:
        msg_error = escape_markdown("❌ لطفاً فقط عدد وارد کنید (تومان):")
        back_cb = f"admin:wallet_menu:{convo.get('identifier')}"
        await _safe_edit(uid, convo['msg_id'], msg_error, reply_markup=await admin_menu.cancel_action(back_cb))


async def process_charge_reason_step(message: types.Message):
    """مرحله دریافت توضیحات و انجام تراکنش"""
    uid, text = message.from_user.id, message.text.strip()
    
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    if uid not in admin_conversations: return
    convo = admin_conversations[uid]

    if convo.get('step') != 'get_reason':
        return

    reason = text
    if reason == '.':
        reason = "شارژ دستی توسط مدیریت"

    amount = convo['amount']
    identifier = convo['identifier']
    msg_id = convo['msg_id']

    # پیدا کردن یوزر آیدی واقعی
    target_user_id = None
    if str(identifier).isdigit():
        target_user_id = int(identifier)
    else:
        async with db.get_session() as session:
            stmt = select(UserUUID.user_id).where(UserUUID.uuid == str(identifier))
            res = await session.execute(stmt)
            target_user_id = res.scalar_one_or_none()

    if not target_user_id:
        await _safe_edit(uid, msg_id, escape_markdown("❌ کاربر یافت نشد."), reply_markup=await admin_menu.main())
        del admin_conversations[uid]
        return

    try:
        success = await db.update_wallet_balance(
            user_id=target_user_id,
            amount=amount,
            transaction_type='admin_deposit',
            description=reason
        )
        
        if success:
            final_msg = (
                f"✅ *کیف پول شارژ شد*\n\n"
                f"👤 کاربر: `{target_user_id}`\n"
                f"💰 مبلغ: `{amount:,}` تومان\n"
                f"📝 بابت: {escape_markdown(reason)}"
            )
            
            back_cb = f"admin:wallet_menu:{identifier}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 بازگشت به کیف پول", callback_data=back_cb))
            
            await _safe_edit(uid, msg_id, final_msg, reply_markup=kb)
        else:
            await _safe_edit(uid, msg_id, escape_markdown("❌ خطا در ثبت تراکنش."), reply_markup=await admin_menu.main())

    except Exception as e:
        logger.error(f"Charge Error: {e}")
        await _safe_edit(uid, msg_id, escape_markdown("❌ خطای سیستمی رخ داد."), reply_markup=await admin_menu.main())
    
    if uid in admin_conversations:
        del admin_conversations[uid]


# ==============================================================================
# 💸 بخش دوم: برداشت/صفر کردن (Manual Withdraw)
# ==============================================================================

async def handle_manual_withdraw_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    
    if uid in admin_conversations:
        del admin_conversations[uid]

    try: user_id = int(identifier)
    except: return

    async with db.get_session() as session:
        user = await session.get(User, user_id)
        if not user: return
        balance = user.wallet_balance or 0.0

    if balance <= 0:
        await bot.answer_callback_query(call.id, "موجودی کاربر صفر یا منفی است.", show_alert=True)
        return

    admin_conversations[uid] = {
        'action_type': 'manual_withdraw',
        'msg_id': msg_id,
        'target_user_id': user_id,
        'current_balance': balance
    }
    
    prompt = (f"موجودی فعلی کاربر *{escape_markdown(user.first_name or 'User')}* مبلغ *{balance:,.0f} تومان* است\\.\n\n"
              f"آیا از صفر کردن موجودی اطمینان دارید؟")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ بله، صفر کن", callback_data="admin:manual_withdraw_exec"),
        types.InlineKeyboardButton("❌ خیر", callback_data="admin:cancel_wallet_action")
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_manual_withdraw_execution(call: types.CallbackQuery, params: list):
    uid = call.from_user.id
    if uid not in admin_conversations: 
        await bot.answer_callback_query(call.id, "نشست منقضی شده است.")
        return
        
    convo = admin_conversations.pop(uid, {})
    amount = convo.get('current_balance', 0.0)
    target_user_id = convo.get('target_user_id')
    msg_id = convo.get('msg_id')
    
    success = await db.update_wallet_balance(
        user_id=target_user_id, 
        amount=-amount,
        transaction_type='admin_withdraw', 
        description="صفر کردن توسط مدیریت"
    )

    if success:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت", callback_data=f"admin:us:{target_user_id}"))
        msg = escape_markdown("✅ موجودی کاربر با موفقیت صفر شد.")
        await _safe_edit(uid, msg_id, msg, reply_markup=kb)
    else:
        msg = escape_markdown("❌ خطا در دیتابیس.")
        await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.main())


# ==============================================================================
# ❌ دکمه لغو عملیات (مشترک)
# ==============================================================================

async def handle_wallet_cancel_action(call: types.CallbackQuery, params: list):
    """پاکسازی کامل وضعیت هنگام زدن دکمه لغو"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    
    if uid in admin_conversations:
        del admin_conversations[uid]
    
    msg = escape_markdown("❌ عملیات لغو شد.")
    await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.main())

# ==============================================================================
# ⚠️ بخش سازگاری (Compatibility)
# این بخش برای جلوگیری از ارور ImportError اضافه شده است
# ==============================================================================

async def handle_manual_charge_execution(call, params):
    """(منسوخ شده) دیگر استفاده نمی‌شود ولی برای ایمپورت‌های قدیمی نگه داشته شده."""
    pass

# الیاس‌ها برای توابعی که نامشان عوض شده
handle_manual_charge_cancel = handle_wallet_cancel_action
handle_manual_withdraw_cancel = handle_wallet_cancel_action