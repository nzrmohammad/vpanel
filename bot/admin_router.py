# bot/admin_router.py

import logging
import time
from typing import Callable, Any
from telebot import types
from telebot.asyncio_filters import SimpleCustomFilter

# --- Imports ---
from .bot_instance import bot
from .utils import initialize_utils
from .config import ADMIN_IDS

# --- Import Handlers ---
from .admin_handlers import (
    user_management, reporting, broadcast, backup, group_actions,
    plan_management, panel_management, support, wallet as wallet_admin,
    navigation, debug
)

logger = logging.getLogger(__name__)

# --- State Management ---
if not hasattr(bot, 'context_state'):
    bot.context_state = {}

CONVERSATION_TIMEOUT = 300  # 5 minutes

# ===================================================================
# 1. Custom Filters & Decorators
# ===================================================================

class IsAdminFilter(SimpleCustomFilter):
    """Filter to check if the user is an admin"""
    key = 'is_admin'
    
    async def check(self, message: types.Message):
        return message.from_user.id in ADMIN_IDS

def safe_handler(func: Callable) -> Callable:
    """Decorator for safe error handling and logging"""
    async def wrapper(call_or_message, *args, **kwargs):
        user_id = call_or_message.from_user.id
        username = call_or_message.from_user.username
        
        action_name = func.__name__
        if isinstance(call_or_message, types.CallbackQuery):
            logger.info(f"ADMIN ACTION [Callback]: {user_id} ({username}) -> {call_or_message.data}")
        else:
            logger.info(f"ADMIN ACTION [Message]: {user_id} ({username}) -> {action_name}")

        try:
            return await func(call_or_message, *args, **kwargs)
        except Exception as e:
            logger.error(f"CRITICAL ERROR in {action_name}: {e}", exc_info=True)
            try:
                if isinstance(call_or_message, types.CallbackQuery):
                    await bot.answer_callback_query(call_or_message.id, "❌ Internal processing error.", show_alert=True)
                elif isinstance(call_or_message, types.Message):
                    await bot.reply_to(call_or_message, "❌ Internal server error occurred.")
            except:
                pass
    return wrapper

# ===================================================================
# 2. Initialization
# ===================================================================

def register_admin_handlers(bot_instance, scheduler_instance):
    """Initialize handlers and inject state"""
    
    initialize_utils(bot_instance)
    bot.add_custom_filter(IsAdminFilter())

    # Modules that need access to state
    modules_to_init = [
        user_management, plan_management, panel_management,
        wallet_admin, support
    ]
    
    # Pass bot.context_state as the shared dictionary
    for module in modules_to_init:
        init_func_name = f"initialize_{module.__name__.split('.')[-1]}_handlers"
        if hasattr(module, init_func_name):
            getattr(module, init_func_name)(bot_instance, bot.context_state)

    if hasattr(group_actions, 'initialize_group_actions_handlers'):
        group_actions.initialize_group_actions_handlers(bot_instance, bot.context_state)

    debug.register_debug_handlers(bot_instance, scheduler_instance)

# ===================================================================
# 3. Route Helpers & Logic
# ===================================================================

@safe_handler
async def route_add_user(call: types.CallbackQuery, params: list):
    """Router for adding a user"""
    if hasattr(user_management, 'handle_add_user_start'):
        await user_management.handle_add_user_start(call, params)
    else:
        await bot.answer_callback_query(call.id, "⚠️ User management module not updated.", show_alert=True)

# ===================================================================
# 4. Dispatcher Dictionary
# ===================================================================
ADMIN_CALLBACK_HANDLERS = {
    # Navigation
    "panel": navigation.handle_show_panel,
    "management_menu": navigation.handle_management_menu,
    "search_menu": navigation.handle_search_menu,
    "group_actions_menu": navigation.handle_group_actions_menu,
    "user_analysis_menu": navigation.handle_user_analysis_menu,
    "system_status_menu": navigation.handle_system_status_menu,
    "manage_panel": navigation.handle_panel_management_menu,
    "select_server": navigation.handle_server_selection,

    # Actions
    "add_user": route_add_user,
    "add_user_select_panel": getattr(user_management, 'handle_add_user_select_panel_callback', None),

    # Reports
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
    "panel_report_detail": reporting.handle_panel_specific_reports_menu,
    "manage_single_panel": navigation.handle_panel_management_menu, 

    # Plans & Panels
    "plan_manage": plan_management.handle_plan_management_menu,
    "plan_show_category": plan_management.handle_show_plans_by_category,
    "plan_details": plan_management.handle_plan_details_menu,
    "plan_delete_confirm": plan_management.handle_delete_plan_confirm,
    "plan_delete_execute": plan_management.handle_delete_plan_execute,
    "plan_edit_start": plan_management.handle_plan_edit_start,
    "plan_add_start": plan_management.handle_plan_add_start,
    "plan_add_type": plan_management.get_plan_add_type,

    "cat_manage": plan_management.handle_category_management_menu,
    "cat_delete": plan_management.handle_category_delete,
    "cat_add_start": plan_management.handle_category_add_start,
    
    "panel_manage": panel_management.handle_panel_management_menu,
    "panel_details": panel_management.handle_panel_details,
    "panel_add_start": panel_management.handle_start_add_panel,
    "panel_set_type": panel_management.handle_set_panel_type,
    "panel_toggle": panel_management.handle_panel_toggle_status,
    "panel_edit_start": panel_management.handle_panel_edit_start,
    "panel_delete_confirm": panel_management.handle_panel_delete_confirm,
    "panel_delete_execute": panel_management.handle_panel_delete_execute,
    "panel_set_cat": panel_management.handle_set_panel_category,

    # User Management Actions
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
    "add_user_to_panel": user_management.handle_add_user_start,

    # Marzban Mapping
    "mapping_menu": user_management.handle_mapping_menu,
    "mapping_list": user_management.handle_mapping_list,
    "add_mapping": user_management.handle_add_mapping_start,
    
    # حذف
    "del_map_conf": user_management.handle_delete_mapping_confirm,
    "del_map_exec": user_management.handle_delete_mapping_execute,

    # Wallet
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

    # Groups & Badges
    "group_action_select_plan": group_actions.handle_select_plan_for_action,
    "ga_select_type": group_actions.handle_select_action_type,
    "ga_ask_value": group_actions.handle_ask_action_value,
    "adv_ga_select_filter": group_actions.handle_select_advanced_filter,
    "adv_ga_select_action": group_actions.handle_select_action_for_filter,
    "ga_confirm": group_actions.ga_execute,
    "awd_b_menu": user_management.handle_award_badge_menu,
    "awd_b": user_management.handle_award_badge,
    "ach_req_approve": user_management.handle_achievement_request_callback,
    "ach_req_reject": user_management.handle_achievement_request_callback,
    "support_reply": support.prompt_for_reply,

    # Tools
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
    "broadcast_confirm": broadcast.broadcast_confirm,
    "backup_menu": backup.backup_menu_handler,
    "backup": backup.backup_panel_data,
}

# ===================================================================
# 5. Global Handlers (Cleanup & Steps)
# ===================================================================

@bot.message_handler(commands=['cancel'], is_admin=True)
async def admin_cancel_command(message: types.Message):
    """Cancel operation and reset state"""
    uid = message.from_user.id
    if uid in bot.context_state:
        del bot.context_state[uid]
        await bot.reply_to(message, "✅ Operation cancelled and state reset.")
    else:
        await bot.reply_to(message, "No active operation.")

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice'], is_admin=True, func=lambda m: m.from_user.id in bot.context_state)
@safe_handler
async def global_step_handler(message: types.Message):
    """
    Manages conversation steps with timeout check
    """
    uid = message.from_user.id
    
    if uid in bot.context_state:
        step_data = bot.context_state[uid]
        
        # Check timeout
        last_time = step_data.get('timestamp', 0)
        if time.time() - last_time > CONVERSATION_TIMEOUT:
            del bot.context_state[uid]
            await bot.reply_to(message, "⏳ Operation timed out. Please try again.")
            return

        # Update last interaction time
        step_data['timestamp'] = time.time()
        
        next_func = step_data.get('next_handler')
        if next_func:
            await next_func(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:"), is_admin=True)
@safe_handler
async def handle_admin_callbacks(call: types.CallbackQuery):
    """Central admin button handler"""
    uid = call.from_user.id
    # Extend state time
    if uid in bot.context_state:
        bot.context_state[uid]['timestamp'] = time.time()

    parts = call.data.split(':')
    if len(parts) < 2: return
        
    action = parts[1]
    params = parts[2:]
    
    # Special handling for single_panel navigation if no specific handler
    if action == "manage_single_panel":
        # This callback needs to redirect to the specific menu
        # Format: manage_single_panel:ID:Type
        pass 

    handler = ADMIN_CALLBACK_HANDLERS.get(action)
    
    if handler:
        await handler(call, params)
    else:
        logger.warning(f"Handler not found for: {action}")
        await bot.answer_callback_query(call.id, "❌ Command not found.", show_alert=True)