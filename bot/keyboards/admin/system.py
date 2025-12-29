# bot/keyboards/admin/system.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu

class AdminSystemMenu(BaseMenu):
    """ابزارهای سیستمی، بکاپ و دستورات گروهی"""

    async def backup_selection_menu(self, panel_types: list, current_filter: str = 'all') -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        
        filters = [("❌ غیرفعال", "inactive"), ("✅ فعال", "active"), ("👥 همه", "all")]
        filter_btns = []
        for label, code in filters:
            display = f"🔘 {label}" if code == current_filter else label
            cb = "noop" if code == current_filter else f"admin:backup_filter:{code}" 
            filter_btns.append(self.btn(display, cb))
        kb.row(*filter_btns)
        
        panel_buttons = []
        for p_type in panel_types:
            panel_buttons.append(self.btn(f"📥 {p_type.capitalize()} (API)", f"admin:backup:{p_type}:{current_filter}"))
            
        if panel_buttons: kb.add(*panel_buttons)
        kb.add(self.btn("🗄️ دیتابیس ربات (SQL + JSON)", "admin:backup:bot_db"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def system_tools_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔄 آپدیت آمار (Snapshot)", "admin:force_snapshot"),
            self.btn("🔄 ریست مصرف امروز همه", "admin:reset_all_daily_usage_confirm")
        )
        kb.add(
            self.btn("🏆 ریست امتیازات", "admin:reset_all_points_confirm"),
            self.btn("🗑️ حذف تمام دستگاه‌ها", "admin:delete_all_devices_confirm")
        )
        kb.add(self.btn("💸 ریست موجودی همه", "admin:reset_all_balances_confirm"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def group_actions_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔥 پیشرفته", "admin:adv_ga_select_filter"),
            self.btn("⚙️ بر اساس پلن", "admin:group_action_select_plan")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def select_plan_for_action_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        for plan in plans:
            kb.add(self.btn(plan['name'], f"admin:ga_select_type:{plan['id']}"))
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def select_action_type_menu(self, context_value: any, context_type: str) -> types.InlineKeyboardMarkup:
        # استفاده از متد کمکی که در اینجا بازتعریف شده (یا می‌تواند به shared برود)
        kb = self.create_markup(row_width=2)
        base_callback="admin:ga_ask_value"
        suffix = f"{context_type}:{context_value}"
        kb.add(
            self.btn("➕ افزودن حجم", f"{base_callback}:add_gb:{suffix}"),
            self.btn("➕ افزودن روز", f"{base_callback}:add_days:{suffix}")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def confirm_group_action_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(self.btn("✅ بله، انجام شود", "admin:ga_confirm"), self.btn("❌ لغو", "admin:group_actions_menu"))
        return kb

    async def advanced_group_action_filter_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(self.btn("⏳ در آستانه انقضا (۳ روز)", "admin:adv_ga_select_action:expiring_soon"))
        kb.add(self.btn("🚫 غیرفعال (۳۰ روز)", "admin:adv_ga_select_action:inactive_30_days"))
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def broadcast_target_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📡 آنلاین (۲۴س)", "admin:broadcast_target:online"),
            self.btn("✅ فعال (دارای سرویس)", "admin:broadcast_target:active_1")
        )
        kb.add(
            self.btn("⏳ غیرفعال (۷ روز)", "admin:broadcast_target:inactive_7"),
            self.btn("🚫 هرگز متصل نشده", "admin:broadcast_target:inactive_0")
        )
        kb.add(self.btn("👥 همه کاربران", "admin:broadcast_target:all"))
        kb.add(self.btn("🔙 لغو", "admin:panel"))
        return kb

    async def confirm_broadcast_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، ارسال شود", "admin:broadcast_confirm"),
            self.btn("❌ خیر، لغو", "admin:panel")
        )
        return kb