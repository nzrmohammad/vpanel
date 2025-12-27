# bot/admin_handlers/wallet/manual_manage.py

import logging
from telebot import types
from sqlalchemy import select
from bot.database import db
from bot.db.base import User
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards import admin as admin_menu
from bot.bot_instance import bot
from .states import admin_conversations

logger = logging.getLogger(__name__)

# --- بخش اول: شارژ دستی (Manual Charge) ---

async def handle_manual_charge_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    
    admin_conversations[uid] = {
        'action_type': 'manual_charge',
        'msg_id': msg_id,
        'identifier': identifier,
        'next_handler': _get_manual_charge_amount
    }
    
    back_cb = f"admin:user_details:{identifier}" if identifier.isdigit() else "admin:user_manage"
    await _safe_edit(uid, msg_id, "💰 لطفاً مبلغ شارژ دستی (تومان) را وارد کنید:", reply_markup=await admin_menu.cancel_action(back_cb))

async def _get_manual_charge_amount(message: types.Message):
    admin_id, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(admin_id, message.message_id)
    except: pass

    if admin_id not in admin_conversations: return
    convo = admin_conversations[admin_id]
    
    try:
        amount = float(text)
        convo['amount'] = amount
        
        async with db.get_session() as session:
            identifier = convo['identifier']
            user = None
            if identifier.isdigit():
                user = await session.get(User, int(identifier))
            if not user:
                from bot.db.base import UserUUID
                stmt = select(User).outerjoin(UserUUID).where((User.username == identifier) | (UserUUID.uuid == identifier)).limit(1)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
            
            if not user:
                await _safe_edit(admin_id, convo['msg_id'], "❌ کاربر یافت نشد.", reply_markup=await admin_menu.main())
                return

            convo['target_user_id'] = user.user_id
            user_name = user.first_name or user.username or "کاربر"
        
        confirm_prompt = (f"❓ آیا از شارژ کیف پول کاربر *{escape_markdown(user_name)}* \n"
                          f"به مبلغ *{amount:,.0f} تومان* اطمینان دارید؟")
        
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ بله، تایید", callback_data="admin:manual_charge_exec"),
            types.InlineKeyboardButton("❌ خیر، لغو", callback_data="admin:manual_charge_cancel")
        )
        await _safe_edit(admin_id, convo['msg_id'], confirm_prompt, reply_markup=kb)

    except ValueError:
        await _safe_edit(admin_id, convo['msg_id'], "❌ مقدار نامعتبر. لطفاً عدد وارد کنید.", reply_markup=await admin_menu.cancel_action("admin:panel"))

async def handle_manual_charge_execution(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id, {})
    target_user_id = convo.get('target_user_id')
    amount = convo.get('amount')

    if target_user_id and amount:
        if await db.update_wallet_balance(target_user_id, amount, 'deposit', "شارژ دستی توسط مدیریت"):
            kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت به پروفایل", callback_data=f"admin:us:{target_user_id}"))
            await _safe_edit(admin_id, convo['msg_id'], f"✅ شارژ موفق: *{amount:,.0f} تومان*", reply_markup=kb)
        else:
            await _safe_edit(admin_id, convo['msg_id'], "❌ خطا در عملیات.", reply_markup=await admin_menu.main())

async def handle_manual_charge_cancel(call: types.CallbackQuery, params: list):
    uid = call.from_user.id
    if uid in admin_conversations: del admin_conversations[uid]
    await _safe_edit(uid, call.message.message_id, "❌ عملیات لغو شد.", reply_markup=await admin_menu.main())


# --- بخش دوم: برداشت/صفر کردن (Manual Withdraw) ---

async def handle_manual_withdraw_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    try: user_id = int(identifier)
    except: return

    async with db.get_session() as session:
        user = await session.get(User, user_id)
        if not user: return
        balance = user.wallet_balance or 0.0

    if balance <= 0:
        await bot.answer_callback_query(call.id, "موجودی صفر/منفی است.", show_alert=True)
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
        types.InlineKeyboardButton("❌ خیر", callback_data="admin:manual_withdraw_cancel")
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_manual_withdraw_execution(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    convo = admin_conversations.pop(admin_id, {})
    amount = convo.get('current_balance', 0.0)
    target_user_id = convo.get('target_user_id')
    
    if await db.update_wallet_balance(target_user_id, -amount, 'withdraw', "برداشت توسط مدیریت"):
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت", callback_data=f"admin:us:{target_user_id}"))
        await _safe_edit(admin_id, convo['msg_id'], "✅ موجودی کاربر صفر شد.", reply_markup=kb)
    else:
        await _safe_edit(admin_id, convo['msg_id'], "❌ خطا در دیتابیس.", reply_markup=await admin_menu.main())

async def handle_manual_withdraw_cancel(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id in admin_conversations:
        convo = admin_conversations.pop(admin_id)
        back = f"admin:us:{convo.get('target_user_id')}"
        await _safe_edit(admin_id, convo.get('msg_id'), "❌ لغو شد.", reply_markup=await admin_menu.cancel_action(back))