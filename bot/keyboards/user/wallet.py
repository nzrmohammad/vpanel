# bot/keyboards/user/wallet.py

from telebot import types
from typing import List, Dict, Any
from ..base import BaseMenu
from bot.language import get_string
from bot.database import db
from bot.formatters import user_formatter

class UserWalletMenu(BaseMenu):
    """مدیریت کیف پول، فروشگاه و خرید پلن"""

    async def wallet_main_menu(self, balance: float, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی اصلی کیف پول"""
        kb = self.create_markup(row_width=2)
        kb.add(self.btn(f"موجودی شما: {balance:,.0f} تومان", "noop"))
        
        kb.add(
            self.btn(f"📜 {get_string('transaction_history', lang_code)}", "wallet:history"),
            self.btn(f"➕ {get_string('charge_wallet', lang_code)}", "wallet:charge")
        )
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def plan_categories_menu(self, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        all_categories = await db.get_server_categories()
        active_codes = await db.get_active_location_codes()
        
        cat_buttons = []
        for cat in all_categories:
            if cat['code'] in active_codes:
                text = f"{cat['emoji']} {cat['name']}"
                cat_buttons.append(self.btn(text, f"show_plans:{cat['code']}"))

        if not cat_buttons:
             kb.add(self.btn("⚠️ در حال حاضر سروری موجود نیست", "noop"))
        else:
             kb.add(*cat_buttons)
             kb.add(self.btn("➕ حجم یا زمان", "show_addons"))
        
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def plan_category_menu(self, lang_code: str, user_balance: float, plans: list) -> types.InlineKeyboardMarkup:
        """نمایش لیست پلن‌ها"""
        kb = self.create_markup(row_width=1)
        
        balance_str = "{:,.0f}".format(user_balance)
        btn_balance = self.btn(f"💰 {balance_str} تومان", "wallet:main")
        btn_charge = self.btn(f"➕ {get_string('charge_wallet', lang_code)}", "wallet:charge")
        kb.row(btn_balance, btn_charge)
        
        for plan in plans:
            btn_text = await user_formatter.format_plan_btn(plan, user_balance)
            is_affordable = user_balance >= plan.get('price', 0)
            cb_data = f"wallet:buy_confirm:{plan['id']}" if is_affordable else "wallet:insufficient"
            kb.add(self.btn(btn_text, cb_data))

        kb.row(self.back_btn("view_plans", lang_code))
        return kb

    async def achievement_shop_menu(self, user_points: int, access_rights: dict, shop_items: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی فروشگاه امتیازها"""
        kb = self.create_markup(row_width=2)
        
        data_items, day_items, lottery_items = [], [], []
        
        for item in shop_items:
            target = item.get('target', 'all')
            if target != 'all':
                access_key = f"has_access_{target}"
                if not access_rights.get(access_key):
                    continue

            name_lower = item['name'].lower()
            if 'lottery' in name_lower:
                lottery_items.append(item)
            elif item.get('extra_days', 0) > 0 or item.get('days', 0) > 0:
                day_items.append(item)
            else:
                data_items.append(item)

        def make_btn(itm):
            cost = itm.get('cost', itm.get('price', 0))
            emoji = "✅" if user_points >= cost else "❌"
            item_id = itm.get('id') or itm.get('key') 
            return self.btn(f"{emoji} {itm['name']} ({int(cost)})", f"shop:confirm:{item_id}")

        if data_items:
            kb.add(self.btn("📦 افزایش حجم", "noop"))
            kb.add(*[make_btn(i) for i in data_items])
        if day_items:
            kb.add(self.btn("⏳ تمدید زمان", "noop"))
            kb.add(*[make_btn(i) for i in day_items])
        if lottery_items:
            kb.add(self.btn("🎉 سرگرمی", "noop"))
            kb.add(*[make_btn(i) for i in lottery_items])
            
        kb.add(self.btn("🎰 گردونه شانس", "lucky_spin_menu"))
        kb.add(self.back_btn("view_plans", "fa"))
        return kb

    async def payment_options_menu(self, lang_code: str, payment_methods: list, back_callback: str = "wallet:main") -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        buttons = []
        for pm in payment_methods:            
            emoji = "💳" if pm['type'] == 'card' else "💎"
            title = pm.get('title', 'روش پرداخت')
            buttons.append(self.btn(f"{emoji} {title}", f"payment:select:{pm['id']}"))

        if buttons:
            kb.add(*buttons)
        kb.add(self.back_btn(back_callback, lang_code))
        return kb

    async def select_account_for_purchase_menu(self, user_uuids: list, plan_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        for u in user_uuids:
            text = f"👤 {u.get('name', get_string('unknown_user', lang_code))}"
            kb.add(self.btn(text, f"wallet:buy_for_account:{u['id']}:{plan_id}"))
        kb.add(self.back_btn("view_plans", lang_code))
        return kb

    async def select_destination_menu(self, service_list: list, plan_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        new_service_text = f"🆕 {get_string('btn_create_new_service', lang_code)}" 
        kb.add(self.btn(new_service_text, f"wallet:preview_new:{plan_id}"))
        
        for item in service_list:
            kb.add(self.btn(item['text'], f"wallet:preview_renew:{item['id']}:{plan_id}"))
        kb.add(self.back_btn("view_plans", lang_code))
        return kb

    async def post_charge_menu(self, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🛒 مشاهده سرویس‌ها", "view_plans"),
            self.btn("🔙 بازگشت به کیف پول", "wallet:main")
        )
        return kb

    async def wallet_history_menu(self, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(self.back_btn("wallet:main", lang_code))
        return kb

    async def confirm_payment_menu(self, confirm_callback: str, cancel_callback: str = "view_plans", lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"❌ {get_string('btn_cancel', lang_code)}", cancel_callback),
            self.btn(f"✅ {get_string('btn_pay', lang_code)}", confirm_callback)
        )
        return kb