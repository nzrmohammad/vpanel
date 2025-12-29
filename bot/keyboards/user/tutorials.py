# bot/keyboards/user/tutorials.py

from telebot import types
from ..base import BaseMenu
from bot.language import get_string

class UserTutorialsMenu(BaseMenu):
    """منوهای آموزش اتصال"""

    async def tutorial_main_menu(self, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(get_string('os_android', lang_code), "tutorial_os:android"),
            self.btn(get_string('os_windows', lang_code), "tutorial_os:windows"),
            self.btn(get_string('os_ios', lang_code), "tutorial_os:ios")
        )
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def tutorial_os_menu(self, os_type: str, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        buttons = []
        
        apps = []
        if os_type == 'android': apps = ['v2rayng', 'hiddify', 'happ']
        elif os_type == 'windows': apps = ['v2rayn', 'hiddify', 'happ']
        elif os_type == 'ios': apps = ['shadowrocket', 'streisand', 'hiddify', 'happ']

        for app in apps:
            app_key = f'app_{app}'
            buttons.append(self.btn(get_string(app_key, lang_code), f"tutorial_app:{os_type}:{app}"))

        kb.add(*buttons)
        kb.add(self.btn(f"🔙 {get_string('btn_back_to_os', lang_code)}", "tutorials"))
        return kb
        
    async def tutorial_link_menu(self, url: str, os_type: str, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(types.InlineKeyboardButton(get_string("btn_view_tutorial", lang_code), url=url))
        kb.add(self.back_btn(f"tutorial_os:{os_type}", lang_code))
        return kb