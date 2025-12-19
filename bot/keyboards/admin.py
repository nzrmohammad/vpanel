# bot/keyboards/admin.py

from telebot import types
from typing import Optional, List, Dict, Any
from .base import BaseMenu
from bot.database import db

class AdminMenu(BaseMenu):
    """
    کلاس مدیریت کیبوردهای پنل ادمین.
    تمام منوها به صورت Async و داینامیک طراحی شده‌اند.
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
            [("⚙️ تنظیمات پنل‌ها", "admin:panel_manage"), ("🛠️ ابزارهای سیستمی", "admin:system_tools_menu")],
            [("🔗 مدیریت اتصال مرزبان", "admin:mapping_menu")],
            [("🔙 بازگشت به منوی اصلی", "back")]
        ]
        for row in layout:
            kb.row(*[self.btn(t, cb) for t, cb in row])
        return kb

    # ---------------------------------------------------------
    # بخش مدیریت کاربران (User Management)
    # ---------------------------------------------------------
    
    async def management_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """
        منوی انتخاب پنل برای مدیریت کاربران.
        """
        kb = self.create_markup(row_width=2)
        categories = await db.get_server_categories()
        cat_map = {c['code']: c['emoji'] for c in categories}
        
        kb.add(self.btn("➕ افزودن کاربر جدید (سراسری)", "admin:add_user:all"))

        if not panels:
            kb.add(self.btn("⚠️ هیچ پنلی یافت نشد (افزودن پنل)", "admin:panel_add_start"))
        else:
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

    # ---------------------------------------------------------
    # بخش گزارش‌ها (Reports)
    # ---------------------------------------------------------

    async def reports_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی گزارش‌ها با لیست داینامیک سرورها"""
        kb = self.create_markup(row_width=2)
        
        # دکمه‌های گزارش اختصاصی برای هر پنل
        panel_buttons = []
        for p in panels:
            btn_text = f"{p['name']} ({p['panel_type']})" # فرمت درخواستی شما
            panel_buttons.append(self.btn(btn_text, f"admin:panel_report_detail:{p['id']}"))

        if panel_buttons:
            kb.add(*panel_buttons)

        # گزارش‌های عمومی
        kb.add(
            self.btn("💳 تراکنش‌های مالی", "admin:list:payments:0"),
            self.btn("🤖 کاربران ربات", "admin:list:bot_users:0")
        )
        kb.add(
            self.btn("💰 موجودی کیف‌پول‌ها", "admin:list:balances:0"), 
            self.btn("🏆 لیدربرد امتیازات", "admin:list:leaderboard:0")
        )
        kb.add(
            self.btn("📊 گزارش بر اساس پلن", "admin:user_analysis_menu"),
            self.btn("💸 گزارش سود و زیان", "admin:financial_report")
        )
        
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_specific_reports_menu(self, panel_id: int, panel_name: str) -> types.InlineKeyboardMarkup:
        """منوی گزارش‌های ریز برای یک پنل"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ کاربران فعال (۲۴س)", f"admin:list:active_users:{panel_id}:0"),
            self.btn("📡 کاربران آنلاین", f"admin:list:online_users:{panel_id}:0")
        )
        kb.add(
            self.btn("⏳ غیرفعال‌ها", f"admin:list:inactive_users:{panel_id}:0"),
            self.btn("🚫 هرگز متصل نشده", f"admin:list:never_connected:{panel_id}:0")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb

    # ---------------------------------------------------------
    # بخش مدیریت پلن‌ها (Plans)
    # ---------------------------------------------------------

    async def plan_management_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """
        منوی مدیریت پلن‌ها.
        لیست پلن‌های موجود را نمایش می‌دهد + دکمه افزودن.
        """
        kb = self.create_markup(row_width=2)
        
        # لیست پلن‌های موجود
        for plan in plans:
            # نمایش نام و قیمت
            btn_text = f"{plan['name']} ({int(plan['price']):,} T)"
            kb.add(self.btn(btn_text, f"admin:plan_details:{plan['id']}"))

        kb.add(self.btn("🌍 مدیریت کشورها", "admin:cat_manage"))
        kb.add(self.btn("➕ افزودن پلن جدید", "admin:plan_add_start"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    # ---------------------------------------------------------
    # بخش مدیریت پنل‌ها / سرورها (Servers)
    # ---------------------------------------------------------

    async def panel_list_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """لیست پنل‌های متصل برای ویرایش/حذف (دو ستونه + پرچم)"""
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
            
        if panel_buttons:
            kb.add(*panel_buttons)
            
        kb.row(
            self.btn("🌍 مدیریت کشورها", "admin:cat_manage"),
            self.btn("➕ افزودن پنل", "admin:panel_add_start")
        )
        
        kb.row(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_category_selection_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی انتخاب کشور برای پنل (دو ستونه)"""
        kb = self.create_markup(row_width=2) 
        
        for cat in categories:
            button_text = f"{cat['emoji']} {cat['name']}"
            kb.add(self.btn(button_text, f"admin:panel_set_cat:{cat['code']}"))
        
        kb.row(self.btn("🔙 انصراف", "admin:panel_manage"))
        return kb

    # ---------------------------------------------------------
    # سایر منوها (جستجو، ابزارها، بکاپ و ...)
    # ---------------------------------------------------------

    async def search_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("🔎 نام / یوزرنیم / UUID", "admin:sg"),
            self.btn("🆔 آیدی عددی تلگرام", "admin:search_by_tid")
        )
        kb.add(self.btn("🔥 پاکسازی کاربر (Purge)", "admin:purge_user"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def group_actions_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(
            self.btn("⚙️ دستور گروهی (بر اساس پلن)", "admin:group_action_select_plan"),
            self.btn("🔥 دستور گروهی (پیشرفته)", "admin:adv_ga_select_filter")
        )
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def system_tools_menu(self) -> types.InlineKeyboardMarkup:
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

    async def user_interactive_menu(self, identifier: str, is_active: bool, panel_type: str, back_callback: str = None) -> types.InlineKeyboardMarkup:
        """منوی مدیریت تکی کاربر با حفظ کانتکست (سرچ/مدیریت)"""
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
        kb.add(
            self.btn("🔄 تمدید اشتراک", f"admin:renew_sub_menu:{base}"),
            self.btn("🗑 حذف کامل", f"admin:us_delc:{base}")
        )
        
        final_back = back_callback or "admin:management_menu"
        kb.add(self.btn("🔙 بازگشت", final_back))
        return kb

    async def broadcast_target_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📡 آنلاین (۲۴س)", "admin:broadcast_target:online"),
            self.btn("✅ فعال (دارای سرویس)", "admin:broadcast_target:active_1")
        )
        kb.add(
            self.btn("⏳ غیرفعال (۷ روز)", "admin:broadcast_target:inactive_7"),
            self.btn("🚫 هرگز متصل نشده", "admin:broadcast_target:inactive_0")
        )
        kb.add(self.btn("👥 همه کاربران", "admin:broadcast_target:all"))
        kb.add(self.btn("🔙 لغو", "admin:panel"))
        return kb

    async def confirm_broadcast_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، ارسال شود", "admin:broadcast_confirm"),
            self.btn("❌ خیر، لغو", "admin:panel")
        )
        return kb

    async def backup_selection_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("📄 Hiddify Users", "admin:backup:hiddify"),
            self.btn("📄 Marzban Users", "admin:backup:marzban")
        )
        kb.add(self.btn("🗄️ دیتابیس ربات (SQL)", "admin:backup:bot_db"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def system_status_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی انتخاب سرور برای چک کردن وضعیت سیستم"""
        kb = self.create_markup(row_width=2)
        for p in panels:
            kb.add(self.btn(f"وضعیت {p['name']}", f"admin:health_check:{p['id']}"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    # --- متدهای کمکی و متفرقه ---

    async def select_plan_for_report_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        
        kb.row(self.btn("👤 کاربران بدون پلن", "admin:list_by_plan:0:0"))
        
        # ساخت لیست دکمه‌های پلن‌ها
        plan_btns = []
        for plan in plans:
            plan_btns.append(self.btn(f"📦 {plan['name']}", f"admin:list_by_plan:{plan['id']}:0"))
        
        # اضافه کردن دکمه‌ها به صورت دو تایی در هر ردیف
        kb.add(*plan_btns)
        
        kb.row(self.btn("🔙 بازگشت", "admin:reports_menu"))
        return kb

    async def select_plan_for_action_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        for plan in plans:
            kb.add(self.btn(plan['name'], f"admin:ga_select_type:{plan['id']}"))
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def select_action_type_menu(self, context_value: any, context_type: str) -> types.InlineKeyboardMarkup:
        return await self._create_resource_action_menu(
            base_callback="admin:ga_ask_value",
            args=[context_type, context_value],
            back_callback="admin:group_actions_menu"
        )

    async def confirm_group_action_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(self.btn("✅ بله، انجام شود", "admin:ga_confirm"), self.btn("❌ لغو", "admin:group_actions_menu"))
        return kb

    async def award_badge_menu(self, identifier: str, context_suffix: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        badges = [
            ('🏊‍♂️ شنا', 'water_athlete'), ('🏋️‍♂️ بدن‌سازی', 'bodybuilder'),
            ('💎 حامی ویژه', 'vip_friend'), ('🌟 اسطوره', 'legend')
        ]
        for name, code in badges:
            kb.add(self.btn(name, f"admin:awd_b:{code}:{identifier}{context_suffix}"))
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def advanced_group_action_filter_menu(self) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=1)
        kb.add(self.btn("⏳ در آستانه انقضا (۳ روز)", "admin:adv_ga_select_action:expiring_soon"))
        kb.add(self.btn("🚫 غیرفعال (۳۰ روز)", "admin:adv_ga_select_action:inactive_30_days"))
        kb.add(self.btn("🔙 بازگشت", "admin:group_actions_menu"))
        return kb

    async def server_selection_menu(self, base_callback: str, panels: List[Dict[str, Any]] = None) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        if panels:
            for p in panels:
                kb.add(self.btn(p['name'], f"{base_callback}:{p['id']}"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
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

    async def cancel_action(self, back_callback="admin:panel") -> types.InlineKeyboardMarkup:
        kb = self.create_markup()
        kb.add(self.btn("✖️ لغو عملیات", back_callback))
        return kb

    async def confirm_delete(self, identifier: str, panel: str) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("❌ بله، حذف کن", f"admin:del_a:confirm:{panel}:{identifier}"),
            self.btn("✅ نه، لغو کن", f"admin:del_a:cancel:{panel}:{identifier}")
        )
        return kb
    
    async def confirm_delete_mapping_menu(self, uuid_str: str, page: int) -> types.InlineKeyboardMarkup:
        """منوی تایید حذف اتصال مرزبان"""
        kb = self.create_markup(row_width=2)
        kb.add(
            self.btn("✅ بله، حذف کن", f"admin:del_map_exec:{uuid_str}:{page}"),
            self.btn("❌ انصراف", f"admin:mapping_list:{page}") # برگشت به لیست، نه پنل اصلی
        )
        return kb


    async def mapping_main_menu(self) -> types.InlineKeyboardMarkup:
        """منوی اصلی انتخاب عملیات مپینگ (دکمه‌ها کنار هم)"""
        kb = self.create_markup(row_width=2)
        
        kb.add(
            self.btn("➕ ایجاد اتصال جدید", "admin:add_mapping"),
            self.btn("📋 لیست اتصالات موجود", "admin:mapping_list:0")
        )
        
        # دکمه بازگشت در ردیف جداگانه
        kb.add(self.btn("🔙 بازگشت به پنل", "admin:panel"))
        return kb

    async def mapping_list_menu(self, mappings: list, page: int, total_count: int, page_size: int) -> types.InlineKeyboardMarkup:
        """منوی لیست اتصالات (با دکمه ایجاد در بالا)"""
        kb = self.create_markup(row_width=2)  
        
        if not mappings:
            kb.add(self.btn("➕ ایجاد اتصال جدید", "admin:add_mapping"))
        
        map_buttons = []
        for m in mappings:
            uuid_short = str(m['hiddify_uuid'])[:5]
            btn_text = f"🗑 {m['marzban_username']} ({uuid_short})"
            map_buttons.append(self.btn(btn_text, f"admin:del_map_conf:{m['hiddify_uuid']}:{page}"))
        
        # افزودن دکمه‌ها
        kb.add(*map_buttons)
            
        nav_buttons = []
        if page > 0:
            nav_buttons.append(self.btn("⬅️ قبلی", f"admin:mapping_list:{page - 1}"))
        
        if (page + 1) * page_size < total_count:
            nav_buttons.append(self.btn("بعدی ➡️", f"admin:mapping_list:{page + 1}"))
            
        if nav_buttons:
            kb.row(*nav_buttons)
            
        # بازگشت به منوی مپینگ (نه پنل اصلی)
        kb.add(self.btn("🔙 بازگشت", "admin:mapping_menu"))
        return kb

    # ---------------------------------------------------------
    # متدهای جدید برای بخش ویرایش کاربر
    # ---------------------------------------------------------
    async def edit_user_panel_select_menu(self, identifier: str, panels: list) -> types.InlineKeyboardMarkup:
        """
        منوی انتخاب پنل برای ویرایش کاربر.
        """
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
        
        if all_panel_btn:
            kb.row(all_panel_btn)
            
        if other_buttons:
            kb.add(*other_buttons)
        
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def edit_user_action_menu(self, identifier: str, panel_target: str) -> types.InlineKeyboardMarkup:
        return await self._create_resource_action_menu(
            base_callback="admin:ae",
            args=[panel_target, identifier],
            back_callback=f"admin:us_edt:{identifier}"
        )

    async def _create_resource_action_menu(self, base_callback: str, args: list, back_callback: str) -> types.InlineKeyboardMarkup:
        """
        یک تابع عمومی برای ساخت منوی افزودن حجم و روز.
        base_callback: مثل 'admin:ae' یا 'admin:ga_ask_value'
        args: لیست پارامترهایی که باید به کالبک چسبانده شوند (مثل [panel_name, uuid])
        back_callback: کالبک دکمه بازگشت
        """
        kb = self.create_markup(row_width=2)
        
        # آرگومان‌ها را با : به هم وصل می‌کنیم
        suffix = ":".join(map(str, args))
        
        kb.add(
            self.btn("➕ افزودن حجم", f"{base_callback}:add_gb:{suffix}"),
            self.btn("➕ افزودن روز", f"{base_callback}:add_days:{suffix}")
        )
        
        kb.add(self.btn("🔙 بازگشت", back_callback))
        return kb