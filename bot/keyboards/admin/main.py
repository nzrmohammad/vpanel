# bot/keyboards/admin/main.py

from telebot import types
from ..base import BaseMenu

class AdminMainMenu(BaseMenu):
    """منوی اصلی مدیریت و متدهای عمومی"""

    async def main(self) -> types.InlineKeyboardMarkup:
        """منوی اصلی مدیریت"""
        kb = self.create_markup(row_width=2)
        
        layout = [
            [("📊 داشبورد سریع", "admin:quick_dashboard")],
            [("🔎 جستجوی کاربر", "admin:search_menu"), ("👥 مدیریت کاربران", "admin:management_menu")],
            [("📊 گزارش‌ها و آمار", "admin:reports_menu"), ("⚙️ دستورات گروهی", "admin:group_actions_menu")],
            [("💾 پشتیبان‌گیری", "admin:backup_menu"), ("📣 پیام همگانی", "admin:broadcast")],
            [("⏰ کارهای زمان‌بندی", "admin:scheduled_tasks"), ("🗂️ مدیریت پلن‌ها", "admin:plan_manage")],
            [("⚙️ تنظیمات پنل‌ها", "admin:panel_manage"), ("🛠️ ابزارهای سیستمی", "admin:system_tools_menu")],
            [("⚙️ تنظیمات سیستم", "admin:settings:main"), ("🔗 مدیریت اتصال مرزبان", "admin:mapping_menu")],
            [("🔙 بازگشت به منوی اصلی", "back")]
        ]
        
        for row in layout:
            btns = []
            for item in row:
                if isinstance(item, tuple) and len(item) >= 2:
                    btns.append(self.btn(item[0], item[1]))
            if btns:
                kb.row(*btns)
                
        return kb

    async def cancel_action(self, back_callback="admin:panel") -> types.InlineKeyboardMarkup:
        """دکمه عمومی لغو عملیات"""
        kb = self.create_markup()
        kb.add(self.btn("✖️ لغو عملیات", back_callback))
        return kb