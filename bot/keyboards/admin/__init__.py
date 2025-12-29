# bot/keyboards/admin/__init__.py

from .main import AdminMainMenu
from .users import AdminUsersMenu
from .servers import AdminServersMenu
from .reports import AdminReportsMenu
from .plans import AdminPlansMenu
from .system import AdminSystemMenu

class AdminKeyboards(
    AdminMainMenu,
    AdminUsersMenu,
    AdminServersMenu,
    AdminReportsMenu,
    AdminPlansMenu,
    AdminSystemMenu
):
    """
    Facade class for all admin keyboards.
    Combines all separated modules into one class to maintain compatibility.
    """
    pass

# نمونه‌سازی برای استفاده در هندلرها
admin_keyboard = AdminKeyboards()