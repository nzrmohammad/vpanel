# bot/keyboards/admin/users.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu
from bot.database import db

class AdminUsersMenu(BaseMenu):
    """مدیریت کاربران، جستجو و ویرایش"""

    async def management_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی انتخاب پنل برای مدیریت کاربران"""
        kb = self.create_markup(row_width=2)
        categories = await db.get_server_categories()
        cat_map = {c['code']: c['emoji'] for c in categories}
        
        if not panels:
            kb.add(self.btn("⚠️ هیچ پنلی یافت نشد (افزودن پنل)", "admin:panel_add_start"))
        else:
            kb.add(self.btn("➕ افزودن کاربر جدید (سراسری)", "admin:add_user:all"))

            buttons = []
            for p in panels:
                flag = cat_map.get(p.get('category'), "")
                btn_text = f"{p['name']} {flag} ({p['panel_type']})"
                buttons.append(self.btn(btn_text, f"admin:manage_single_panel:{p['id']}:{p['panel_type']}"))
            
            kb.add(*buttons)

        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def manage_single_panel_menu(self, panel_id: int, panel_type: str, panel_name: str) -> types.InlineKeyboardMarkup:
        """منوی عملیات روی یک پنل خاص"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"📋 لیست کاربران", f"admin:p_users:{panel_id}:0"),
            self.btn(f"➕ افزودن کاربر", f"admin:add_user_to_panel:{panel_id}")
        )
        kb.add(self.btn("🔙 بازگشت به لیست سرورها", "admin:management_menu"))
        return kb

    async def search_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔎 نام / یوزرنیم / UUID", "admin:sg"),
            self.btn("🆔 آیدی عددی تلگرام", "admin:search_by_tid")
        )
        kb.add(self.btn("🔥 پاکسازی کاربر (Purge)", "admin:purge_user"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def user_interactive_menu(self, identifier: str, is_active: bool, panel_type: str, back_callback: str = None) -> types.InlineKeyboardMarkup:
        """منوی مدیریت تکی کاربر"""
        kb = self.create_markup(row_width=2)
        base = f"{identifier}"
        ctx_param = "s" if back_callback and "search" in back_callback else "x"
        
        kb.add(
            self.btn("⚙️ تغییر وضعیت", f"admin:us_tgl:{base}"),
            self.btn("📝 یادداشت", f"admin:us_note:{base}:{ctx_param}")
        )
        kb.add(
            self.btn("💳 ثبت پرداخت", f"admin:us_lpay:{base}"),
            self.btn("📜 سابقه پرداخت", f"admin:us_phist:{identifier}:0")
        )
        kb.add(
            self.btn("💰 شارژ کیف پول", f"admin:us_mchg:{base}:x"),
            self.btn("💸 برداشت وجه", f"admin:us_wdrw:{base}")
        )
        kb.add(
            self.btn("🔧 ویرایش کاربر", f"admin:us_edt:{base}"),
            self.btn("📱 حذف دستگاه‌ها", f"admin:us_ddev:{base}")
        )
        kb.add(
            self.btn("♻️ تنظیمات ریست", f"admin:us_reset_menu:{base}:x"),
            self.btn("⚠️ ارسال هشدار", f"admin:us_warn_menu:{base}:x")
        )
        kb.add(self.btn("🌍 مدیریت دسترسی نودها", f"admin:us_acc_p_list:{identifier}"))
        kb.add(
            self.btn("🔄 تمدید اشتراک", f"admin:renew_sub_menu:{base}"),
            self.btn("🗑 حذف کامل", f"admin:us_delc:{base}")
        )
        
        final_back = back_callback or "admin:management_menu"
        kb.add(self.btn("🔙 بازگشت", final_back))
        return kb

    async def edit_user_panel_select_menu(self, identifier: str, panels: list) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        all_panel_btn = None
        other_buttons = []
        
        for p in panels:
            cb_data = f"admin:ep:{p['id']}:{identifier}"
            display_text = f"{p['flag']} {p['name']}"
            button = self.btn(display_text, cb_data)
            if p['id'] == 'all':
                all_panel_btn = button
            else:
                other_buttons.append(button)
        
        if all_panel_btn: kb.row(all_panel_btn)
        if other_buttons: kb.add(*other_buttons)
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def edit_user_action_menu(self, identifier: str, panel_target: str) -> types.InlineKeyboardMarkup:
        return await self._create_resource_action_menu(
            base_callback="admin:ae",
            args=[panel_target, identifier],
            back_callback=f"admin:us_edt:{identifier}"
        )

    async def _create_resource_action_menu(self, base_callback: str, args: list, back_callback: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        suffix = ":".join(map(str, args))
        kb.add(
            self.btn("➕ افزودن حجم", f"{base_callback}:add_gb:{suffix}"),
            self.btn("➕ افزودن روز", f"{base_callback}:add_days:{suffix}")
        )
        kb.add(self.btn("🔙 بازگشت", back_callback))
        return kb

    async def user_country_access_menu(self, identifier: str, all_categories: list, user_allowed: list) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        buttons = []
        for cat in all_categories:
            code, name, emoji = cat['code'], cat['name'], cat['emoji']
            is_allowed = code in user_allowed
            status_icon = "✅" if is_allowed else "❌"
            buttons.append(self.btn(f"{status_icon} {emoji} {name}", f"admin:us_access_toggle:{identifier}:{code}"))
            
        if buttons: kb.add(*buttons)
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def user_access_panel_list_menu(self, identifier: str, panels: list, panel_access: dict = None, cat_map: dict = None) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        if panel_access is None: panel_access = {}
        if cat_map is None: cat_map = {}
        
        if not panels:
            kb.add(self.btn("⚠️ هیچ پنلی یافت نشد", "noop"), self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
            return kb

        buttons = []
        for p in panels:
            p_id = str(p['id'])
            allowed_codes = panel_access.get(p_id, [])
            flags = ""
            if allowed_codes:
                shown_flags = [cat_map.get(code, code) for code in allowed_codes[:2]] 
                flags = "".join(shown_flags) + ("+" if len(allowed_codes) > 2 else "")
                flags = f" {flags}"
            
            p_type_short = p.get('panel_type', '')[:3].upper()
            buttons.append(self.btn(f"📂 {p['name']} ({p_type_short}){flags}", f"admin:us_acc_n_list:{identifier}:{p['id']}"))

        kb.add(*buttons)
        kb.row(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def user_access_nodes_menu(self, identifier: str, panel_id: int, panel_name: str, nodes: list, allowed_nodes: list) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        buttons = []
        for node in nodes:
            is_allowed = node['code'] in allowed_nodes
            status = "✅" if is_allowed else "❌"
            buttons.append(self.btn(f"{status} {node['flag']} {node['name']}", f"admin:us_acc_tgl:{identifier}:{panel_id}:{node['code']}"))
            
        if buttons: kb.add(*buttons)
        else: kb.add(self.btn("⚠️ هیچ نودی برای این پنل تعریف نشده است", "noop"))
            
        kb.row(self.btn("🔙 بازگشت به لیست پنل‌ها", f"admin:us_acc_p_list:{identifier}"))
        return kb

    async def user_access_aggregated_menu(self, target_id, panels_data, user_panel_access):
        markup = types.InlineKeyboardMarkup(row_width=2)
        for item in panels_data:
            panel, nodes, flag = item['panel'], item['nodes'], item['flag']
            panel_id = str(panel['id'])
            current_access = user_panel_access.get(panel_id, [])

            markup.add(types.InlineKeyboardButton(f"📂 {panel['name']} ({panel['panel_type']}) {flag}", callback_data="admin:none"))
            node_btns = []
            for node in nodes:
                status_icon = "✅" if node['code'] in current_access else "❌"
                callback = f"admin:tgl_n_acc:{target_id}:{panel['id']}:{node['code']}"
                node_btns.append(types.InlineKeyboardButton(f"{status_icon} {node['flag']} {node['name']}", callback_data=callback))
            if node_btns: markup.add(*node_btns)

        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"admin:us:{target_id}"))
        return markup

    async def award_badge_menu(self, identifier: str, context_suffix: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        badges = [('🏊‍♂️ شنا', 'water_athlete'), ('🏋️‍♂️ بدن‌سازی', 'bodybuilder'), ('💎 حامی ویژه', 'vip_friend'), ('🌟 اسطوره', 'legend')]
        for name, code in badges:
            kb.add(self.btn(name, f"admin:awd_b:{code}:{identifier}{context_suffix}"))
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def select_plan_for_renew_menu(self, identifier: str, context_suffix: str, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        for plan in plans:
            kb.add(self.btn(plan['name'], f"admin:renew_apply_plan:{plan['id']}:{identifier}{context_suffix}"))
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def reset_usage_selection_menu(self, identifier: str, base_callback: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(self.btn("تمام پنل‌ها", f"admin:{base_callback}:both:{identifier}"))
        kb.add(self.btn("🔙 لغو", f"admin:us:{identifier}"))
        return kb

    async def confirm_delete(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("❌ بله، حذف کن", f"admin:del_a:confirm:{panel}:{identifier}"),
            self.btn("✅ نه، لغو کن", f"admin:del_a:cancel:{panel}:{identifier}")
        )
        return kb