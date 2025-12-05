# bot/admin_router.py
import logging
from bot.admin_handlers import (
    user_management,
    panel_management,
    plan_management,
    reporting,
    group_actions,
    broadcast,
    backup,
    wallet as admin_wallet,
    support
)

logger = logging.getLogger(__name__)

def register_admin_handlers():
    """
    فعال‌سازی تمام هندلرهای بخش مدیریت
    """
    logger.info("Loading Admin Handlers...")
    
    return [
        user_management,
        panel_management,
        plan_management,
        reporting,
        group_actions,
        broadcast,
        backup,
        admin_wallet,
        support
    ]