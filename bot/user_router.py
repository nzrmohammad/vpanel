# bot/user_router.py
import logging
from bot.user_handlers import (
    account,
    main_menu,
    wallet,
    settings,
    info,
    feedback,
    support,
    help,
    features
)

logger = logging.getLogger(__name__)

def register_user_handlers():
    """
    این تابع فقط ماژول‌ها را ایمپورت می‌کند تا هندلرهای آن‌ها
    که با دکوریتور @bot تعریف شده‌اند، در حافظه بارگذاری و فعال شوند.
    """
    # ترتیب ایمپورت مهم نیست، مگر اینکه هندلرهای عمومی (مثل Regex) داشته باشید
    # که باید آخر باشند.
    
    logger.info("Loading User Handlers...")
    
    # نکته فنی: صرفاً با ایمپورت کردن ماژول، دکوریتورهای داخل آن اجرا می‌شوند
    # و هندلرها به هسته بات متصل می‌شوند.
    return [
        account,
        wallet,
        settings,
        info,
        feedback,
        main_menu,
        support,
        help,
        features
    ]