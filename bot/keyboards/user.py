# bot/keyboards/user.py

from telebot import types
from typing import List, Dict, Any, Optional
from .base import BaseMenu, CATEGORY_META
from ..language import get_string
from bot.database import db
from ..config import (EMOJIS)

class UserMenu(BaseMenu):
    """
    کلاس مدیریت کیبوردهای پنل کاربری.
    تمام متدها به صورت Async تعریف شده‌اند تا با ساختار جدید سازگار باشند.
    """

    async def main(self, is_admin: bool, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی اصلی ربات برای کاربران"""
        kb = self.create_markup(row_width=2)
        
        # تعریف دکمه‌ها (متن و کالبک)
        buttons = [
            (f"{EMOJIS['key']} {get_string('manage_account', lang_code)}", "manage"),
            (f"{EMOJIS['lightning']} {get_string('quick_stats', lang_code)}", "quick_stats"),
            (f"🛒 {get_string('view_plans', lang_code)}", "view_plans"),
            (f"💳 {get_string('wallet', lang_code)}", "wallet:main"),
            (f"📚 {get_string('btn_tutorials', lang_code)}", "tutorials"),
            (f"👤 {get_string('user_account_page_title', lang_code)}", "user_account"),
            (f"👥 {get_string('btn_referrals', lang_code)}", "referral:info"),
            (f"🏆 {get_string('btn_achievements', lang_code)}", "achievements"),
            (f"⚙️ {get_string('settings', lang_code)}", "settings"),
            (f"🎁 {get_string('birthday_gift', lang_code)}", "birthday_gift"),
            (f"💬 {get_string('support', lang_code)}", "support:new"),
            (f"🌐 {get_string('btn_web_login', lang_code)}", "web_login")
        ]

        # افزودن دکمه‌ها به صورت جفتی
        for i in range(0, len(buttons), 2):
            b1 = self.btn(buttons[i][0], buttons[i][1])
            if i + 1 < len(buttons):
                b2 = self.btn(buttons[i+1][0], buttons[i+1][1])
                kb.row(b1, b2)
            else:
                kb.row(b1)

        # دکمه پنل مدیریت (مخصوص ادمین‌ها)
        if is_admin:
            kb.add(self.btn(f"{EMOJIS['crown']} پنل مدیریت", "admin:panel"))
            
        return kb

    async def accounts(self, rows: list, lang_code: str) -> types.InlineKeyboardMarkup:
        """لیست سرویس‌های کاربر"""
        kb = self.create_markup(row_width=1)
        for r in rows:
            name = r.get('name', get_string('unknown_user', lang_code))
            usage = f"{r.get('usage_percentage', 0):.0f}%"
            # نمایش روزهای باقی‌مانده اگر موجود باشد
            expire = f" - {r['expire']} days" if r.get('expire') is not None else ""
            
            button_text = f"📊 {name} ({usage}{expire})"
            kb.add(self.btn(button_text, f"acc_{r['id']}"))

        kb.add(self.btn(f"➕ {get_string('btn_add_account', lang_code)}", "add"))
        kb.add(self.back_btn("back", lang_code))
        return kb
    
    async def account_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی مدیریت یک سرویس خاص (دریافت لینک، تمدید و...)"""
        # دریافت مقدار از دیتابیس (خروجی رشته است)
        enable_transfer = await db.get_config('enable_traffic_transfer', 'True')
        
        kb = self.create_markup(row_width=2)
        
        # ردیف ۱: آمار مصرف و دریافت لینک
        kb.add(
            self.btn(f"⏱ {get_string('btn_periodic_usage', lang_code)}", f"win_select_{uuid_id}"),
            self.btn(f"{EMOJIS['globe']} {get_string('btn_get_links', lang_code)}", f"getlinks_{uuid_id}")
        )
        
        # ردیف ۲: تغییر نام و تاریخچه پرداخت
        kb.add(
            self.btn(f"✏️ {get_string('btn_change_name', lang_code)}", f"changename_{uuid_id}"),
            self.btn(f"💳 {get_string('btn_payment_history', lang_code)}", f"payment_history_{uuid_id}_0")
        )
        
        # ردیف ۳: حذف و تاریخچه مصرف
        kb.add(
            self.btn(f"🗑 {get_string('btn_delete', lang_code)}", f"del_{uuid_id}"),
            self.btn(f"📈 {get_string('btn_usage_history', lang_code)}", f"usage_history_{uuid_id}")
        )
        
        # اصلاح شرط: چک کردن مقدار رشته‌ای به صورت حروف کوچک
        if str(enable_transfer).lower() == 'true':
            kb.add(self.btn("💸 انتقال ترافیک", f"transfer_start_{uuid_id}"))
            
        kb.add(self.back_btn("manage", lang_code))
        return kb

    async def quick_stats_menu(self, num_accounts: int, current_page: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی آمار سریع (فقط دکمه‌های نویگیشن)"""
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
        """منوی انتخاب سرور برای مشاهده آمار (بر اساس دسترسی کاربر)"""
        kb = self.create_markup(row_width=2)
        buttons = []
        
        # تولید دکمه‌ها بر اساس دسترسی‌های کاربر
        for key, has_access in access_rights.items():
            if not has_access: continue
            
            # استخراج کد کشور از کلید (مثلاً has_access_de -> de)
            category = key.replace('has_access_', '')
            meta = CATEGORY_META.get(category, {'emoji': '', 'name': category.upper()})
            
            btn_text = f"{meta['name']} {meta['emoji']}"
            buttons.append(self.btn(btn_text, f"win_srv:{uuid_id}:{category}"))
        
        if buttons:
            kb.add(*buttons)

        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb


    async def plan_categories_menu(self, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی انتخاب دسته‌بندی (کاملاً داینامیک از دیتابیس)"""
        kb = self.create_markup(row_width=2)
        
        # 1. دریافت لیست فعال کشورها از دیتابیس
        categories = await db.get_server_categories()
        
        # 2. ساخت دکمه‌ها
        cat_buttons = []
        for cat in categories:
            # cat شامل: code, name, emoji
            text = f"{cat['emoji']} {cat['name']}"
            cat_buttons.append(self.btn(text, f"show_plans:{cat['code']}"))

        kb.add(*cat_buttons)
        
        # 3. دکمه‌های ثابت پایین
        kb.add(self.btn("➕ حجم یا زمان", "show_addons"),self.btn("🛍️ فروشگاه دستاوردها", "shop:main"))
        kb.add(self.back_btn("back", lang_code))
        
        return kb

    async def plan_category_menu(self, lang_code: str, user_balance: float, plans: list) -> types.InlineKeyboardMarkup:
        """
        نمایش لیست پلن‌های موجود در یک دسته‌بندی خاص
        به همراه وضعیت موجودی کاربر
        """
        kb = self.create_markup(row_width=1)
        
        # نمایش موجودی
        balance_str = "{:,.0f}".format(user_balance)
        kb.add(self.btn(f"موجودی: {balance_str} تومان", "wallet:main"))
        
        for plan in plans:
            price = plan.get('price', 0)
            is_affordable = user_balance >= price
            emoji = "✅" if is_affordable else "❌"
            price_str = "{:,.0f}".format(price)
            
            btn_text = f"{emoji} {plan.get('name')} ({price_str} تومان)"
            # ارسال ID پلن برای پردازش در هندلر
            cb_data = f"wallet:buy_confirm:{plan['id']}" if is_affordable else "wallet:insufficient"
            
            kb.add(self.btn(btn_text, cb_data))

        kb.add(self.btn(f"➕ {get_string('charge_wallet', lang_code)}", "wallet:charge"))
        kb.add(self.back_btn("view_plans", lang_code))
        return kb

    async def settings(self, settings_dict: dict, lang_code: str, access: dict) -> types.InlineKeyboardMarkup:
        """منوی تنظیمات (گزارش‌ها و هشدارها)"""
        kb = self.create_markup()
        
        def status(key):
            return '✅' if settings_dict.get(key, True) else '❌'

        # بخش ۱: گزارش‌ها
        kb.add(self.btn(f"🗓️ {get_string('reports_category', lang_code)}", "noop"))
        kb.row(
            self.btn(f"📊 {get_string('daily_report', lang_code)} {status('daily_reports')}", "toggle:daily_reports"),
            self.btn(f"📅 {get_string('weekly_report', lang_code)} {status('weekly_reports')}", "toggle:weekly_reports")
        )
        kb.add(self.btn(f"📆 {get_string('monthly_report', lang_code)} {status('monthly_reports')}", "toggle:monthly_reports"))

        # بخش ۲: هشدارها (فیلتر شده بر اساس دسترسی کاربر)
        kb.add(self.btn(f"🪫 {get_string('alerts_category', lang_code)}", "noop"))
        
        # دریافت لیست کامل کشورها از دیتابیس
        categories_list = await db.get_server_categories()
        
        alert_btns = []
        for cat in categories_list:
            cat_code = cat['code']
            
            # --- تغییر جدید: بررسی دسترسی کاربر ---
            # اگر دیکشنری access وجود نداشت یا کلید دسترسی این کشور True نبود، از این مورد عبور کن
            # مثال کلید: has_access_de
            if not access or not access.get(f"has_access_{cat_code}"):
                continue
            # ---------------------------------------

            emoji = cat['emoji']
            
            # کلید تنظیمات برای این کشور
            setting_key = f"data_warning_{cat_code}"
            
            # ساخت دکمه
            alert_btns.append(self.btn(f"{emoji} {status(setting_key)}", f"toggle:{setting_key}"))
        
        if alert_btns:
            # دکمه‌ها را ۳ تایی در هر ردیف می‌چینیم
            for i in range(0, len(alert_btns), 3):
                kb.row(*alert_btns[i:i+3])
        else:
            # اگر لیست خالی بود، یعنی کاربر به هیچ کشوری دسترسی ندارد (سرویس فعال ندارد)
            kb.add(self.btn("⚠️ سرویس فعالی ندارید", "noop"))

        # بخش ۳: عمومی
        kb.add(self.btn(f"📢 {get_string('general_notifications_category', lang_code)}", "noop"))
        kb.row(
            self.btn(f"🏆 {status('achievement_alerts')}", "toggle:achievement_alerts"),
            self.btn(f"🎁 {status('promotional_alerts')}", "toggle:promotional_alerts")
        )

        kb.add(
            self.btn(f"🌐 {get_string('change_language', lang_code)}", "change_language"),
            self.back_btn("back", lang_code)
        )
        return kb

    async def achievement_shop_menu(self, user_points: int, access_rights: dict, shop_items: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی فروشگاه امتیازها"""
        kb = self.create_markup(row_width=2)
        
        # تفکیک آیتم‌ها
        data_items = []
        day_items = []
        lottery_items = []
        
        for item in shop_items:
            # فیلتر کردن آیتم‌ها بر اساس دسترسی کاربر (مثلا فقط کسانی که سرور آلمان دارند حجم آلمان بخرند)
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

        # تابع کمکی ساخت دکمه خرید
        def make_btn(itm):
            cost = itm.get('cost', itm.get('price', 0))
            emoji = "✅" if user_points >= cost else "❌"
            # استفاده از شناسه یا کلید آیتم
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
        kb.add(self.back_btn("view_plans", "fa")) # زبان را می‌توان از آرگومان گرفت
        return kb

    async def wallet_main_menu(self, balance: float, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی اصلی کیف پول"""
        kb = self.create_markup(row_width=2)
        kb.add(self.btn(f"موجودی شما: {balance:,.0f} تومان", "noop"))
        
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
        """تنظیمات تمدید خودکار کیف پول"""
        kb = self.create_markup(row_width=1)
        status_text = "✅ فعال" if auto_renew_status else "❌ غیرفعال"
        
        kb.add(self.btn(f"تمدید خودکار: {status_text}", "wallet:toggle_auto_renew"))
        kb.add(self.back_btn("wallet:main", lang_code))
        return kb
    
    async def payment_options_menu(self, lang_code: str, payment_methods: list, back_callback: str = "wallet:main") -> types.InlineKeyboardMarkup:
        """
        منوی انتخاب روش پرداخت (پویا از دیتابیس)
        payment_methods: لیستی از دیکشنری‌های روش پرداخت
        """
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

    async def tutorial_main_menu(self, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی انتخاب سیستم عامل برای آموزش"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(get_string('os_android', lang_code), "tutorial_os:android"),
            self.btn(get_string('os_windows', lang_code), "tutorial_os:windows"),
            self.btn(get_string('os_ios', lang_code), "tutorial_os:ios")
        )
        kb.add(self.back_btn("back", lang_code))
        return kb

    async def tutorial_os_menu(self, os_type: str, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی انتخاب نرم‌افزار بر اساس سیستم عامل"""
        kb = self.create_markup(row_width=2)
        buttons = []
        
        apps = []
        if os_type == 'android': apps = ['v2rayng', 'hiddify', 'happ']
        elif os_type == 'windows': apps = ['v2rayn', 'hiddify', 'happ']
        elif os_type == 'ios': apps = ['shadowrocket', 'streisand', 'hiddify', 'happ']

        for app in apps:
            app_key = f'app_{app}'
            # کلید ترجمه باید در فایل زبان موجود باشد
            buttons.append(self.btn(get_string(app_key, lang_code), f"tutorial_app:{os_type}:{app}"))

        kb.add(*buttons)
        kb.add(self.btn(f"🔙 {get_string('btn_back_to_os', lang_code)}", "tutorials"))
        return kb
        
    async def get_links_menu(self, uuid_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """منوی دریافت لینک‌های اتصال"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn(f"📋 {get_string('btn_link_normal', lang_code)}", f"getlink_normal_{uuid_id}"),
            self.btn(f"📝 {get_string('btn_link_b64', lang_code)}", f"getlink_b64_{uuid_id}")
        )
        kb.add(self.btn(f"🔙 {get_string('back', lang_code)}", f"acc_{uuid_id}"))
        return kb
    
    async def feedback_rating_menu(self) -> types.InlineKeyboardMarkup:
        """منوی نظرسنجی ستاره‌ای"""
        kb = self.create_markup(row_width=5)
        stars = [self.btn("⭐️" * i, f"feedback:rating:{i}") for i in range(1, 6)]
        kb.add(*stars)
        kb.add(self.btn("لغو", "back"))
        return kb

    async def select_account_for_purchase_menu(self, user_uuids: list, plan_id: int, lang_code: str) -> types.InlineKeyboardMarkup:
        """انتخاب اکانت برای اعمال پلن خریداری شده"""
        kb = self.create_markup(row_width=1)
        for u in user_uuids:
            text = f"👤 {u.get('name', get_string('unknown_user', lang_code))}"
            kb.add(self.btn(text, f"wallet:buy_for_account:{u['id']}:{plan_id}"))
        
        kb.add(self.back_btn("view_plans", lang_code))
        return kb

    async def post_charge_menu(self, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        """منوی نمایش داده شده پس از شارژ موفق"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🛒 مشاهده سرویس‌ها", "view_plans"),
            self.btn("🔙 بازگشت به کیف پول", "wallet:main")
        )
        return kb
    
    async def user_cancel_action(self, back_callback: str, lang_code: str = 'fa') -> types.InlineKeyboardMarkup:
        """دکمه عمومی لغو عملیات"""
        kb = self.create_markup()
        cancel_text = get_string('btn_cancel_action', lang_code)
        kb.add(self.btn(f"✖️ {cancel_text}", back_callback))
        return kb