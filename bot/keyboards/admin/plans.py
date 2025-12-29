# bot/keyboards/admin/plans.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu

class AdminPlansMenu(BaseMenu):
    """مدیریت پلن‌ها و فروشگاه"""

    async def plan_management_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        cat_buttons = []
        for cat in categories:
            btn_text = f"{cat['emoji']} {cat['name']}"
            cat_buttons.append(self.btn(btn_text, f"admin:plan_show_category:{cat['code']}"))
        
        if cat_buttons: kb.add(*cat_buttons)
        kb.add(self.btn("🔙 بازگشت به پنل", "admin:panel"))
        return kb

    async def plan_type_selection_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(self.btn("🚀 ترکیبی (همه سرورها)", "admin:plan_add_type:combined"))
        
        cat_btns = [self.btn(f"{cat['emoji']} {cat['name']}", f"admin:plan_add_type:{cat['code']}") for cat in categories]
        if cat_btns: kb.add(*cat_btns)
            
        kb.add(self.btn("🔙 بازگشت", "admin:plan_manage"))
        return kb

    async def shop_management_menu(self, addons_list):
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        if not addons_list:
            keyboard.add(types.InlineKeyboardButton("❌ محصولی یافت نشد", callback_data="ignore"))
        else:
            for item in addons_list:
                status_icon = "🟢" if item['is_active'] else "🔴"
                btn_text = f"{status_icon} {item['name']} | 💰 {int(item['price'])}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:shop:detail:{item['id']}"))

        keyboard.add(types.InlineKeyboardButton("➕ افزودن محصول جدید", callback_data="admin:shop:add"))
        keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin:panel"))
        return keyboard

    async def shop_item_detail_menu(self, item):
        kb = types.InlineKeyboardMarkup(row_width=2)
        status_text = "فعال ✅" if item['is_active'] else "غیرفعال ❌"
        kb.add(self.btn(f"وضعیت: {status_text}", f"admin:shop:toggle:{item['id']}"))
        kb.add(self.btn("🗑 حذف محصول", f"admin:shop:del:{item['id']}"))
        kb.add(self.btn("🔙 بازگشت به لیست", "admin:shop:main"))
        return kb

    async def shop_cancel_menu(self):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:shop:cancel"))
        return kb