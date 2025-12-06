# bot/keyboards/admin.py

from telebot import types
from typing import Optional, List, Dict, Any
from .base import BaseMenu

class AdminMenu(BaseMenu):
    """
    کلاس مدیریت کیبوردهای پنل ادمین.
    شامل تمام منوها و دکمه‌های مورد نیاز برای مدیریت ربات.
    """

    async def main(self) -> types.InlineKeyboardMarkup:
        """منوی اصلی مدیریت"""
        kb = self.create_markup(row_width=2)
        layout = [
            [("📊 داشبورد سریع", "admin:quick_dashboard")],
            [("🔎 جستجوی کاربر", "admin:search_menu"), ("👥 مدیریت کاربران", "admin:management_menu")],
            [("📊 گزارش‌ها و آمار", "admin:reports_menu"), ("⚙️ دستورات گروهی", "admin:group_actions_menu")],
            [("💾 پشتیبان‌گیری", "admin:backup_menu"), ("📣 پیام همگانی", "admin:broadcast")],
            [("⏰ کارهای زمان‌بندی", "admin:scheduled_tasks"), ("🗂️ مدیریت پلن‌ها", "admin:plan_manage")],
            [("⚙️ مدیریت پنل‌ها", "admin:panel_manage"), ("🛠️ ابزارهای سیستمی", "admin:system_tools_menu")],
            [("🔙 بازگشت به منوی اصلی", "back")]
        ]
        for row in layout:
            kb.row(*[self.btn(t, cb) for t, cb in row])
        return kb

    async def system_tools_menu(self) -> types.InlineKeyboardMarkup:
        """منوی ابزارهای سیستمی"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔄 آپدیت آمار (Snapshot)", "admin:force_snapshot"),
            self.btn("🔄 ریست مصرف امروز همه", "admin:reset_all_daily_usage_confirm")
        )
        kb.add(
            self.btn("🏆 ریست امتیازات", "admin:reset_all_points_confirm"),
            self.btn("🗑️ حذف تمام دستگاه‌ها", "admin:delete_all_devices_confirm")
        )
        kb.add(self.btn("💸 ریست موجودی همه", "admin:reset_all_balances_confirm"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def search_menu(self) -> types.InlineKeyboardMarkup:
        """منوی جستجو"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔎 نام کاربر", "admin:sg"),
            self.btn("🆔 آیدی تلگرام", "admin:search_by_tid")
        )
        kb.add(self.btn("🔥 پاکسازی کاربر با آیدی", "admin:purge_user"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def group_actions_menu(self) -> types.InlineKeyboardMarkup:
        """منوی دستورات گروهی"""
        kb = self.create_markup(row_width=1)
        kb.add(
            self.btn("⚙️ دستور گروهی (بر اساس پلن)", "admin:group_action_select_plan"),
            self.btn("🔥 دستور گروهی (پیشرفته)", "admin:adv_ga_select_filter")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def management_menu(self) -> types.InlineKeyboardMarkup:
        """منوی انتخاب نوع پنل برای مدیریت کاربران"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("مدیریت پنل‌های Hiddify", "admin:manage_panel:hiddify"),
            self.btn("مدیریت پنل‌های Marzban", "admin:manage_panel:marzban")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_management_menu(self, panel_type: str) -> types.InlineKeyboardMarkup:
        """منوی مدیریت یک پنل خاص (افزودن کاربر/لیست)"""
        kb = self.create_markup(row_width=1)
        kb.add(
            self.btn("➕ افزودن کاربر جدید", f"admin:add_user:{panel_type}"),
            self.btn("📋 لیست کاربران پنل", f"admin:list:panel_users:{panel_type}:0")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:management_menu"))
        return kb

    async def user_interactive_menu(self, identifier: str, is_active: bool, panel: str, back_callback: str = None) -> types.InlineKeyboardMarkup:
        """منوی مدیریت تکی کاربر (عملیات مختلف)"""
        kb = self.create_markup(row_width=2)
        
        context_suffix = ":s" if back_callback and "search_menu" in back_callback else ""
        panel_short = 'h' if panel == 'hiddify' else 'm'
        base = f"{identifier}{context_suffix}"

        # ردیف ۱
        kb.add(
            self.btn("⚙️ تغییر وضعیت", f"admin:us_tgl:{base}"),
            self.btn("📝 یادداشت ادمین", f"admin:us_note:{base}:{panel_short}")
        )
        # ردیف ۲
        kb.add(
            self.btn("💳 ثبت پرداخت", f"admin:us_lpay:{base}"),
            self.btn("📜 سابقه پرداخت", f"admin:us_phist:{identifier}:0{context_suffix}")
        )
        # ردیف ۳
        kb.add(
            self.btn("💰 شارژ کیف پول", f"admin:us_mchg:{base}:{panel_short}"),
            self.btn("💸 برداشت وجه", f"admin:us_wdrw:{base}")
        )
        # ردیف ۴
        kb.add(
            self.btn("🔧 ویرایش کاربر", f"admin:us_edt:{base}"),
            self.btn("📱 حذف دستگاه‌ها", f"admin:us_ddev:{base}")
        )
        # ردیف ۵
        kb.add(
            self.btn("♻️ تنظیمات ریست", f"admin:us_reset_menu:{base}:{panel_short}"),
            self.btn("⚠️ ارسال هشدار", f"admin:us_warn_menu:{base}:{panel_short}")
        )
        # ردیف ۶
        kb.add(
            self.btn("🔄 تمدید اشتراک", f"admin:renew_sub_menu:{base}"),
            self.btn("🗑 حذف کامل", f"admin:us_delc:{base}")
        )
        # ردیف ۷
        kb.add(self.btn("🥺 پیام دلتنگی", f"admin:us_winback:{base}:{panel_short}"))
        
        final_back = back_callback or f"admin:manage_panel:{panel}"
        kb.add(self.btn("🔙 بازگشت", final_back))
        return kb

    async def renew_subscription_menu(self, identifier: str, context_suffix: str) -> types.InlineKeyboardMarkup:
        """منوی تمدید اشتراک"""
        kb = self.create_markup(row_width=1)
        # برای بازگشت نیاز به پنل داریم، فرض بر hiddify یا استفاده از context_suffix برای اصلاح مسیر
        # در اینجا ساده‌سازی شده، بهتر است پنل هم پاس داده شود. اما طبق کد قبلی:
        panel_short = 'h' # Fallback default
        
        kb.add(self.btn("🔄 اعمال پلن جدید", f"admin:renew_select_plan:{identifier}{context_suffix}"))
        kb.add(self.btn("🔙 بازگشت به کاربر", f"admin:us:{panel_short}:{identifier}{context_suffix}"))
        return kb

    async def select_plan_for_renew_menu(self, identifier: str, context_suffix: str, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """انتخاب پلن برای تمدید"""
        kb = self.create_markup(row_width=1)
        
        for plan in plans:
            name = plan['name']
            plan_id = plan['id']
            kb.add(self.btn(name, f"admin:renew_apply_plan:{plan_id}:{identifier}{context_suffix}"))
        
        kb.add(self.btn("🔙 بازگشت", f"admin:renew_sub_menu:{identifier}{context_suffix}"))
        return kb

    async def edit_user_menu(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        """منوی ویرایش کاربر (حجم/زمان)"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("➕ افزودن حجم", f"admin:ae:add_gb:{panel}:{identifier}"),
            self.btn("➕ افزودن روز", f"admin:ae:add_days:{panel}:{identifier}")
        )
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{panel}:{identifier}"))
        return kb

    async def reset_usage_selection_menu(self, identifier: str, base_callback: str, context: Optional[str] = None) -> types.InlineKeyboardMarkup:
        """منوی انتخاب پنل برای ریست حجم"""
        kb = self.create_markup(row_width=2)
        suffix = f":{context}" if context else ""
        panel_short = 'h' # Default fallback
        
        kb.add(
            self.btn("آلمان 🇩🇪", f"admin:{base_callback}:hiddify:{identifier}{suffix}"),
            self.btn("فرانسه 🇫🇷", f"admin:{base_callback}:marzban:{identifier}{suffix}")
        )
        kb.add(self.btn("هر دو پنل", f"admin:{base_callback}:both:{identifier}{suffix}"))
        kb.add(self.btn("🔙 لغو", f"admin:us:{panel_short}:{identifier}{suffix}"))
        return kb

    async def reports_menu(self) -> types.InlineKeyboardMarkup:
        """منوی گزارش‌ها"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("گزارش پنل‌های Hiddify", "admin:panel_reports:hiddify"),
            self.btn("گزارش پنل‌های Marzban", "admin:panel_reports:marzban")
        )
        kb.add(
            self.btn("💳 پرداخت‌ها", "admin:list:payments:0"),
            self.btn("🤖 کاربران ربات", "admin:list:bot_users:0")
        )
        kb.add(
            self.btn("💰 موجودی‌ها", "admin:list:balances:0"), 
            self.btn("🎂 تولدها", "admin:list:birthdays:0")
        )
        kb.add(
            self.btn("🏆 لیدربرد امتیاز", "admin:list:leaderboard:0"),
            self.btn("📊 گزارش پلن", "admin:user_analysis_menu")
        )
        kb.add(
            self.btn("📱 دستگاه‌ها", "admin:list:devices:0"),
            self.btn("💸 گزارش مالی", "admin:financial_report")
        )
        kb.add(self.btn("📊 بازخوردها", "admin:list:feedback:0"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_specific_reports_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        """گزارش‌های خاص یک پنل"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ فعال (۲۴س)", f"admin:list:active_users:{panel}:0"),
            self.btn("📡 آنلاین", f"admin:list:online_users:{panel}:0")
        )
        kb.add(
            self.btn("🚫 هرگز متصل نشده", f"admin:list:never_connected:{panel}:0"),
            self.btn("⏳ غیرفعال (هفتگی)", f"admin:list:inactive_users:{panel}:0")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb

    async def analytics_menu(self, panel: str) -> types.InlineKeyboardMarkup:
        """منوی تحلیل و آمار"""
        kb = self.create_markup(row_width=2)
        kb.add(self.btn("🏆 پرمصرف‌ترین‌ها", f"admin:list:top_consumers:{panel}:0"))
        
        if panel == 'hiddify':
            kb.add(self.btn("🌡️ سلامت پنل", "admin:health_check"))
        elif panel == 'marzban':
            kb.add(self.btn("🖥️ وضعیت سیستم", "admin:marzban_stats"))

        kb.add(
            self.btn("🔙 تغییر پنل", "admin:select_server:analytics_menu"),
            self.btn("↩️ منوی مدیریت", "admin:panel")
        )
        return kb

    async def select_plan_for_report_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """انتخاب پلن برای گزارش‌گیری"""
        kb = self.create_markup(row_width=1)
        for plan in plans:
            name = plan['name']
            plan_id = plan['id']
            kb.add(self.btn(name, f"admin:list_by_plan:{plan_id}:0"))
            
        kb.add(self.btn("📝 کاربران بدون پلن", "admin:list_no_plan:0"))
        kb.add(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb

    async def select_plan_for_action_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """انتخاب پلن برای دستور گروهی"""
        kb = self.create_markup(row_width=1)
        for plan in plans:
            name = plan['name']
            plan_id = plan['id']
            kb.add(self.btn(name, f"admin:ga_select_type:{plan_id}"))
            
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def select_action_type_menu(self, context_value: any, context_type: str) -> types.InlineKeyboardMarkup:
        """انتخاب نوع دستور گروهی (حجم/زمان)"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("➕ افزودن حجم", f"admin:ga_ask_value:add_gb:{context_type}:{context_value}"),
            self.btn("➕ افزودن روز", f"admin:ga_ask_value:add_days:{context_type}:{context_value}")
        )
        back_cb = "admin:group_action_select_plan" if context_type == 'plan' else "admin:adv_ga_select_filter"
        kb.add(self.btn("🔙 بازگشت", back_cb))
        return kb

    async def advanced_group_action_filter_menu(self) -> types.InlineKeyboardMarkup:
        """فیلترهای پیشرفته برای دستور گروهی"""
        kb = self.create_markup(row_width=1)
        kb.add(self.btn("⏳ در آستانه انقضا (۳ روز)", "admin:adv_ga_select_action:expiring_soon"))
        kb.add(self.btn("🚫 غیرفعال (۳۰ روز)", "admin:adv_ga_select_action:inactive_30_days"))
        kb.add(self.btn("🔙 بازگشت", "admin:management_menu"))
        return kb

    async def broadcast_target_menu(self) -> types.InlineKeyboardMarkup:
        """انتخاب مخاطبین پیام همگانی"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📡 آنلاین", "admin:broadcast_target:online"),
            self.btn("✅ فعال اخیر", "admin:broadcast_target:active_1")
        )
        kb.add(
            self.btn("⏳ غیرفعال اخیر", "admin:broadcast_target:inactive_7"),
            self.btn("🚫 هرگز متصل نشده", "admin:broadcast_target:inactive_0")
        )
        kb.add(self.btn("👥 همه کاربران", "admin:broadcast_target:all"))
        kb.add(self.btn("🔙 لغو", "admin:panel"))
        return kb

    async def confirm_broadcast_menu(self) -> types.InlineKeyboardMarkup:
        """تایید ارسال پیام همگانی"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، ارسال شود", "admin:broadcast_confirm"),
            self.btn("❌ خیر، لغو", "admin:panel")
        )
        return kb

    async def backup_selection_menu(self) -> types.InlineKeyboardMarkup:
        """منوی بکاپ‌گیری"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📄 Hiddify", "admin:backup:hiddify"),
            self.btn("📄 Marzban", "admin:backup:marzban")
        )
        kb.add(self.btn("🗄️ دیتابیس ربات", "admin:backup:bot_db"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def server_selection_menu(self, base_callback: str) -> types.InlineKeyboardMarkup:
        """انتخاب سرور عمومی"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("آلمان 🇩🇪", f"{base_callback}:hiddify"),
            self.btn("فرانسه 🇫🇷", f"{base_callback}:marzban")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def cancel_action(self, back_callback="admin:panel") -> types.InlineKeyboardMarkup:
        """دکمه لغو عمومی"""
        kb = self.create_markup()
        kb.add(self.btn("✖️ لغو عملیات", back_callback))
        return kb
        
    async def confirm_delete(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        """تایید حذف کاربر"""
        panel_short = 'h' if panel == 'hiddify' else 'm'
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("❌ بله، حذف کن", f"admin:del_a:confirm:{panel_short}:{identifier}"),
            self.btn("✅ نه، لغو کن", f"admin:del_a:cancel:{panel_short}:{identifier}")
        )
        return kb
    
    async def system_status_menu(self) -> types.InlineKeyboardMarkup:
        """منوی وضعیت سیستم"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("آلمان 🇩🇪", "admin:health_check"),
            self.btn("فرانسه 🇫🇷", "admin:marzban_stats")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb
    
    async def award_badge_menu(self, identifier: str, context_suffix: str, badges: List[Dict[str, Any]] = None) -> types.InlineKeyboardMarkup:
        """
        منوی اهدای دستی نشان.
        """
        kb = self.create_markup(row_width=2)
        
        # لیست پیش‌فرض برای اطمینان
        if not badges:
            badges = [
                {'code': 's_coach', 'name': "🏊‍♀️ مربی شنا"}, 
                {'code': 'b_coach', 'name': "🏋️‍♂️ مربی بدن‌سازی"},
                {'code': 'vip_friend', 'name': "💎 حامی ویژه"}
            ]

        buttons = [self.btn(b['name'], f"admin:awd_b:{b['code']}:{identifier}{context_suffix}") for b in badges]
        
        for i in range(0, len(buttons), 2):
            if i+1 < len(buttons):
                kb.row(buttons[i], buttons[i+1])
            else:
                kb.row(buttons[i])

        panel_short = 'h' # Fallback
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{panel_short}:{identifier}{context_suffix}"))
        return kb
    
    async def confirm_group_action_menu(self) -> types.InlineKeyboardMarkup:
        """تایید دستور گروهی"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، انجام شود", "admin:ga_confirm"),
            self.btn("❌ لغو", "admin:group_actions_menu")
        )
        return kb