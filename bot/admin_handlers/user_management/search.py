# bot/admin_handlers/user_management/search.py

import time
from telebot import types
from sqlalchemy import select, or_, cast, String  # ✅ اضافه شدن cast و String
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot  # ایمپورت بات اصلی
from bot.admin_handlers.user_management import state  # ایمپورت ماژول state
from bot.admin_handlers.user_management.helpers import _delete_user_message
from bot.admin_handlers.user_management.profile import show_user_summary

from bot.database import db
from bot.db.base import User, UserUUID
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

# ==============================================================================
# مدیریت منو اصلی (اختیاری اگر در navigation نباشد)
# ==============================================================================
async def handle_management_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی مدیریت"""
    uid, msg_id = call.from_user.id, call.message.message_id
    from bot.database import db 
    active_panels = await db.get_active_panels()
    
    markup = await admin_menu.management_menu(active_panels)
    await _safe_edit(uid, msg_id, "مدیریت کاربران:", reply_markup=markup)

async def handle_search_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی انتخاب روش جستجو"""
    uid, msg_id = call.from_user.id, call.message.message_id
    prompt = "🔍 لطفاً روش جستجو را انتخاب کنید:"
    markup = await admin_menu.search_menu()
    await _safe_edit(uid, msg_id, prompt, reply_markup=markup)

# ==============================================================================
# لاجیک جستجو
# ==============================================================================

async def handle_global_search_convo(call, params):
    """شروع جستجوی کاربر با نام، یوزرنیم یا UUID"""
    uid, msg_id = call.from_user.id, call.message.message_id
    state.admin_conversations[uid] = {
        'step': 'global_search', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_search_input
    }
    
    text = r"🔎 لطفاً *نام*، *نام کاربری* یا بخشی از *UUID* کاربر را ارسال کنید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def handle_search_by_telegram_id_convo(call, params):
    """شروع جستجو با آیدی عددی تلگرام"""
    uid, msg_id = call.from_user.id, call.message.message_id
    state.admin_conversations[uid] = {
        'step': 'tid_search', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_search_input
    }
    
    text = "🆔 لطفاً *آیدی عددی تلگرام* کاربر را ارسال کنید:"
    
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def process_search_input(message: types.Message):
    """پردازش ورودی جستجو"""
    uid, query = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in state.admin_conversations: return
    data = state.admin_conversations.pop(uid)
    msg_id = data['msg_id']
    step = data['step']
    
    async with db.get_session() as session:
        stmt = select(User).distinct().options(selectinload(User.uuids))
        
        if step == 'tid_search':
            if not query.isdigit():
                await _safe_edit(uid, msg_id, "❌ آیدی باید عدد باشد.", reply_markup=await admin_menu.search_menu())
                return
            stmt = stmt.where(User.user_id == int(query))
        else:
            # ✅ اصلاح شده: تبدیل UUID به String برای قابلیت جستجو با ILIKE
            stmt = stmt.outerjoin(UserUUID).where(
                or_(
                    User.username.ilike(f"%{query}%"),
                    User.first_name.ilike(f"%{query}%"),
                    User.last_name.ilike(f"%{query}%"),
                    cast(UserUUID.uuid, String).ilike(f"%{query}%"), # تبدیل به متن
                    UserUUID.name.ilike(f"%{query}%")
                )
            )
        
        result = await session.execute(stmt)
        users = result.scalars().all()

    if not users:
        safe_query = escape_markdown(query)
        await _safe_edit(uid, msg_id, rf"❌ کاربری با مشخصات «{safe_query}» یافت نشد\.", reply_markup=await admin_menu.search_menu())
        return
    
    if len(users) == 1:
        # نمایش مستقیم پروفایل
        await show_user_summary(uid, msg_id, users[0].user_id)
    else:
        # نمایش لیست انتخاب
        safe_query = escape_markdown(query)
        text = rf"🔍 نتایج جستجو برای `{safe_query}` \({len(users)} مورد\):"
        kb = types.InlineKeyboardMarkup(row_width=1)
        for u in users[:10]:
            display = f"{u.first_name or 'NoName'} (@{u.username or 'NoUser'})"
            # پارامتر s انتهای کالبک یعنی Context=Search
            kb.add(types.InlineKeyboardButton(display, callback_data=f"admin:us:{u.user_id}:s"))
        
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:search_menu"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# ==============================================================================
# لاجیک حذف کامل (Purge)
# ==============================================================================

async def handle_purge_user_convo(call, params):
    """شروع پروسه حذف کامل (Purge) با آیدی"""
    uid, msg_id = call.from_user.id, call.message.message_id
    state.admin_conversations[uid] = {
        'step': 'purge_user', 
        'msg_id': msg_id,
        'timestamp': time.time(),
        'next_handler': process_purge_user
    }
    text = r"🔥 برای *پاکسازی کامل* \(حذف از دیتابیس\)، آیدی عددی کاربر را بفرستید:"
    await _safe_edit(uid, msg_id, text, reply_markup=await admin_menu.cancel_action("admin:search_menu"))

async def process_purge_user(message: types.Message):
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    if uid not in state.admin_conversations: return
    msg_id = state.admin_conversations.pop(uid)['msg_id']
    
    if not text.isdigit():
        await _safe_edit(uid, msg_id, "❌ آیدی نامعتبر.", reply_markup=await admin_menu.search_menu())
        return
        
    target_id = int(text)
    success = await db.purge_user_by_telegram_id(target_id)
    if success:
        msg_text = escape_markdown(f"✅ کاربر {target_id} با موفقیت کامل پاکسازی شد.")
        await _safe_edit(uid, msg_id, msg_text, reply_markup=await admin_menu.search_menu())
    else:
        msg_text = escape_markdown("❌ کاربر یافت نشد یا خطا در حذف.")
        await _safe_edit(uid, msg_id, msg_text, reply_markup=await admin_menu.search_menu())