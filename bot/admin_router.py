# bot/admin_router.py

import logging
from telebot import types

# ایمپورت دکوریتورها و بات
from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.utils import _safe_edit

# ایمپورت تمام هندلرها
from bot.admin_handlers import (
    user_management,
    panel_management,
    plan_management,
    reporting,
    group_actions,
    broadcast,
    backup,
    wallet as wallet_admin,
    support
)

# اگر هندلرهای هیدیفای و مرزبان جداگانه دارید، آنها را هم ایمپورت کنید
# from bot.admin_handlers import admin_hiddify_handlers, admin_marzban_handlers

logger = logging.getLogger(__name__)

# ===================================================================
# توابع منوهای اصلی (جایگزین توابع داخلی فایل قدیمی)
# ===================================================================

async def _handle_show_panel(call, params):
    """نمایش منوی اصلی پنل مدیریت"""
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "👑 **پنل مدیریت**\n\nلطفاً یک گزینه را انتخاب کنید:", 
        reply_markup=await admin_menu.main()
    )

async def _handle_management_menu(call, params):
    """منوی مدیریت کاربران"""
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "👥 **مدیریت کاربران**\nنوع پنل را انتخاب کنید:", 
        reply_markup=await admin_menu.management_menu()
    )

async def _handle_search_menu(call, params):
    """منوی جستجو"""
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "🔎 **جستجوی کاربر**", 
        reply_markup=await admin_menu.search_menu()
    )

async def _handle_group_actions_menu(call, params):
    """منوی دستورات گروهی"""
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "⚙️ **دستورات گروهی**", 
        reply_markup=await admin_menu.group_actions_menu()
    )

async def _handle_user_analysis_menu(call, params):
    """منوی گزارش پلن‌ها"""
    await reporting.handle_report_by_plan_selection(call, params)

async def _handle_system_status_menu(call, params):
    """منوی وضعیت سیستم"""
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "📊 **وضعیت سیستم**", 
        reply_markup=await admin_menu.system_status_menu()
    )

async def _handle_panel_management_menu(call, params):
    """منوی مدیریت پنل خاص"""
    # پاک کردن استیت‌های قبلی اگر لازم باشد
    # await bot.clear_step_handler_by_chat_id(call.from_user.id)
    panel_type = params[0]
    panel_name = "Hiddify" if panel_type == "hiddify" else "Marzban"
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        f"مدیریت کاربران پنل‌های نوع *{panel_name}*", 
        reply_markup=await admin_menu.panel_management_menu(panel_type)
    )

async def _handle_server_selection(call, params):
    """منوی انتخاب سرور عمومی"""
    base_callback = params[0]
    text = "لطفاً نوع پنل را انتخاب کنید:"
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        text,
        reply_markup=await admin_menu.server_selection_menu(f"admin:{base_callback}")
    )

# ===================================================================
# دیکشنری مسیریابی (Dispatcher Dictionary)
# ===================================================================
# این دیکشنری کلیدهای کالبک (مثل 'panel') را به توابع Async متصل می‌کند

ADMIN_CALLBACK_HANDLERS = {
    # --- Menus ---
    "panel": _handle_show_panel,
    "quick_dashboard": reporting.handle_quick_dashboard,
    "scheduled_tasks": reporting.handle_show_scheduled_tasks,
    "management_menu": _handle_management_menu,
    "manage_panel": _handle_panel_management_menu,
    "select_server": _handle_server_selection,
    "search_menu": _handle_search_menu,
    "group_actions_menu": _handle_group_actions_menu,
    "reports_menu": reporting.handle_reports_menu,
    "panel_reports": reporting.handle_panel_specific_reports_menu,
    "user_analysis_menu": _handle_user_analysis_menu,
    "system_status_menu": _handle_system_status_menu,
    
    # --- Plan Management ---
    "plan_manage": plan_management.handle_plan_management_menu,
    "plan_show_category": plan_management.handle_show_plans_by_category,
    "plan_details": plan_management.handle_plan_details_menu,
    "plan_delete_confirm": plan_management.handle_delete_plan_confirm,
    "plan_delete_execute": plan_management.handle_delete_plan_execute,
    "plan_edit_start": plan_management.handle_plan_edit_start,
    "plan_add_start": plan_management.handle_plan_add_start,
    "plan_add_type": plan_management.get_plan_add_type,
    
    # --- Panel Management ---
    "panel_manage": panel_management.handle_panel_management_menu,
    "panel_details": panel_management.handle_panel_details,
    "panel_add_start": panel_management.handle_start_add_panel,
    "panel_set_type": panel_management.handle_set_panel_type,
    "panel_toggle": panel_management.handle_panel_toggle_status,
    "panel_edit_start": panel_management.handle_panel_edit_start,
    "panel_delete_confirm": panel_management.handle_panel_delete_confirm,
    "panel_delete_execute": panel_management.handle_panel_delete_execute,
    
    # --- User Management (Actions) ---
    # نکته: توابع مربوط به افزودن کاربر هیدیفای/مرزبان را اگر دارید اینجا اضافه کنید
    # "add_user": lambda c, p: (_start_add_hiddify... if p[0] == 'hiddify' else ...),
    
    "sg": user_management.handle_global_search_convo,
    "search_by_tid": user_management.handle_search_by_telegram_id_convo,
    "purge_user": user_management.handle_purge_user_convo,
    
    "us": user_management.handle_show_user_summary,
    "us_edt": user_management.handle_edit_user_menu,
    "ep": user_management.handle_select_panel_for_edit, # Edit Panel Select
    "ae": user_management.handle_ask_edit_value,       # Ask Edit Value
    
    "us_tgl": user_management.handle_toggle_status,
    "tglA": user_management.handle_toggle_status_action,
    
    "us_lpay": user_management.handle_log_payment,
    "us_phist": user_management.handle_payment_history,
    "reset_phist": user_management.handle_reset_payment_history_confirm,
    "do_reset_phist": user_management.handle_reset_payment_history_action,
    
    "us_reset_menu": user_management.handle_user_reset_menu,
    "us_rb": user_management.handle_reset_birthday,
    "us_rusg": user_management.handle_reset_usage_menu,
    "rsa": user_management.handle_reset_usage_action,
    "us_rtr": user_management.handle_reset_transfer_cooldown,
    
    "us_warn_menu": user_management.handle_user_warning_menu,
    "us_spn": user_management.handle_send_payment_reminder,
    "us_sdw": user_management.handle_send_disconnection_warning,
    
    "us_delc": user_management.handle_delete_user_confirm,
    "del_a": user_management.handle_delete_user_action,
    
    "us_note": user_management.handle_ask_for_note,
    
    "us_ddev": user_management.handle_delete_devices_confirm,
    "del_devs_exec": user_management.handle_delete_devices_action,
    
    "us_winback": user_management.manual_winback_handler,
    "churn_contact_user": user_management.handle_churn_contact_user,
    "churn_send_offer": user_management.handle_churn_send_offer,
    
    "renew_sub_menu": user_management.handle_renew_subscription_menu,
    "renew_select_plan": user_management.handle_renew_select_plan_menu,
    "renew_apply_plan": user_management.handle_renew_apply_plan,
    
    # --- Badges & Achievements ---
    "awd_b_menu": user_management.handle_award_badge_menu,
    "awd_b": user_management.handle_award_badge,
    "ach_req_approve": user_management.handle_achievement_request_callback,
    "ach_req_reject": user_management.handle_achievement_request_callback,
    
    # --- Wallet (Admin) ---
    "us_mchg": wallet_admin.handle_manual_charge_request,
    "manual_charge": wallet_admin.handle_manual_charge_request,
    "manual_charge_exec": wallet_admin.handle_manual_charge_execution,
    "manual_charge_cancel": wallet_admin.handle_manual_charge_cancel,
    "us_wdrw": wallet_admin.handle_manual_withdraw_request,
    "manual_withdraw_exec": wallet_admin.handle_manual_withdraw_execution,
    "manual_withdraw_cancel": wallet_admin.handle_manual_withdraw_cancel,
    "charge_confirm": wallet_admin.handle_charge_request_callback,
    "charge_reject": wallet_admin.handle_charge_request_callback,
    
    # --- Reporting ---
    "health_check": reporting.handle_health_check,
    "marzban_stats": reporting.handle_marzban_system_stats,
    "list": reporting.handle_paginated_list,
    "list_devices": reporting.handle_connected_devices_list,
    "list_by_plan": reporting.handle_list_users_by_plan,
    "list_no_plan": reporting.handle_list_users_no_plan,
    
    "financial_report": reporting.handle_financial_report,
    "financial_details": reporting.handle_financial_details,
    "confirm_delete_trans": reporting.handle_confirm_delete_transaction,
    "do_delete_trans": reporting.handle_do_delete_transaction,
    
    # --- Group Actions ---
    "group_action_select_plan": group_actions.handle_select_plan_for_action,
    "ga_select_type": group_actions.handle_select_action_type,
    "ga_ask_value": group_actions.handle_ask_action_value,
    "adv_ga_select_filter": group_actions.handle_select_advanced_filter,
    "adv_ga_select_action": group_actions.handle_select_action_for_filter,
    "ga_confirm": group_actions.ga_execute,
    
    # --- System Tools & Backup ---
    "system_tools_menu": user_management.handle_system_tools_menu,
    "reset_all_daily_usage_confirm": user_management.handle_reset_all_daily_usage_confirm,
    "reset_all_daily_usage_exec": user_management.handle_reset_all_daily_usage_action,
    "force_snapshot": user_management.handle_force_snapshot,
    "reset_all_points_confirm": user_management.handle_reset_all_points_confirm,
    "reset_all_points_exec": user_management.handle_reset_all_points_execute,
    "delete_all_devices_confirm": user_management.handle_delete_all_devices_confirm,
    "delete_all_devices_exec": user_management.handle_delete_all_devices_execute,
    "reset_all_balances_confirm": user_management.handle_reset_all_balances_confirm,
    "reset_all_balances_exec": user_management.handle_reset_all_balances_execute,
    
    "backup_menu": backup.backup_menu_handler,
    "backup": backup.backup_panel_data,
    
    "broadcast": broadcast.start_broadcast_flow,
    "broadcast_target": broadcast.ask_for_broadcast_message,
    "broadcast_confirm": broadcast.broadcast_confirm,
    
    "support_reply": support.prompt_for_reply,
}

# ===================================================================
# Main Callback Handler (The Glue)
# ===================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:"))
async def handle_admin_callbacks(call: types.CallbackQuery):
    """
    این تابع مرکزی تمام کال‌بک‌های ادمین را دریافت کرده و به تابع مناسب هدایت می‌کند.
    """
    try:
        # 1. جدا کردن بخش‌های کالبک
        parts = call.data.split(':')
        action = parts[1] # مثلاً 'panel' یا 'us'
        params = parts[2:] # پارامترهای اضافی
        
        # 2. پیدا کردن هندلر مناسب از دیکشنری
        handler = ADMIN_CALLBACK_HANDLERS.get(action)
        
        if handler:
            # 3. اجرای تابع به صورت Async
            # تمام توابع ما باید async باشند و (call, params) را بپذیرند
            await handler(call, params)
        else:
            logger.warning(f"No handler found for admin action: '{action}' in callback: {call.data}")
            await bot.answer_callback_query(call.id, "❌ دستور نامعتبر یا قدیمی است.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error handling admin callback '{call.data}': {e}", exc_info=True)
        await bot.answer_callback_query(call.id, "❌ خطایی در پردازش درخواست رخ داد.", show_alert=True)

def register_admin_handlers():
    """
    این تابع فقط برای سازگاری با custom_bot.py است.
    چون دکوریتور @bot... در بالا استفاده شده، نیازی به ثبت دستی نیست.
    """
    pass