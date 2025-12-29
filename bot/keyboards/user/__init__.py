# bot/keyboards/user/__init__.py

from .main import UserMainMenu
from .services import UserServicesMenu
from .wallet import UserWalletMenu
from .tutorials import UserTutorialsMenu

class UserKeyboards(UserMainMenu, UserServicesMenu, UserWalletMenu, UserTutorialsMenu):
    """
    کلاس تجمیعی برای کیبوردهای کاربر.
    این کلاس از تمام زیرکلاس‌ها ارث‌بری می‌کند تا ساختار قبلی (فراخوانی متدها از یک کلاس واحد) حفظ شود
    و نیازی به تغییرات گسترده در هندلرها نباشد.
    """
    pass

# نمونه‌سازی برای استفاده در هندلرها (اختیاری)
user_keyboard = UserKeyboards()