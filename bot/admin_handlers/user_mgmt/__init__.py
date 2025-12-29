# bot/admin_handlers/user_mgmt/__init__.py

from .search import (
    handle_management_menu, handle_search_menu,
    handle_global_search_convo, handle_search_by_telegram_id_convo,
    process_search_input, handle_show_user_summary, show_user_summary,
    handle_user_interactive_menu, 
    handle_manage_single_panel_menu, # ✅ نام تابع اصلاح شد
    handle_panel_users_list, handle_filter_users,
    init as init_search
)

from .create import (
    handle_add_user_menu, handle_add_user_select_panel, handle_start_add_user,
    get_new_user_name, get_new_user_uuid, get_new_user_limit, get_new_user_days,
    handle_squad_callback, handle_external_squad_callback,
    handle_random_user_generation, handle_cancel_process,
    handle_add_user_to_panel_start,
    init as init_create
)

from .edit import (
    handle_edit_user_menu, handle_select_panel_for_edit, handle_ask_edit_value,
    process_edit_value, handle_toggle_status, handle_toggle_status_action,
    handle_delete_user_confirm, handle_delete_user_action,
    handle_delete_user_from_panel,
    init as init_edit
)

from .financial import (
    handle_payment_history, handle_log_payment, handle_reset_payment_history_confirm,
    handle_reset_payment_history_action, handle_ask_for_note, process_save_note,
    handle_renew_subscription_menu, handle_renew_apply_plan,
    handle_award_badge_menu, handle_award_badge, handle_achievement_request_callback,
    init as init_financial
)

from .access import (
    handle_user_access_panel_list, handle_user_access_toggle,
    handle_user_reset_menu, handle_reset_usage_action,
    handle_reset_birthday, handle_reset_transfer_cooldown,
    handle_user_warning_menu, handle_send_payment_reminder,
    handle_send_disconnection_warning, handle_delete_devices_action,
    init as init_access
)

# بخش Mapping (اختیاری اگر فایل mapping.py را ساخته‌اید)
try:
    from .mapping import (
        handle_mapping_menu, handle_mapping_list, handle_add_mapping_start,
        get_mapping_uuid_step, get_mapping_username_step,
        handle_delete_mapping_confirm, handle_delete_mapping_execute,
        init as init_mapping
    )
except ImportError:
    def init_mapping(*args): pass

def initialize_user_management_handlers(bot, conv_dict):
    init_search(bot, conv_dict)
    init_create(bot, conv_dict)
    init_edit(bot, conv_dict)
    init_financial(bot, conv_dict)
    init_access(bot, conv_dict)
    init_mapping(bot, conv_dict)