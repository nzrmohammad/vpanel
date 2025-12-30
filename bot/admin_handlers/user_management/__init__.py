# bot/admin_handlers/user_management/__init__.py

from .state import set_bot, set_conversations

# ایمپورت تمام هندلرها برای دسترسی از بیرون پکیج
from .search import (
    handle_management_menu, handle_search_menu,
    handle_global_search_convo, handle_search_by_telegram_id_convo,
    process_search_input, handle_purge_user_convo, process_purge_user
)

from .profile import (
    handle_show_user_summary, show_user_summary,
    handle_user_interactive_menu
)

from .creation import (
    handle_add_user_select_panel, handle_start_add_user,
    get_new_user_name, get_new_user_uuid, get_new_user_limit,
    get_new_user_days, get_new_user_telegram_id, skip_telegram_id,
    handle_squad_callback, handle_external_squad_callback,
    handle_cancel_process
)

from .editing import (
    handle_edit_user_menu, handle_select_panel_for_edit,
    handle_ask_edit_value, process_edit_value
)

from .status import (
    handle_toggle_status, handle_toggle_status_action
)

from .finance import (
    handle_payment_history, handle_log_payment,
    handle_reset_payment_history_confirm, handle_reset_payment_history_action
)

from .mapping import (
    handle_mapping_menu,
    handle_mapping_list,
    handle_add_mapping_start,
    handle_delete_mapping_confirm,
    handle_delete_mapping_execute,
    handle_confirm_map_replace
)

from .actions import (
    handle_user_reset_menu, handle_reset_usage_menu, handle_reset_usage_action,
    handle_reset_birthday, handle_reset_transfer_cooldown,
    handle_user_warning_menu, handle_send_payment_reminder,
    handle_send_disconnection_warning, handle_ask_for_note, process_save_note,
    handle_delete_user_confirm, handle_delete_user_action,
    handle_delete_devices_confirm, handle_delete_devices_action,
    handle_renew_subscription_menu, handle_renew_select_plan_menu,
    handle_renew_apply_plan, handle_award_badge_menu, handle_award_badge,
    handle_achievement_request_callback, handle_churn_contact_user,
    handle_churn_send_offer
)

from .access import (
    handle_manage_single_panel_menu, handle_panel_users_list,
    handle_user_access_panel_list, handle_user_access_toggle,
    handle_add_user_to_panel_start
)

from .system import (
    handle_system_tools_menu, handle_reset_all_daily_usage_confirm,
    handle_reset_all_daily_usage_action, handle_force_snapshot,
    handle_reset_all_points_confirm, handle_reset_all_points_execute,
    handle_delete_all_devices_confirm, handle_delete_all_devices_execute,
    handle_reset_all_balances_confirm, handle_reset_all_balances_execute
)

def initialize_user_management_handlers(bot_instance, conv_dict):
    """
    تابع راه‌اندازی که توسط admin_router صدا زده می‌شود.
    """
    set_bot(bot_instance)
    set_conversations(conv_dict)