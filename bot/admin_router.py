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
    navigation, debug, settings, shop_management
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
        support, settings, shop_management
    ]
    
    # Pass bot.context_state as the shared dictionary
    for module in modules_to_init:
        try:
            # ساخت نام تابع initialize بر اساس نام ماژول
            # مثلا برای panel_management دنبال initialize_panel_management_handlers می‌گردد
            module_name = module.__name__.split('.')[-1]
            init_func_name = f"initialize_{module_name}_handlers"
            
            if hasattr(module, init_func_name):
                func = getattr(module, init_func_name)
                if callable(func):
                    func(bot_instance, bot.context_state)
                else:
                    logger.error(f"❌ Error: {init_func_name} in {module_name} is NOT a function (it's a {type(func)}).")
        except Exception as e:
            logger.error(f"❌ Failed to init module {module}: {e}")

    # Wallet init
    if hasattr(wallet_admin, 'admin_conversations') and isinstance(wallet_admin.admin_conversations, dict):
        wallet_admin.admin_conversations.update(bot.context_state)

    # Group actions init
    if hasattr(group_actions, 'initialize_group_actions_handlers'):
        if callable(group_actions.initialize_group_actions_handlers):
            group_actions.initialize_group_actions_handlers(bot_instance, bot.context_state)

    # Debug init
    if hasattr(debug, 'register_debug_handlers') and callable(debug.register_debug_handlers):
        debug.register_debug_handlers(bot_instance, scheduler_instance)

# ===================================================================
# 3. Route Helpers & Logic
# ===================================================================

@safe_handler
async def route_add_user(call: types.CallbackQuery, params: list):
    """Router for adding a user"""
    # بررسی اینکه آیا تابع در فایل user_management/creation.py ایمپورت و اکسپوز شده است یا خیر
    # با توجه به فایل‌هایی که فرستادید، تابع handle_start_add_user در creation.py است.
    # اگر پکیج user_management آن را اکسپوز نکرده باشد، باید دستی هندل شود.
    
    # تلاش برای یافتن تابع با نام‌های مختلف احتمالی
    handler = getattr(user_management, 'handle_add_user_start', None) or \
              getattr(user_management, 'handle_start_add_user', None)
              
    if handler and callable(handler):
        await handler(call, params)
    else:
        await bot.answer_callback_query(call.id, "⚠️ User management module not updated.", show_alert=True)

@safe_handler
async def route_system_config(call: types.CallbackQuery, params: list):
    if not params: return
    action = params[0]
    
    if action == 'list':
        await settings.list_config_category(call, params[1:])
    elif action == 'edit':
        await settings.edit_config_start(call, params[1:])

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
    # در فایل creation.py نام تابع handle_add_user_select_panel است
    "add_user_select_panel": getattr(user_management, 'handle_add_user_select_panel', getattr(user_management, 'handle_add_user_select_panel_callback', None)),
    "sel_squad": getattr(user_management, 'handle_squad_callback', None),
    "sel_ext_squad": getattr(user_management, 'handle_external_squad_callback', None),
    "skip_squad": getattr(user_management, 'handle_squad_callback', None),
    "cancel": getattr(user_management, 'handle_cancel_process', None),

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
    "manage_single_panel": getattr(user_management, 'handle_manage_single_panel_menu', None),
    "add_user_to_panel": getattr(user_management, 'handle_add_user_to_panel_start', None),
    "p_users": getattr(user_management, 'handle_panel_users_list', None),

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
    "cat_detail": plan_management.handle_category_details,
    "cat_edit": plan_management.handle_category_edit_start,
    "cat_delete": plan_management.handle_category_delete, 
    "cat_del_exec": plan_management.handle_category_delete_execute,
    "cat_add_start": plan_management.handle_category_add_start,
    
    "panel_manage": panel_management.handle_panel_management_menu,
    "panel_details": panel_management.handle_panel_details,
    "panel_add_start": panel_management.handle_start_add_panel,
    "panel_set_type": panel_management.handle_set_panel_type,
    
    "panel_toggle": panel_management.handle_panel_choice_toggle,
    "panel_edit_start": panel_management.handle_panel_edit_start,
    "panel_delete_confirm": panel_management.handle_panel_choice_delete,
    "panel_del_exec": panel_management.handle_panel_delete_execute,
    "panel_delete_execute": panel_management.handle_panel_delete_execute,
    "panel_set_cat": panel_management.handle_set_panel_category,

    # User Management Actions
    "sg": getattr(user_management, 'handle_global_search_convo', None),
    "search_by_tid": getattr(user_management, 'handle_search_by_telegram_id_convo', None),
    "purge_user": getattr(user_management, 'handle_purge_user_convo', None),
    "us": getattr(user_management, 'handle_show_user_summary', None),
    "us_edt": getattr(user_management, 'handle_edit_user_menu', None),
    "ep": getattr(user_management, 'handle_select_panel_for_edit', None),
    "ae": getattr(user_management, 'handle_ask_edit_value', None),
    "us_tgl": getattr(user_management, 'handle_toggle_status', None),
    "tglA": getattr(user_management, 'handle_toggle_status_action', None),
    "us_lpay": getattr(user_management, 'handle_log_payment', None),
    "us_phist": getattr(user_management, 'handle_payment_history', None),
    "reset_phist": getattr(user_management, 'handle_reset_payment_history_confirm', None),
    "do_reset_phist": getattr(user_management, 'handle_reset_payment_history_action', None),
    "us_reset_menu": getattr(user_management, 'handle_user_reset_menu', None),
    "us_rb": getattr(user_management, 'handle_reset_birthday', None),
    "us_rusg": getattr(user_management, 'handle_reset_usage_menu', None),
    "rsa": getattr(user_management, 'handle_reset_usage_action', None),
    "us_rtr": getattr(user_management, 'handle_reset_transfer_cooldown', None),
    "us_warn_menu": getattr(user_management, 'handle_user_warning_menu', None),
    "us_spn": getattr(user_management, 'handle_send_payment_reminder', None),
    "us_sdw": getattr(user_management, 'handle_send_disconnection_warning', None),
    "us_delc": getattr(user_management, 'handle_delete_user_confirm', None),
    "del_a": getattr(user_management, 'handle_delete_user_action', None),
    "us_ddev": getattr(user_management, 'handle_delete_devices_confirm', None),
    "del_devs_exec": getattr(user_management, 'handle_delete_devices_action', None),
    "us_note": getattr(user_management, 'handle_ask_for_note', None),
    "renew_sub_menu": getattr(user_management, 'handle_renew_subscription_menu', None),
    "renew_select_plan": getattr(user_management, 'handle_renew_select_plan_menu', None),
    "renew_apply_plan": getattr(user_management, 'handle_renew_apply_plan', None),
    "churn_contact_user": getattr(user_management, 'handle_churn_contact_user', None),
    "churn_send_offer": getattr(user_management, 'handle_churn_send_offer', None),
    "skip_telegram_id": getattr(user_management, 'skip_telegram_id', None),
    
    # Panel Node Management
    'panel_add_node_start': panel_management.handle_panel_add_node_start,
    'panel_node_save': panel_management.handle_panel_node_save,
    'panel_ch_ren': panel_management.handle_panel_choice_rename,
    'panel_ch_del': panel_management.handle_panel_choice_delete,
    'panel_ch_tog': panel_management.handle_panel_choice_toggle,
    'panel_manage_nodes': panel_management.handle_panel_manage_nodes,
    
    # Node Actions
    'panel_node_sel': panel_management.handle_panel_node_selection,
    'p_node_ren_st': panel_management.handle_node_rename_start,
    'p_node_tog': panel_management.handle_node_toggle,
    'node_delete_conf': panel_management.handle_node_delete_confirm,
    'p_node_del': panel_management.handle_node_delete_confirm,

    'us_acc_p_list': getattr(user_management, 'handle_user_access_panel_list', None),
    'us_acc_tgl': getattr(user_management, 'handle_user_access_toggle', None),
    'tgl_acc': getattr(user_management, 'handle_user_access_toggle', None),
    'ptgl': getattr(user_management, 'handle_user_access_toggle', None),
    'node_manage': getattr(user_management, 'handle_user_access_panel_list', None),
    'node_tgl': getattr(user_management, 'handle_user_access_toggle', None),
    
    'tgl_n_acc': getattr(user_management, 'handle_user_access_toggle', None),
    'tgl_p_acc': getattr(user_management, 'handle_user_access_toggle', None),

    # Marzban Mapping
    "mapping_menu": getattr(user_management, 'handle_mapping_menu', None),
    "mapping_list": getattr(user_management, 'handle_mapping_list', None),
    "map_detail": getattr(user_management, 'handle_mapping_detail', None),
    "add_mapping": getattr(user_management, 'handle_add_mapping_start', None),
    
    "del_map_conf": getattr(user_management, 'handle_delete_mapping_confirm', None),
    "del_map_exec": getattr(user_management, 'handle_delete_mapping_execute', None),
    "confirm_map_replace": getattr(user_management, 'handle_confirm_map_replace', None),

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
    "charge_req": wallet_admin.handle_charge_request_callback,
    "reset_all_balances_confirm": getattr(user_management, 'handle_reset_all_balances_confirm', None),
    "reset_all_balances_exec": getattr(user_management, 'handle_reset_all_balances_execute', None),

    # Groups & Badges
    "group_action_select_plan": group_actions.handle_select_plan_for_action,
    "ga_select_type": group_actions.handle_select_action_type,
    "ga_ask_value": group_actions.handle_ask_action_value,
    "adv_ga_select_filter": group_actions.handle_select_advanced_filter,
    "adv_ga_select_action": group_actions.handle_select_action_for_filter,
    "ga_confirm": group_actions.ga_execute,
    "awd_b_menu": getattr(user_management, 'handle_award_badge_menu', None),
    "awd_b": getattr(user_management, 'handle_award_badge', None),

    # Tools
    "system_tools_menu": getattr(user_management, 'handle_system_tools_menu', None),
    "reset_all_daily_usage_confirm": getattr(user_management, 'handle_reset_all_daily_usage_confirm', None),
    "reset_all_daily_usage_exec": getattr(user_management, 'handle_reset_all_daily_usage_action', None),
    "force_snapshot": getattr(user_management, 'handle_force_snapshot', None),
    "reset_all_points_confirm": getattr(user_management, 'handle_reset_all_points_confirm', None),
    "reset_all_points_exec": getattr(user_management, 'handle_reset_all_points_execute', None),
    "delete_all_devices_confirm": getattr(user_management, 'handle_delete_all_devices_confirm', None),
    "delete_all_devices_exec": getattr(user_management, 'handle_delete_all_devices_execute', None),
    "broadcast": broadcast.start_broadcast_flow,
    "broadcast_target": broadcast.ask_for_broadcast_message,
    "broadcast_confirm": broadcast.broadcast_confirm,
    "backup_menu": backup.backup_menu_handler,
    "backup": backup.backup_panel_data,

    # --- Settings Handlers ---
    "settings": settings.settings_main_panel,
    "sys_conf": route_system_config,
    "pay_methods": settings.list_payment_methods,
    "add_method": settings.start_add_method,
    "del_method": settings.delete_payment_method_handler,
    "toggle_method": settings.toggle_payment_method_handler,
    "edit_usdt_rate": settings.edit_usdt_rate_start,
    "pm_manage": settings.manage_single_payment_method,
    "pm_toggle": settings.toggle_payment_method_handler,
    "pm_del": settings.delete_payment_method_handler,
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
            if callable(next_func):
                await next_func(message)
            else:
                logger.error(f"❌ Error: next_handler for user {uid} is NOT callable: {next_func}")
                await bot.reply_to(message, "❌ Internal error: Step handler is missing or invalid.")

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
    
    if action == "none":
        await bot.answer_callback_query(call.id)
        return
    
    handler = ADMIN_CALLBACK_HANDLERS.get(action)
    
    if handler:
        if callable(handler):
            await handler(call, params)
        else:
            logger.error(f"❌ Handler for action '{action}' is NOT callable (it's a {type(handler)}). Check ADMIN_CALLBACK_HANDLERS.")
            await bot.answer_callback_query(call.id, f"❌ Error: Handler for {action} is invalid.", show_alert=True)
    else:
        logger.warning(f"Handler not found for: {action}")
        await bot.answer_callback_query(call.id, "❌ Command not found.", show_alert=True)