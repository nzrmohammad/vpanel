# bot/menu/base.py

from telebot import types
from typing import Optional, List, Dict
from ..language import get_string
from ..config import PAGE_SIZE, EMOJIS, CARD_PAYMENT_INFO, ONLINE_PAYMENT_LINK, ACHIEVEMENT_SHOP_ITEMS

# دیکشنری مشترک برای نام‌های نمایشی و ایموجی‌ها
CATEGORY_META = {
    'de': {'emoji': '🇩🇪', 'name': 'آلمان'},
    'de2': {'emoji': '🇩🇪', 'name': 'آلمان (2)'},
    'fr': {'emoji': '🇫🇷', 'name': 'فرانسه'},
    'tr': {'emoji': '🇹🇷', 'name': 'ترکیه'},
    'us': {'emoji': '🇺🇸', 'name': 'آمریکا'},
    'ro': {'emoji': '🇷🇴', 'name': 'رومانی'},
    'fi': {'emoji': '🇫🇮', 'name': 'فنلاند'},
    'ir': {'emoji': '🇮🇷', 'name': 'ایران'},
    'supp': {'emoji': '🆘', 'name': 'پشتیبانی'},
}

class BaseMenu:
    """کلاس پایه برای تمام منوها شامل متدهای کمکی"""
    
    def create_markup(self, row_width=2) -> types.InlineKeyboardMarkup:
        return types.InlineKeyboardMarkup(row_width=row_width)

    def btn(self, text: str, callback_data: str, url: str = None) -> types.InlineKeyboardButton:
        return types.InlineKeyboardButton(text, callback_data=callback_data, url=url)

    def back_btn(self, callback: str, lang_code: str) -> types.InlineKeyboardButton:
        return self.btn(f"🔙 {get_string('back', lang_code)}", callback)

    async def create_pagination_menu(self, base_callback: str, current_page: int, total_items: int, back_callback: str, lang_code: str = 'fa', context: Optional[str] = None) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        
        back_text = f"🔙 {get_string('back', lang_code)}"
        prev_text = f"⬅️ {get_string('btn_prev_page', lang_code)}"
        next_text = f"{get_string('btn_next_page', lang_code)} ➡️"

        if total_items <= PAGE_SIZE:
            kb.add(self.btn(back_text, back_callback))
            return kb

        context_suffix = f":{context}" if context else ""
        nav_buttons = []
        
        if current_page > 0:
            nav_buttons.append(self.btn(prev_text, f"{base_callback}:{current_page - 1}{context_suffix}"))
            
        if (current_page + 1) * PAGE_SIZE < total_items:
            nav_buttons.append(self.btn(next_text, f"{base_callback}:{current_page + 1}{context_suffix}"))

        if nav_buttons:
            kb.row(*nav_buttons)

        kb.add(self.btn(back_text, back_callback))
        return kb

    async def back_or_cancel(self, back_callback: str, cancel_callback: str = "admin:panel") -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔙 بازگشت", back_callback),
            self.btn("✖️ لغو", cancel_callback)
        )
        return kb