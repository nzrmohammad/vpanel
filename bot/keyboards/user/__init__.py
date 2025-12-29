from .main import UserMainMenu
from .services import UserServicesMenu
from .wallet import UserWalletMenu
from .tutorials import UserTutorialsMenu

class UserKeyboards(UserMainMenu, UserServicesMenu, UserWalletMenu, UserTutorialsMenu):
    """Facade class for user keyboards"""
    pass

# نمونه‌سازی نهایی
user_keyboard = UserKeyboards()