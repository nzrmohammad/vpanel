# bot/admin_router.py

import logging
from telebot import types

# 1. Imports
from .bot_instance import bot
from .utils import _safe_edit, initialize_utils

# 2. Import Handlers
from .admin_handlers import (
    user_management, 
    reporting, 
    broadcast, 
    backup, 
    group_actions, 
    plan_management, 
    panel_management,
    support,
    wallet as wallet_admin,
    navigation, # ✅ اضافه شده
    debug       # ✅ اضافه شده
)

# 3. Hiddify/Marzban specific imports (اگر هنوز نیاز دارید به صورت جداگانه باشند)
from .admin_hiddify_handlers import _start_add_hiddify_user_convo, initialize_hiddify_handlers, handle_add_user_back_step
from .admin_marzban_handlers import _start_add_marzban_user_convo, initialize_marzban_handlers

logger = logging.getLogger(__name__)

# دیکشنری مشترک برای مدیریت وضعیت مکالمات ادمین
shared_admin_conversations = {}

def register_admin_handlers(bot_instance, scheduler_instance):
    """
    تابع اصلی برای راه‌اندازی تمام هندلرهای ادمین
    """
    # فعال‌سازی ابزارهای کمکی
    initialize_utils(bot_instance)

    # 4. Initialize Sub-Handlers with shared state
    # پاس دادن bot و دیکشنری وضعیت به ماژول‌های دیگر
    initialize_hiddify_handlers(bot_instance, shared_admin_conversations)
    initialize_marzban_handlers(bot_instance, shared_admin_conversations)
    
    group_actions.initialize_group_actions_handlers(bot_instance, shared_admin_conversations) if hasattr(group_actions, 'initialize_group_actions_handlers') else None
    user_management.initialize_user_management_handlers(bot_instance, shared_admin_conversations)
    plan_management.initialize_plan_management_handlers(bot_instance, shared_admin_conversations)
    panel_management.initialize_panel_management_handlers(bot_instance, shared_admin_conversations)
    wallet_admin.initialize_wallet_handlers(bot_instance, shared_admin_conversations)
    support.initialize_support_handlers(bot_instance, shared_admin_conversations)
    
    # Broadcast و Reporting ممکن است نیاز به init خاصی نداشته باشند یا متفاوت باشند
    # broadcast.initialize_broadcast_handlers(...) 
    
    # ثبت دستورات دیباگ (test, addpoints, ...)
    debug.register_debug_handlers(bot_instance, scheduler_instance)

# ===================================================================
# 5. Global Step Handler (حیاتی برای AsyncTeleBot)
# ===================================================================
@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice'])
async def global_step_handler(message: types.Message):
    """
    مدیریت مراحل مکالمه (State Machine) برای ادمین‌ها.
    جایگزین register_next_step_handler در نسخه Async.
    """
    uid = message.from_user.id
    
    if uid in shared_admin_conversations:
        step_data = shared_admin_conversations[uid]
        next_func = step_data.get('next_handler') # تابعی که باید اجرا شود
        
        if next_func:
            # اجرای تابع مرحله بعد
            await next_func(message)
            return

# ===================================================================
# 6. Dispatcher Dictionary (Routing Map)
# ===================================================================
ADMIN_CALLBACK_HANDLERS = {
    # --- Navigation Menus (Moved to navigation.py) ---
    "panel": navigation.handle_show_panel,
    "management_menu": navigation.handle_management_menu,
    "search_menu": navigation.handle_search_menu,
    "group_actions_menu": navigation.handle_group_actions_menu,
    "user_analysis_menu": navigation.handle_user_analysis_menu,
    "system_status_menu": navigation.handle_system_status_menu,
    "manage_panel": navigation.handle_panel_management_menu,
    "select_server": navigation.handle_server_selection,
    "add_user_back": handle_add_user_back_step,

    # --- Reporting & Dashboard ---
    "quick_dashboard": reporting.handle_quick_dashboard,
    "scheduled_tasks": reporting.handle_show_scheduled_tasks,
    "reports_menu": reporting.handle_reports_menu,
    "panel_reports": reporting.handle_panel_specific_reports_menu,
    "health_check": reporting.handle_health_check,
    "marzban_stats": reporting.handle_marzban_system_stats,
    "list": reporting.handle_paginated_list,
    "financial_report": reporting.handle_financial_report,
    "financial_details": reporting.handle_financial_details,
    "list_devices": reporting.handle_connected_devices_list,
    "report_by_plan_select": reporting.handle_report_by_plan_selection,
    "list_by_plan": reporting.handle_list_users_by_plan,
    "list_no_plan": reporting.handle_list_users_no_plan,

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
    "add_user": lambda c, p: (_start_add_hiddify_user_convo if p[0] == 'hiddify' else _start_add_marzban_user_convo)(c.from_user.id, c.message.message_id),
    "sg": user_management.handle_global_search_convo,
    "search_by_tid": user_management.handle_search_by_telegram_id_convo,
    "purge_user": user_management.handle_purge_user_convo,
    
    "us": user_management.handle_show_user_summary,
    "us_edt": user_management.handle_edit_user_menu,
    "ep": user_management.handle_select_panel_for_edit,
    "ae": user_management.handle_ask_edit_value,
    
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
    "us_ddev": user_management.handle_delete_devices_confirm,
    "del_devs_exec": user_management.handle_delete_devices_action,
    "us_note": user_management.handle_ask_for_note,

    "renew_sub_menu": user_management.handle_renew_subscription_menu,
    "renew_select_plan": user_management.handle_renew_select_plan_menu,
    "renew_apply_plan": user_management.handle_renew_apply_plan,

    "churn_contact_user": user_management.handle_churn_contact_user,
    "churn_send_offer": user_management.handle_churn_send_offer,

    # --- Wallet & Finance ---
    "financial_report": reporting.handle_financial_report,
    "financial_details": reporting.handle_financial_details,
    "confirm_delete_trans": reporting.handle_confirm_delete_transaction,
    "do_delete_trans": reporting.handle_do_delete_transaction,
    
    "us_mchg": wallet_admin.handle_manual_charge_request,
    "manual_charge": wallet_admin.handle_manual_charge_request,
    "manual_charge_exec": wallet_admin.handle_manual_charge_execution,
    "manual_charge_cancel": wallet_admin.handle_manual_charge_cancel,
    "us_wdrw": wallet_admin.handle_manual_withdraw_request,
    "manual_withdraw_exec": wallet_admin.handle_manual_withdraw_execution,
    "manual_withdraw_cancel": wallet_admin.handle_manual_withdraw_cancel,
    
    "charge_confirm": wallet_admin.handle_charge_request_callback,
    "charge_reject": wallet_admin.handle_charge_request_callback,
    "reset_all_balances_confirm": user_management.handle_reset_all_balances_confirm,
    "reset_all_balances_exec": user_management.handle_reset_all_balances_execute,

    # --- Group Actions ---
    "group_action_select_plan": group_actions.handle_select_plan_for_action,
    "ga_select_type": group_actions.handle_select_action_type,
    "ga_ask_value": group_actions.handle_ask_action_value,
    "adv_ga_select_filter": group_actions.handle_select_advanced_filter,
    "adv_ga_select_action": group_actions.handle_select_action_for_filter,

    # --- Badges & Support ---
    "awd_b_menu": user_management.handle_award_badge_menu,
    "awd_b": user_management.handle_award_badge,
    "ach_req_approve": user_management.handle_achievement_request_callback,
    "ach_req_reject": user_management.handle_achievement_request_callback,
    "support_reply": support.prompt_for_reply,

    # --- System Tools & Backup ---
    "system_tools_menu": user_management.handle_system_tools_menu,
    "reset_all_daily_usage_confirm": user_management.handle_reset_all_daily_usage_confirm,
    "reset_all_daily_usage_exec": user_management.handle_reset_all_daily_usage_action,
    "force_snapshot": user_management.handle_force_snapshot,
    "reset_all_points_confirm": user_management.handle_reset_all_points_confirm,
    "reset_all_points_exec": user_management.handle_reset_all_points_execute,
    "delete_all_devices_confirm": user_management.handle_delete_all_devices_confirm,
    "delete_all_devices_exec": user_management.handle_delete_all_devices_execute,
    
    "broadcast": broadcast.start_broadcast_flow,
    "broadcast_target": broadcast.ask_for_broadcast_message,
    "backup_menu": backup.handle_backup_menu,
    "backup": backup.handle_backup_action,
}

# ===================================================================
# 7. Main Callback Handler
# ===================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:"))
async def handle_admin_callbacks(call: types.CallbackQuery):
    """
    هندلر مرکزی تمام دکمه‌های شیشه‌ای ادمین.
    کالبک را پارس کرده و به تابع مربوطه در دیکشنری هدایت می‌کند.
    """
    try:
        # 1. جدا کردن بخش‌ها
        parts = call.data.split(':')
        if len(parts) < 2: 
            return # فرمت اشتباه است
            
        action = parts[1] # مثل 'us', 'panel', 'add_user'
        params = parts[2:] # پارامترهای اضافی مثل ID کاربر
        
        # 2. پیدا کردن هندلر
        handler = ADMIN_CALLBACK_HANDLERS.get(action)
        
        if handler:
            # 3. اجرای هندلر (Async)
            await handler(call, params)
        else:
            logger.warning(f"No handler found for admin action: '{action}' in callback: {call.data}")
            await bot.answer_callback_query(call.id, "❌ دستور نامعتبر یا قدیمی است.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error handling admin callback '{call.data}': {e}", exc_info=True)
        await bot.answer_callback_query(call.id, "❌ خطایی در پردازش درخواست رخ داد.", show_alert=True)