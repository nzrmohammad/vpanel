from .search import (
    handle_global_search_convo, handle_search_by_telegram_id_convo,
    process_search_input, handle_show_user_summary, show_user_summary,
    init as init_search
)
from .create import (
    handle_add_user_select_panel, get_new_user_name, get_new_user_uuid,
    get_new_user_limit, get_new_user_days, init as init_create
)
from .edit import (
    handle_edit_user_menu, handle_select_panel_for_edit, handle_ask_edit_value,
    process_edit_value, handle_toggle_status_action, handle_delete_user_confirm,
    handle_delete_user_action, init as init_edit
)
from .financial import (
    handle_payment_history, handle_log_payment, handle_ask_for_note,
    process_save_note, handle_renew_subscription_menu, handle_renew_apply_plan,
    init as init_financial
)
from .access import (
    handle_user_access_panel_list, handle_user_access_toggle,
    handle_user_reset_menu, init as init_access
)

def initialize_user_management_handlers(bot, conv_dict):
    """
    این تابع جایگزین تابع قبلی در فایل تک شد.
    وظیفه‌اش مقداردهی اولیه متغیرهای global در تمام زیرماژول‌هاست.
    """
    init_search(bot, conv_dict)
    init_create(bot, conv_dict)
    init_edit(bot, conv_dict)
    init_financial(bot, conv_dict)
    init_access(bot, conv_dict)