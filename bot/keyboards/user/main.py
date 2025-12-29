# bot/keyboards/user/main.py

from telebot import types
from ..base import BaseMenu
from bot.language import get_string
from bot.database import db
from bot.config import EMOJIS

class UserMainMenu(BaseMenu):
    """منوهای اصلی، تنظیمات و عمومی کاربر"""

    async def main(self, is_admin: bool, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی اصلی ربات برای کاربران"""
        kb = self.create_markup(row_width=2)
        
        buttons = [
            (f"{EMOJIS['key']} {get_string('manage_account', lang_code)}", "manage"),
            (f"{EMOJIS['lightning']} {get_string('quick_stats', lang_code)}", "quick_stats"),
            (f"🛒 {get_string('view_plans', lang_code)}", "view_plans"),
            (f"💳 {get_string('wallet', lang_code)}", "wallet:main"),
            (f"📚 {get_string('btn_tutorials', lang_code)}", "tutorials"),
            (f"👤 {get_string('user_account_page_title', lang_code)}", "user_account"),
            (f"👥 {get_string('btn_referrals', lang_code)}", "referral:info"),
            (f"⚙️ {get_string('settings', lang_code)}", "settings"),
            (f"🎁 {get_string('birthday_gift', lang_code)}", "birthday_gift"),
            (f"💬 {get_string('support', lang_code)}", "support:new"),
            (f"🌐 {get_string('btn_web_login', lang_code)}", "web_login")
        ]

        for i in range(0, len(buttons), 2):
            b1 = self.btn(buttons[i][0], buttons[i][1])
            if i + 1 < len(buttons):
                b2 = self.btn(buttons[i+1][0], buttons[i+1][1])
                kb.row(b1, b2)
            else:
                kb.row(b1)

        if is_admin:
            kb.add(self.btn(f"{EMOJIS['crown']} پنل مدیریت", "admin:panel"))
            
        return kb

    async def settings(self, settings_dict: dict, lang_code: str, access: dict) -> types.InlineKeyboardMarkup:
        """منوی تنظیمات (گزارش‌ها و هشدارها)"""
        kb = self.create_markup()
        
        def status(key):
            return '✅' if settings_dict.get(key, True) else '❌'

        kb.add(self.btn(f"🗓️ {get_string('reports_category', lang_code)}", "noop"))
        kb.row(
            self.btn(f"📆 {get_string('monthly_report', lang_code)} {status('monthly_reports')}", "toggle:monthly_reports"),
            self.btn(f"📅 {get_string('weekly_report', lang_code)} {status('weekly_reports')}", "toggle:weekly_reports"),
            self.btn(f"📊 {get_string('daily_report', lang_code)} {status('daily_reports')}", "toggle:daily_reports")
        )

        kb.add(self.btn(f"🪫 {get_string('alerts_category', lang_code)}", "noop"))
        
        categories_list = await db.get_server_categories()
        alert_btns = []
        for cat in categories_list:
            cat_code = cat['code']
            if not access or not access.get(f"has_access_{cat_code}"):
                continue

            emoji = cat['emoji']
            setting_key = f"data_warning_{cat_code}"
            alert_btns.append(self.btn(f"{emoji} {status(setting_key)}", f"toggle:{setting_key}"))
        
        if alert_btns:
            for i in range(0, len(alert_btns), 3):
                kb.row(*alert_btns[i:i+3])
        else:
            kb.add(self.btn("⚠️ سرویس فعالی ندارید", "noop"))

        kb.add(
            self.btn(f"🌐 {get_string('change_language', lang_code)}", "change_language"),
            self.back_btn("back", lang_code)
        )
        return kb

    async def language_selection_start(self) -> types.InlineKeyboardMarkup:
        """منوی انتخاب زبان (استارت)"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🇺🇸 English", "start_lang:en"),
            self.btn("🇮🇷 فارسی", "start_lang:fa")
        )
        return kb

    async def language_change_menu(self) -> types.InlineKeyboardMarkup:
        """منوی تغییر زبان (از تنظیمات)"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🇮🇷 فارسی", "set_lang:fa"),
            self.btn("🇺🇸 English", "set_lang:en")
        )
        kb.add(self.btn("🔙 Back", "settings"))
        return kb

    async def auth_selection(self, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(
            self.btn(f"🔑 {get_string('login_with_uuid', lang_code)}", "auth:login"),
            self.btn(f"🆕 {get_string('create_test_account', lang_code)}", "auth:new")
        )
        return kb

    async def country_selection(self, categories: list, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        buttons = []
        for cat in categories:
            text = f"{cat['emoji']} {cat['name']}"
            buttons.append(self.btn(text, f"new_acc_country:{cat['code']}"))
        
        if buttons:
            kb.add(*buttons)
        kb.add(self.back_btn("start_reset", lang_code))
        return kb

    async def confirm_action_menu(self, yes_callback: str, no_callback: str, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"❌ {get_string('no', lang_code)}", no_callback),
            self.btn(f"✅ {get_string('yes', lang_code)}", yes_callback)
        )
        return kb

    async def user_cancel_action(self, back_callback: str, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        kb = self.create_markup()
        cancel_text = get_string('btn_cancel_action', lang_code)
        kb.add(self.btn(f"✖️ {cancel_text}", back_callback))
        return kb
    
    async def simple_back_menu(self, callback_data: str, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup()
        kb.add(self.back_btn(callback_data, lang_code))
        return kb

    async def feedback_rating_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=5)
        stars = [self.btn("⭐️" * i, f"feedback:rating:{i}") for i in range(1, 6)]
        kb.add(*stars)
        kb.add(self.btn("لغو", "back"))
        return kb