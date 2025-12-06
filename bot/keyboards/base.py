# bot/keyboards/base.py
from telebot import types
from ..language import get_string
from ..config import EMOJIS, PAGE_SIZE

# ✅ اضافه کردن این دیکشنری برای رفع ارور
CATEGORY_META = {
    'de': {'emoji': '🇩🇪', 'name': 'Germany'},
    'fr': {'emoji': '🇫🇷', 'name': 'France'},
    'tr': {'emoji': '🇹🇷', 'name': 'Turkey'},
    'us': {'emoji': '🇺🇸', 'name': 'USA'},
    'ro': {'emoji': '🇷🇴', 'name': 'Romania'},
    'fi': {'emoji': '🇫🇮', 'name': 'Finland'},
    'ir': {'emoji': '🇮🇷', 'name': 'Iran'},
    'supp': {'emoji': '🆘', 'name': 'Support'},
    'combined': {'emoji': '🚀', 'name': 'Combined'}
}

class BaseMenu:
    """کلاس والد برای متدهای مشترک ساخت کیبورد"""

    def create_markup(self, row_width=2) -> types.InlineKeyboardMarkup:
        return types.InlineKeyboardMarkup(row_width=row_width)

    def btn(self, text: str, callback_data: str, url: str = None) -> types.InlineKeyboardButton:
        """تابع کمکی برای ساخت سریع دکمه"""
        return types.InlineKeyboardButton(text, callback_data=callback_data, url=url)

    def back_btn(self, callback_data: str, lang_code: str) -> types.InlineKeyboardButton:
        """دکمه بازگشت استاندارد"""
        return self.btn(f"🔙 {get_string('back', lang_code)}", callback_data)

    async def create_pagination(self, base_callback: str, current_page: int, total_items: int, back_callback: str, lang_code: str) -> types.InlineKeyboardMarkup:
        """ساخت منوی صفحه‌بندی (Pagination) به صورت Async"""
        kb = self.create_markup(row_width=2)
        
        # دکمه‌های ناوبری
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(self.btn(f"⬅️ {get_string('btn_prev_page', lang_code)}", f"{base_callback}:{current_page - 1}"))
        
        if (current_page + 1) * PAGE_SIZE < total_items:
            nav_buttons.append(self.btn(f"{get_string('btn_next_page', lang_code)} ➡️", f"{base_callback}:{current_page + 1}"))

        if nav_buttons:
            kb.row(*nav_buttons)

        kb.add(self.back_btn(back_callback, lang_code))
        return kb