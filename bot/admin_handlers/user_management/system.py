# bot/admin_handlers/user_management/system.py

from telebot import types
from bot.database import db
from bot.utils.network import _safe_edit
from bot.keyboards.admin import admin_keyboard as admin_menu

# ایمپورت ماژولار
from bot.admin_handlers.user_management.state import bot

async def handle_system_tools_menu(call, params):
    """منوی ابزارهای سیستم (اگر نیاز باشد)"""
    # این تابع می‌تواند به منوی system_status_menu هدایت کند یا منوی خودش را داشته باشد
    pass 

async def handle_reset_all_daily_usage_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ بله، ریست کن", callback_data="admin:reset_all_daily_usage_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ آیا مصرف روزانه همه کاربران ریست شود؟", reply_markup=kb)

async def handle_reset_all_daily_usage_action(call, params):
    count = await db.delete_all_daily_snapshots()
    await bot.answer_callback_query(call.id, f"✅ {count} رکورد پاک شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_force_snapshot(call, params):
    await bot.answer_callback_query(call.id, "دستور اجرا شد.")

async def handle_reset_all_points_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید", callback_data="admin:reset_all_points_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ صفر کردن امتیازات همه؟", reply_markup=kb)

async def handle_reset_all_points_execute(call, params):
    count = await db.reset_all_achievement_points()
    await bot.answer_callback_query(call.id, f"✅ امتیاز {count} کاربر صفر شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_delete_all_devices_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید حذف", callback_data="admin:delete_all_devices_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ هشدار: حذف تمام دستگاه‌های متصل؟", reply_markup=kb)

async def handle_delete_all_devices_execute(call, params):
    count = await db.delete_all_user_agents()
    await bot.answer_callback_query(call.id, f"✅ {count} دستگاه حذف شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, "✅ انجام شد.", reply_markup=await admin_menu.system_tools_menu())

async def handle_reset_all_balances_confirm(call, params):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⚠️ تایید", callback_data="admin:reset_all_balances_exec"))
    kb.add(types.InlineKeyboardButton("لغو", callback_data="admin:system_tools_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, "⚠️ صفر کردن موجودی کیف پول همه؟", reply_markup=kb)

async def handle_reset_all_balances_execute(call, params):
    count = await db.reset_all_wallet_balances()
    await bot.answer_callback_query(call.id, "✅ انجام شد.")
    await _safe_edit(call.from_user.id, call.message.message_id, f"✅ موجودی {count} کاربر صفر شد.", reply_markup=await admin_menu.system_tools_menu())