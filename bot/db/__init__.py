# bot/db/__init__.py

from .base import DatabaseManager
from .user import UserDB
from .usage import UsageDB
from .financials import FinancialsDB
from .panel import PanelDB
from .product import ProductDB
from .support import SupportDB
from .transfer import TransferDB
from .wallet import WalletDB
from .notifications import NotificationsDB
from .achievement import AchievementDB
from .feedback import FeedbackDB
from .admin_log import AdminLogDB
from .settings import SettingsDB

class BotDatabase(DatabaseManager, UserDB, UsageDB, FinancialsDB, PanelDB, 
                  ProductDB, SupportDB, TransferDB, WalletDB, NotificationsDB, 
                  AchievementDB, FeedbackDB, AdminLogDB, SettingsDB):
    
    def __init__(self, db_url: str = None):
        super().__init__(db_url)
        self._user_cache = {}