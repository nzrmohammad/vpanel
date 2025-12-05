# bot/menu/user.py

from telebot import types
from typing import List, Dict, Any
from .base import BaseMenu, CATEGORY_META
from ..language import get_string
from ..config import EMOJIS

class UserMenu(BaseMenu):
    
    async def main(self, is_admin: bool, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی اصلی ربات برای کاربر."""
        kb = self.create_markup(row_width=2)
        
        buttons = [
            (f"{EMOJIS['key']} {get_string('manage_account', lang_code)}", "manage"),
            (f"{EMOJIS['lightning']} {get_string('quick_stats', lang_code)}", "quick_stats"),
            (f"🛒 {get_string('view_plans', lang_code)}", "view_plans"),
            (f"💳 {get_string('wallet', lang_code)}", "wallet:main"),
            (f"🩺 {get_string('btn_connection_doctor', lang_code)}", "connection_doctor"),
            (f"📚 {get_string('btn_tutorials', lang_code)}", "tutorials"),
            (f"👤 {get_string('user_account_page_title', lang_code)}", "user_account"),
            (f"👥 {get_string('btn_referrals', lang_code)}", "referral:info"),
            (f"🏆 {get_string('btn_achievements', lang_code)}", "achievements"),
            (f"⚙️ {get_string('settings', lang_code)}", "settings"),
            (f"🎁 {get_string('birthday_gift', lang_code)}", "birthday_gift"),
            (f"💬 {get_string('support', lang_code)}", "support:new"),
            ("📅 اعلام حضور (سکه رایگان)", "daily_checkin"),
            (f"🌐 {get_string('btn_web_login', lang_code)}", "web_login")
        ]

        kb.add(*[self.btn(text, data) for text, data in buttons])

        if is_admin:
            kb.add(self.btn(f"{EMOJIS['crown']} پنل مدیریت", "admin:panel"))
        return kb

    async def accounts(self, rows: list, lang_code: str) -> types.InlineKeyboardMarkup:
        """لیست اکانت‌های کاربر جهت انتخاب."""
        kb = self.create_markup(row_width=1)
        for r in rows:
            name = r.get('name', get_string('unknown_user', lang_code))
            usage_str = f"{r.get('usage_percentage', 0):.0f}%"
            expire_days = r.get('expire')
            
            summary = f"{usage_str} - {expire_days} days" if expire_days is not None else usage_str
            kb.add(self.btn(f"📊 {name} ({summary})", f"acc_{r['id']}"))

        kb.add(self.btn(f"➕ {get_string('btn_add_account', lang_code)}", "add"))
        kb.add(self.back_btn("back", lang_code))
        return kb
    
    async def account_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی مدیریت یک اکانت خاص."""
        kb = self.create_markup(row_width=2)
        buttons_config = [
            (f"⏱ {get_string('btn_periodic_usage', lang_code)}", f"win_select_{uuid_id}"),
            (f"{EMOJIS['globe']} {get_string('btn_get_links', lang_code)}", f"getlinks_{uuid_id}"),
            (f"✏️ {get_string('btn_change_name', lang_code)}", f"changename_{uuid_id}"),
            (f"💳 {get_string('btn_payment_history', lang_code)}", f"payment_history_{uuid_id}_0"),
            (f"🗑 {get_string('btn_delete', lang_code)}", f"del_{uuid_id}"),
            (f"📈 {get_string('btn_usage_history', lang_code)}", f"usage_history_{uuid_id}")
        ]
        kb.add(*[self.btn(text, data) for text, data in buttons_config])

        # دکمه انتقال ترافیک همیشه باشد، هندلر چک می‌کند که فعال است یا نه
        kb.add(self.btn("💸 انتقال ترافیک", f"transfer_start_{uuid_id}"))
        kb.add(self.btn(f"🔙 {get_string('btn_back_to_list', lang_code)}", "manage"))
        return kb

    async def quick_stats_menu(self, num_accounts: int, current_page: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی آمار سریع (فقط دکمه‌های ناوبری)."""
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
        """
        منوی انتخاب سرور (کاملاً داینامیک).
        بر اساس دسترسی‌های کاربر دکمه‌ها را می‌سازد.
        """
        kb = self.create_markup(row_width=2)
        buttons = []
        
        # access_rights: {'has_access_de': True, ...}
        for key, has_access in access_rights.items():
            if not has_access: continue
            
            category = key.replace('has_access_', '')
            meta = CATEGORY_META.get(category, {'emoji': '', 'name': category.upper()})
            
            btn_text = f"{meta['name']} {meta['emoji']}"
            buttons.append(self.btn(btn_text, f"win_srv:{uuid_id}:{category}"))
        
        if buttons:
            kb.add(*buttons)

        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb

    async def plan_categories_menu(self, lang_code: str, available_categories: List[str]) -> types.InlineKeyboardMarkup:
        """
        منوی انتخاب دسته‌بندی برای خرید پلن (داینامیک).
        """
        kb = self.create_markup(row_width=2)
        
        buttons = []
        for cat in available_categories:
            if cat == 'combined':
                text = f"🚀 {get_string('btn_cat_combined', lang_code)}"
            else:
                meta = CATEGORY_META.get(cat, {'emoji': '🌍', 'name': cat.upper()})
                key = f"btn_cat_{cat}"
                trans = get_string(key, lang_code)
                final_name = trans if trans != key else meta['name']
                text = f"{meta['emoji']} {final_name}"
            
            buttons.append(self.btn(text, f"show_plans:{cat}"))

        kb.add(*buttons)
        
        kb.add(
            self.btn("➕ حجم یا زمان", "show_addons"),
            self.btn(get_string('btn_payment_methods', lang_code), "show_payment_options")
        )
        kb.add(self.btn("🛍️ فروشگاه دستاوردها", "shop:main"))
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def settings(self, settings_dict: dict, lang_code: str, access_rights: dict) -> types.InlineKeyboardMarkup:
        """منوی تنظیمات داینامیک بر اساس دسترسی‌های کاربر."""
        kb = self.create_markup()
        
        def get_status_emoji(val):
            return '✅' if val else '❌'

        # 1. گزارش‌ها
        kb.add(self.btn(f"🗓️ {get_string('reports_category', lang_code)}", "noop"))
        
        row_btns = []
        for label, key in [('daily_report', 'daily_reports'), ('weekly_report', 'weekly_reports'), ('monthly_report', 'monthly_reports')]:
            status = settings_dict.get(key, True)
            text = f"{get_string(label, lang_code)} {get_status_emoji(status)}"
            row_btns.append(self.btn(text, f"toggle:{key}"))
        kb.row(*row_btns)

        # 2. هشدارها
        kb.add(self.btn(f"🪫 {get_string('alerts_category', lang_code)}", "noop"))
        
        warning_buttons = []
        for key, has_access in access_rights.items():
            if not has_access: continue
            
            category = key.replace('has_access_', '')
            meta = CATEGORY_META.get(category, {'emoji': category.upper(), 'name': category})
            
            setting_key = f"data_warning_{category}"
            status = settings_dict.get(setting_key, True)
            
            text = f"{meta['emoji']} {get_status_emoji(status)}"
            warning_buttons.append(self.btn(text, f"toggle:{setting_key}"))

        if warning_buttons:
            for i in range(0, len(warning_buttons), 3):
                kb.row(*warning_buttons[i:i+3])

        # 3. سایر تنظیمات
        kb.add(self.btn(f"📢 {get_string('general_notifications_category', lang_code)}", "noop"))
        kb.row(
            self.btn(f"🏆 {get_status_emoji(settings_dict.get('achievement_alerts', True))}", "toggle:achievement_alerts"),
            self.btn(f"🎁 {get_status_emoji(settings_dict.get('promotional_alerts', True))}", "toggle:promotional_alerts")
        )

        kb.add(
            self.btn(f"🌐 {get_string('change_language', lang_code)}", "change_language"),
            self.back_btn("back", lang_code)
        )
        return kb

    async def achievement_shop_menu(self, user_points: int, access_rights: dict, shop_items: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """
        منوی فروشگاه دستاوردها.
        """
        kb = self.create_markup(row_width=2)
        
        day_items, data_items, lottery_items = [], [], []
        
        for item in shop_items:
            item_type = 'data' 
            if item.get('extra_days', 0) > 0: item_type = 'day'
            if 'lottery' in item.get('name', '').lower(): item_type = 'lottery'

            if item_type == 'lottery': lottery_items.append(item)
            elif item_type == 'day': day_items.append(item)
            else: data_items.append(item)

        def create_buy_btn(item):
            cost = item.get('price', 0)
            is_affordable = user_points >= cost
            emoji = "✅" if is_affordable else "❌"
            return self.btn(f"{emoji} {item['name']} ({int(cost)})", f"shop:confirm:{item['id']}")

        if data_items:
            kb.add(self.btn("📦 افزایش حجم", "noop"))
            kb.add(*[create_buy_btn(i) for i in data_items])
            
        if day_items:
            kb.add(self.btn("⏳ تمدید زمان", "noop"))
            kb.add(*[create_buy_btn(i) for i in day_items])
            
        if lottery_items:
            kb.add(self.btn("🎉 سرگرمی", "noop"))
            kb.add(*[create_buy_btn(i) for i in lottery_items])
            
        kb.add(self.btn("🎰 گردونه شانس", "lucky_spin_menu"))
        kb.add(self.btn("🔙 بازگشت", "view_plans"))
        return kb

    async def request_badge_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("💪 بدن‌سازی", "achievements:req:bodybuilder"),
            self.btn("🏊‍♂️ شنا", "achievements:req:water_athlete"),
            self.btn("🤸‍♀️ اریال ", "achievements:req:aerialist")
        )
        kb.add(self.btn("🔙 بازگشت به دستاوردها", "achievements"))
        return kb
    
    async def feedback_rating_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=5)
        stars = [self.btn("⭐️" * i, f"feedback:rating:{i}") for i in range(1, 6)]
        kb.add(*stars)
        kb.add(self.btn("لغو", "back"))
        return kb

    async def select_account_for_purchase_menu(self, user_uuids: list, plan_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """انتخاب اکانت برای اعمال پلن خریداری شده."""
        kb = self.create_markup(row_width=1)
        for u in user_uuids:
            text = f"👤 {u.get('name', get_string('unknown_user', lang_code))}"
            kb.add(self.btn(text, f"wallet:buy_for_account:{u['id']}:{plan_id}"))
        
        kb.add(self.back_btn("view_plans", lang_code))
        return kb
    
    async def wallet_main_menu(self, balance: float, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        balance_str = "{:,.0f}".format(balance)

        kb.add(self.btn(f"موجودی شما: {balance_str} تومان", "noop"))

        kb.add(
            self.btn(f"📜 {get_string('transaction_history', lang_code)}", "wallet:history"),
            self.btn(f"➕ {get_string('charge_wallet', lang_code)}", "wallet:charge")
        )
        kb.add(
            self.btn("💸 انتقال موجودی", "wallet:transfer_start"),
            self.btn("⚙️ تمدید خودکار", "wallet:settings")
        )
        kb.add(self.btn("🎁 خرید برای دیگران", "wallet:gift_start"))
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def wallet_settings_menu(self, auto_renew_status: bool, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        status_text = "✅ فعال" if auto_renew_status else "❌ غیرفعال"
        kb.add(self.btn(f"تمدید خودکار: {status_text}", "wallet:toggle_auto_renew"))
        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", "wallet:main"))
        return kb
    
    async def payment_options_menu(self, lang_code: str, online_link: str = None, card_info: dict = None) -> types.InlineKeyboardMarkup:
        """
        منوی انتخاب روش پرداخت.
        """
        kb = self.create_markup(row_width=2)
        
        if online_link:
            kb.add(self.btn("💳 پرداخت آنلاین (درگاه)", "noop", url=online_link))
        
        if card_info and card_info.get("card_number"):
            bank_name = card_info.get("bank_name", "کارت به کارت")
            kb.add(self.btn(f"📄 {bank_name}", "show_card_details"))

        kb.add(self.btn(get_string('btn_crypto_payment', lang_code), "coming_soon"))
        kb.add(self.back_btn("view_plans", lang_code))
        return kb
        
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
        
        if os_type == 'android': apps = ['v2rayng', 'hiddify', 'happ']
        elif os_type == 'windows': apps = ['v2rayn', 'hiddify', 'happ']
        elif os_type == 'ios': apps = ['shadowrocket', 'streisand', 'hiddify', 'happ']
        else: apps = []

        for app in apps:
            app_key = f'app_{app}'
            buttons.append(self.btn(get_string(app_key, lang_code), f"tutorial_app:{os_type}:{app}"))

        kb.add(*buttons)
        kb.add(self.btn(f"🔙 {get_string('btn_back_to_os', lang_code)}", "tutorials"))
        return kb
        
    async def get_links_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"📋 {get_string('btn_link_normal', lang_code)}", f"getlink_normal_{uuid_id}"),
            self.btn(f"📝 {get_string('btn_link_b64', lang_code)}", f"getlink_b64_{uuid_id}")
        )
        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb
    
    async def post_charge_menu(self, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🛒 مشاهده سرویس‌ها", "view_plans"),
            self.btn("🔙 بازگشت به کیف پول", "wallet:main")
        )
        return kb
    
    async def user_cancel_action(self, back_callback: str, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        kb = self.create_markup()
        cancel_text = get_string('btn_cancel_action', lang_code)
        kb.add(self.btn(f"✖️ {cancel_text}", back_callback))
        return kb