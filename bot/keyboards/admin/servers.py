# bot/keyboards/admin/servers.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu
from bot.database import db

class AdminServersMenu(BaseMenu):
    """مدیریت سرورها و اتصالات"""

    async def panel_list_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """لیست پنل‌های متصل"""
        kb = self.create_markup(row_width=2)
        categories = await db.get_server_categories()
        cat_map = {c['code']: c['emoji'] for c in categories}
        
        if not panels:
            kb.row(self.btn("⚠️ هنوز پنلی اضافه نکرده‌اید", "noop"))
        
        panel_buttons = []
        for p in panels:
            status = "✅" if p['is_active'] else "❌"
            flag = cat_map.get(p.get('category'), "")
            btn_text = f"{status} {p['name']} {flag} ({p['panel_type']})"
            panel_buttons.append(self.btn(btn_text, f"admin:panel_details:{p['id']}"))
            
        if panel_buttons: kb.add(*panel_buttons)
            
        kb.row(
            self.btn("🌍 دسته بندی کشورها", "admin:cat_manage"),
            self.btn("➕ افزودن پنل", "admin:panel_add_start")
        )
        kb.row(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_category_selection_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2) 
        buttons = [self.btn(f"{cat['emoji']} {cat['name']}", f"admin:panel_set_cat:{cat['code']}") for cat in categories]
        if buttons: kb.add(*buttons)
        kb.row(self.btn("🔙 انصراف", "admin:panel_manage"))
        return kb

    async def mapping_main_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📋 لیست اتصالات موجود", "admin:mapping_list:0"),
            self.btn("➕ ایجاد اتصال جدید", "admin:add_mapping")
        )
        kb.add(self.btn("🔙 بازگشت به پنل", "admin:panel"))
        return kb

    async def mapping_list_menu(self, mappings: list, page: int, total_count: int, page_size: int) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)  
        if not mappings:
            kb.add(self.btn("➕ ایجاد اتصال جدید", "admin:add_mapping"))
        
        map_buttons = []
        for m in mappings:
            uuid_short = str(m['hiddify_uuid'])[:5]
            btn_text = f"🗑 {m['marzban_username']} ({uuid_short})"
            map_buttons.append(self.btn(btn_text, f"admin:del_map_conf:{m['hiddify_uuid']}:{page}"))
        kb.add(*map_buttons)
            
        nav_buttons = []
        if page > 0: nav_buttons.append(self.btn("⬅️ قبلی", f"admin:mapping_list:{page - 1}"))
        if (page + 1) * page_size < total_count: nav_buttons.append(self.btn("بعدی ➡️", f"admin:mapping_list:{page + 1}"))
        if nav_buttons: kb.row(*nav_buttons)
            
        kb.add(self.btn("🔙 بازگشت", "admin:mapping_menu"))
        return kb

    async def confirm_delete_mapping_menu(self, uuid_str: str, page: int) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، حذف کن", f"admin:del_map_exec:{uuid_str}:{page}"),
            self.btn("❌ انصراف", f"admin:mapping_list:{page}") 
        )
        return kb

    async def server_selection_menu(self, base_callback: str, panels: List[Dict[str, Any]] = None) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        if panels:
            for p in panels:
                kb.add(self.btn(p['name'], f"{base_callback}:{p['id']}"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb