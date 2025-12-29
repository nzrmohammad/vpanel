# bot/keyboards/user/services.py

from telebot import types
from typing import Dict
from ..base import BaseMenu
from bot.language import get_string
from bot.database import db
from bot.config import EMOJIS

class UserServicesMenu(BaseMenu):
    """مدیریت سرویس‌ها و اکانت‌های کاربر"""

    async def accounts(self, rows: list, lang_code: str) -> types.InlineKeyboardMarkup:
        """لیست سرویس‌های کاربر"""
        kb = self.create_markup(row_width=1)
        for r in rows:
            name = r.get('name', get_string('unknown_user', lang_code))
            usage = f"{r.get('usage_percentage', 0):.0f}%"
            expire = f" - {r['expire']} days" if r.get('expire') is not None else ""
            
            button_text = f"📊 {name} ({usage}{expire})"
            kb.add(self.btn(button_text, f"acc_{r['id']}"))

        kb.add(self.btn(f"➕ {get_string('btn_add_account', lang_code)}", "add"))
        kb.add(self.back_btn("back", lang_code))
        return kb
    
    async def account_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی مدیریت یک سرویس خاص"""
        kb = self.create_markup(row_width=2)
        
        kb.add(
            self.btn(f"⏱ {get_string('btn_periodic_usage', lang_code)}", f"win_select_{uuid_id}"),
            self.btn(f"{EMOJIS['globe']} {get_string('btn_get_links', lang_code)}", f"getlinks_{uuid_id}")
        )
        kb.add(
            self.btn(f"✏️ {get_string('btn_change_name', lang_code)}", f"changename_{uuid_id}"),
            self.btn(f"💳 {get_string('btn_payment_history', lang_code)}", f"payment_history_{uuid_id}_0")
        )
        kb.add(
            self.btn(f"🗑 {get_string('btn_delete', lang_code)}", f"del_{uuid_id}"),
            self.btn(f"📈 {get_string('btn_usage_history', lang_code)}", f"usage_history_{uuid_id}")
        )
        kb.add(self.back_btn("manage", lang_code))
        return kb

    async def quick_stats_menu(self, num_accounts: int, current_page: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        nav_buttons = []
        
        if num_accounts > 1:
            if current_page > 0:
                nav_buttons.append(self.btn(f"⬅️ {get_string('btn_prev_account', lang_code)}", f"qstats_acc_page_{current_page - 1}"))
            if current_page < num_accounts - 1:
                nav_buttons.append(self.btn(f"{get_string('btn_next_account', lang_code)} ➡️", f"qstats_acc_page_{current_page + 1}"))

        if nav_buttons:
            kb.row(*nav_buttons)
            
        kb.add(self.btn(f"🔙 {get_string('back_to_main_menu', lang_code)}", "back"))
        return kb

    async def server_selection_menu(self, uuid_id: int, access_rights: Dict[str, bool], lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی انتخاب سرور برای مشاهده آمار"""
        kb = self.create_markup(row_width=2)
        buttons = []
        
        categories_db = await db.get_server_categories()
        cat_map = {c['code']: c for c in categories_db}

        for key, has_access in access_rights.items():
            if not has_access: continue
            
            cat_code = key.replace('has_access_', '')
            cat_info = cat_map.get(cat_code)
            
            if cat_info:
                btn_text = f"{cat_info['emoji']} {cat_info['name']}"
                buttons.append(self.btn(btn_text, f"win_srv:{uuid_id}:{cat_code}"))
            else:
                buttons.append(self.btn(f"🚩 {cat_code.upper()}", f"win_srv:{uuid_id}:{cat_code}"))
        
        if buttons:
            kb.add(*buttons)

        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb

    async def get_links_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"📋 {get_string('btn_link_normal', lang_code)}", f"getlink_normal_{uuid_id}"),
            self.btn(f"📝 {get_string('btn_link_b64', lang_code)}", f"getlink_b64_{uuid_id}")
        )
        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb

    async def account_not_found_menu(self, acc_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        del_text = get_string('btn_delete_from_bot', lang_code)
        kb.add(self.btn(del_text, f"del_{acc_id}"))
        kb.add(self.back_btn("manage", lang_code))
        return kb