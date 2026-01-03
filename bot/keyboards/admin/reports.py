# bot/keyboards/admin/reports.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu

class AdminReportsMenu(BaseMenu):
    """منوهای گزارش‌گیری"""

    async def reports_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        
        panel_buttons = []
        for p in panels:
            btn_text = f"{p['name']} ({p['panel_type']})"
            panel_buttons.append(self.btn(btn_text, f"admin:panel_report_detail:{p['id']}"))
        if panel_buttons: kb.add(*panel_buttons)

        kb.add(
            self.btn("💳 تراکنش‌های مالی", "admin:list:payments:0"),
            self.btn("🤖 کاربران ربات", "admin:list:bot_users:0")
        )
        kb.add(
            self.btn("💰 موجودی کیف‌پول‌ها", "admin:list:balances:0"), 
            self.btn("🎂 تولد کاربران", "admin:list:birthdays")
        )
        kb.add(
            self.btn("📊 گزارش بر اساس پلن", "admin:user_analysis_menu"),
            self.btn("💸 گزارش سود و زیان", "admin:financial_report")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_specific_reports_menu(self, panel_id: int, panel_name: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ کاربران فعال (۲۴س)", f"admin:list:active_users:{panel_id}:0"),
            self.btn("📡 کاربران آنلاین", f"admin:list:online_users:{panel_id}:0")
        )
        kb.add(
            self.btn("⏳ غیرفعال‌ها", f"admin:list:inactive_users:{panel_id}:0"),
            self.btn("🚫 هرگز متصل نشده", f"admin:list:never_connected:{panel_id}:0")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb

    async def select_plan_for_report_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.row(self.btn("👤 کاربران بدون پلن", "admin:list_by_plan:0:0"))
        
        plan_btns = [self.btn(f"📦 {plan['name']}", f"admin:list_by_plan:{plan['id']}:0") for plan in plans]
        kb.add(*plan_btns)
        kb.row(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb