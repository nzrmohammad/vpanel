# bot/admin_handlers/wallet/manual_manage.py

import logging
import time
from telebot import types
from sqlalchemy import select

from bot.database import db
from bot.db.base import User, UserUUID
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.bot_instance import bot
from bot.admin_handlers.user_management.profile import handle_show_user_summary

logger = logging.getLogger(__name__)

# ==============================================================================
# 💰 بخش اول: شارژ دستی (Manual Charge)
# ==============================================================================

async def handle_manual_charge_request(call: types.CallbackQuery, params: list):
    """شروع پروسه شارژ دستی: درخواست مبلغ"""
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    
    if not hasattr(bot, 'context_state'):
        bot.context_state = {}

    if uid in bot.context_state:
        del bot.context_state[uid]
    
    bot.context_state[uid] = {
        'action_type': 'manual_charge',
        'msg_id': msg_id,
        'identifier': identifier,
        'step': 'get_amount',
        'next_handler': process_charge_amount_step,
        'timestamp': time.time()
    }
    
    msg_text = escape_markdown("💰 لطفاً مبلغ شارژ دستی (تومان) را وارد کنید:")
    
    await _safe_edit(uid, msg_id, msg_text, reply_markup=await admin_menu.cancel_action("admin:manual_charge_cancel"))


async def process_charge_amount_step(message: types.Message):
    """مرحله دریافت مبلغ"""
    uid, text = message.from_user.id, message.text.strip()
    
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    if not hasattr(bot, 'context_state') or uid not in bot.context_state: return
    convo = bot.context_state[uid]
    
    if convo.get('step') != 'get_amount':
        return

    try:
        amount = int(text)
        convo['amount'] = amount
        convo['step'] = 'get_reason'
        convo['next_handler'] = process_charge_reason_step 
        convo['timestamp'] = time.time()
        
        bot.context_state[uid] = convo
        msg_text = escape_markdown("📝 توضیحات تراکنش را وارد کنید:\n(می‌توانید نقطه . بفرستید تا پیش‌فرض ثبت شود)")
        
        await _safe_edit(uid, convo['msg_id'], msg_text, reply_markup=await admin_menu.cancel_action("admin:manual_charge_cancel"))

    except ValueError:
        msg_error = escape_markdown("❌ لطفاً فقط عدد وارد کنید (تومان):")
        await _safe_edit(uid, convo['msg_id'], msg_error, reply_markup=await admin_menu.cancel_action("admin:manual_charge_cancel"))


async def process_charge_reason_step(message: types.Message):
    """مرحله دریافت توضیحات و ثبت"""
    uid, text = message.from_user.id, message.text.strip()
    
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    if not hasattr(bot, 'context_state') or uid not in bot.context_state: return
    convo = bot.context_state[uid]

    if convo.get('step') != 'get_reason':
        return

    reason = text if text != '.' else "شارژ دستی توسط مدیریت"
    amount = convo['amount']
    identifier = convo['identifier']
    msg_id = convo['msg_id']

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
        del bot.context_state[uid]
        return

    try:
        success = await db.update_wallet_balance(
            user_id=target_user_id,
            amount=amount,
            trans_type='admin_deposit',
            description=reason
        )
        
        if success:
            final_msg = (
                f"✅ *کیف پول شارژ شد*\n\n"
                f"👤 کاربر: `{target_user_id}`\n"
                f"💰 مبلغ: `{amount:,}` تومان\n"
                f"📝 بابت: {escape_markdown(reason)}"
            )
            
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"admin:us:{target_user_id}"))
            await _safe_edit(uid, msg_id, final_msg, reply_markup=kb)

            try:
                user_text = (
                    f"🎉 *کیف پول شما شارژ شد*\n\n"
                    f"💳 مبلغ شارژ: `{amount:,}` تومان\n"
                    f"📝 بابت: {escape_markdown(reason)}\n\n"
                    f"✅ هم‌اکنون می‌توانید سرویس مورد نظر خود را خریداری کنید."
                )
                
                user_kb = types.InlineKeyboardMarkup(row_width=1)
                
                user_kb.add(types.InlineKeyboardButton("🛒 خرید سرویس", callback_data="view_plans"))
                user_kb.add(types.InlineKeyboardButton("🏠 منوی اصلی", callback_data="back"))
                
                await bot.send_message(target_user_id, user_text, reply_markup=user_kb, parse_mode='Markdown')
            except Exception as notify_e:
                logger.error(f"Failed to notify user {target_user_id}: {notify_e}")

        else:
            await _safe_edit(uid, msg_id, escape_markdown("❌ خطا در ثبت تراکنش."), reply_markup=await admin_menu.main())

    except Exception as e:
        logger.error(f"Charge Error: {e}")
        await _safe_edit(uid, msg_id, escape_markdown("❌ خطای سیستمی رخ داد."), reply_markup=await admin_menu.main())
    
    # پاکسازی وضعیت ادمین
    if uid in bot.context_state:
        del bot.context_state[uid]


# ==============================================================================
# 💸 بخش دوم: برداشت (Manual Withdraw)
# ==============================================================================

async def handle_manual_withdraw_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    
    if not hasattr(bot, 'context_state'): bot.context_state = {}
    if uid in bot.context_state: del bot.context_state[uid]

    try: user_id = int(identifier)
    except: return

    async with db.get_session() as session:
        user = await session.get(User, user_id)
        if not user: return
        balance = user.wallet_balance or 0.0

    if balance <= 0:
        await bot.answer_callback_query(call.id, "موجودی صفر/منفی است.", show_alert=True)
        return

    bot.context_state[uid] = {
        'action_type': 'manual_withdraw',
        'msg_id': msg_id,
        'target_user_id': user_id,
        'current_balance': balance,
        'timestamp': time.time()
    }
    
    prompt = (f"موجودی فعلی کاربر *{escape_markdown(user.first_name or 'User')}* مبلغ *{balance:,.0f} تومان* است\\.\n\n"
              f"آیا از صفر کردن موجودی اطمینان دارید؟")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ بله، صفر کن", callback_data="admin:manual_withdraw_exec"),
        types.InlineKeyboardButton("❌ خیر", callback_data="admin:manual_withdraw_cancel")
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_manual_withdraw_execution(call: types.CallbackQuery, params: list):
    uid = call.from_user.id
    if not hasattr(bot, 'context_state') or uid not in bot.context_state: 
        await bot.answer_callback_query(call.id, "نشست منقضی شده است.")
        return
        
    convo = bot.context_state.pop(uid, {})
    amount = convo.get('current_balance', 0.0)
    target_user_id = convo.get('target_user_id')
    msg_id = convo.get('msg_id')
    
    success = await db.update_wallet_balance(
        user_id=target_user_id, 
        amount=-amount,
        trans_type='admin_withdraw', 
        description="صفر کردن توسط مدیریت"
    )

    if success:
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت", callback_data=f"admin:us:{target_user_id}"))
        msg = escape_markdown("✅ موجودی کاربر با موفقیت صفر شد.")
        await _safe_edit(uid, msg_id, msg, reply_markup=kb)
        
        try:
             await bot.send_message(target_user_id, "ℹ️ موجودی کیف پول شما توسط مدیریت صفر شد.")
        except: pass
    else:
        msg = escape_markdown("❌ خطا در دیتابیس.")
        await _safe_edit(uid, msg_id, msg, reply_markup=await admin_menu.main())


# ==============================================================================
# ❌ دکمه لغو عملیات (بازگشت سریع)
# ==============================================================================

async def handle_wallet_cancel_action(call: types.CallbackQuery, params: list):
    """پاکسازی وضعیت و بازگشت آنی به پروفایل کاربر"""
    uid = call.from_user.id
    
    target_id = None
    if hasattr(bot, 'context_state') and uid in bot.context_state:
        state = bot.context_state[uid]
        target_id = state.get('identifier') or state.get('target_user_id')
        del bot.context_state[uid]
    
    await bot.answer_callback_query(call.id, "❌ عملیات لغو شد.", show_alert=False)

    if target_id:
        await handle_show_user_summary(call, [str(target_id)])
    else:
        msg = escape_markdown("❌ عملیات لغو شد.")
        await _safe_edit(uid, call.message.message_id, msg, reply_markup=await admin_menu.main())