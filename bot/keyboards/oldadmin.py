# bot/keyboards/admin.py

from telebot import types
from typing import Optional, List, Dict, Any
from .base import BaseMenu
from bot.database import db

class AdminMenu(BaseMenu):
    """
    کلاس مدیریت کیبوردهای پنل ادمین.
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
            [("⚙️ تنظیمات سیستم", "admin:settings:main"), ("🔗 مدیریت اتصال مرزبان", "admin:mapping_menu")],
            [("🔙 بازگشت به منوی اصلی", "back")]
        ]
        
        for row in layout:
            btns = []
            for item in row:
                if isinstance(item, tuple) and len(item) >= 2:
                    btns.append(self.btn(item[0], item[1]))
            if btns:
                kb.row(*btns)
                
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
            btn_text = f"{p['name']} ({p['panel_type']})"
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

    async def plan_management_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """
        منوی اصلی مدیریت پلن‌ها (نمایش لیست کشورها + دکمه‌های مدیریتی)
        """
        kb = self.create_markup(row_width=2)
        
        # 1. ساخت دکمه‌های کشورها (دسته‌بندی‌ها)
        cat_buttons = []
        for cat in categories:
            # نمایش پرچم و نام کشور
            btn_text = f"{cat['emoji']} {cat['name']}"
            callback = f"admin:plan_show_category:{cat['code']}"
            cat_buttons.append(self.btn(btn_text, callback))
        
        # افزودن دکمه‌های کشورها به کیبورد
        if cat_buttons:
            kb.add(*cat_buttons)
        
        # 3. دکمه جدید برای فروشگاه امتیاز
        kb.add(types.InlineKeyboardButton("🏪 مدیریت فروشگاه امتیاز", callback_data="admin:shop:main"))
        
        # 4. دکمه بازگشت
        kb.add(self.btn("🔙 بازگشت به پنل", "admin:panel"))
        
        return kb

    async def plan_type_selection_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی انتخاب نوع پلن (ترکیبی یا اختصاصی کشورها) برای افزودن پلن جدید"""
        kb = self.create_markup(row_width=2)
        
        # دکمه پلن ترکیبی (همه کشورها)
        kb.add(self.btn("🚀 ترکیبی (همه سرورها)", "admin:plan_add_type:combined"))
        
        # دکمه برای هر کشور موجود
        cat_btns = []
        for cat in categories:
            # ارسال کد کشور (مثلا de) به عنوان پارامتر
            cat_btns.append(self.btn(f"{cat['emoji']} {cat['name']}", f"admin:plan_add_type:{cat['code']}"))
            
        if cat_btns:
            kb.add(*cat_btns)
            
        kb.add(self.btn("🔙 بازگشت", "admin:plan_manage"))
        return kb

    # ---------------------------------------------------------
    # بخش مدیریت پنل‌ها / سرورها (Servers)
    # ---------------------------------------------------------

    async def panel_list_menu(self, panels: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """لیست پنل‌های متصل برای ویرایش/حذف"""
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
            self.btn("🌍 دسته بندی کشورها", "admin:cat_manage"),
            self.btn("➕ افزودن پنل", "admin:panel_add_start")
        )
        
        kb.row(self.btn("🔙 بازگشت", "admin:panel"))
        return kb

    async def panel_category_selection_menu(self, categories: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        """منوی انتخاب کشور برای پنل"""
        kb = self.create_markup(row_width=2) 
        
        buttons = []
        for cat in categories:
            button_text = f"{cat['emoji']} {cat['name']}"
            buttons.append(self.btn(button_text, f"admin:panel_set_cat:{cat['code']}"))
        
        if buttons:
            kb.add(*buttons)
        
        kb.row(self.btn("🔙 انصراف", "admin:panel_manage"))
        return kb

    # ---------------------------------------------------------
    # سایر منوها
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


    async def backup_selection_menu(self, panel_types: list, current_filter: str = 'all') -> types.InlineKeyboardMarkup:
        """منوی انتخاب بکاپ (راست‌چین + MarkdownV2 Compatible)"""
        kb = self.create_markup(row_width=2)
        
        # --- 1. بخش فیلترها (چیدمان معکوس برای نمایش صحیح در تلگرام) ---
        # نمایش در تلگرام: [❌ غیرفعال] [✅ فعال] [👥 همه]
        filters = [
            ("❌ غیرفعال", "inactive"),
            ("✅ فعال", "active"),
            ("👥 همه", "all")
        ]
        
        filter_btns = []
        for label, code in filters:
            if code == current_filter:
                display = f"🔘 {label}"
                cb = "noop" 
            else:
                display = label
                cb = f"admin:backup_filter:{code}" 
            
            filter_btns.append(self.btn(display, cb))
        
        # افزودن دکمه‌های فیلتر در یک ردیف
        kb.row(*filter_btns)
        
        # --- 2. بخش دکمه‌های پنل ---
        panel_buttons = []
        for p_type in panel_types:
            display_name = p_type.capitalize()
            # فرمت: admin:backup:{panel_type}:{filter}
            panel_buttons.append(self.btn(f"📥 {display_name} (API)", f"admin:backup:{p_type}:{current_filter}"))
            
        if panel_buttons:
            kb.add(*panel_buttons)
            
        # دکمه‌های ثابت
        kb.add(self.btn("🗄️ دیتابیس ربات (SQL + JSON)", "admin:backup:bot_db"))
        kb.add(self.btn("🔙 بازگشت", "admin:panel"))
        
        return kb

    # --- متدهای کمکی و متفرقه ---

    async def select_plan_for_report_menu(self, plans: List[Dict[str, Any]]) -> types.InlineKeyboardMarkup:
        kb = self.create_markup(row_width=2)
        kb.row(self.btn("👤 کاربران بدون پلن", "admin:list_by_plan:0:0"))
        
        plan_btns = []
        for plan in plans:
            plan_btns.append(self.btn(f"📦 {plan['name']}", f"admin:list_by_plan:{plan['id']}:0"))
        
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
            self.btn("❌ انصراف", f"admin:mapping_list:{page}") 
        )
        return kb


    async def mapping_main_menu(self) -> types.InlineKeyboardMarkup:
        """منوی اصلی انتخاب عملیات مپینگ"""
        kb = self.create_markup(row_width=2)
        
        kb.add(
            self.btn("📋 لیست اتصالات موجود", "admin:mapping_list:0"),
            self.btn("➕ ایجاد اتصال جدید", "admin:add_mapping")
            
        )
        
        kb.add(self.btn("🔙 بازگشت به پنل", "admin:panel"))
        return kb

    async def mapping_list_menu(self, mappings: list, page: int, total_count: int, page_size: int) -> types.InlineKeyboardMarkup:
        """منوی لیست اتصالات"""
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
        if page > 0:
            nav_buttons.append(self.btn("⬅️ قبلی", f"admin:mapping_list:{page - 1}"))
        
        if (page + 1) * page_size < total_count:
            nav_buttons.append(self.btn("بعدی ➡️", f"admin:mapping_list:{page + 1}"))
            
        if nav_buttons:
            kb.row(*nav_buttons)
            
        kb.add(self.btn("🔙 بازگشت", "admin:mapping_menu"))
        return kb

    async def edit_user_panel_select_menu(self, identifier: str, panels: list) -> types.InlineKeyboardMarkup:
        """منوی انتخاب پنل برای ویرایش کاربر"""
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
        """یک تابع عمومی برای ساخت منوی افزودن حجم و روز"""
        kb = self.create_markup(row_width=2)
        suffix = ":".join(map(str, args))
        
        kb.add(
            self.btn("➕ افزودن حجم", f"{base_callback}:add_gb:{suffix}"),
            self.btn("➕ افزودن روز", f"{base_callback}:add_days:{suffix}")
        )
        
        kb.add(self.btn("🔙 بازگشت", back_callback))
        return kb
    
    async def user_country_access_menu(self, identifier: str, all_categories: list, user_allowed: list) -> types.InlineKeyboardMarkup:
        """منوی تیک زدن کشورهای مجاز برای کاربر"""
        kb = self.create_markup(row_width=2)
        
        buttons = []
        for cat in all_categories:
            code = cat['code']
            name = cat['name']
            emoji = cat['emoji']
            
            is_allowed = code in user_allowed
            status_icon = "✅" if is_allowed else "❌"
            
            btn_text = f"{status_icon} {emoji} {name}"
            callback = f"admin:us_access_toggle:{identifier}:{code}"
            
            buttons.append(self.btn(btn_text, callback))
            
        if buttons:
            kb.add(*buttons)
            
        kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb
    
    async def user_access_panel_list_menu(self, identifier: str, panels: list, panel_access: dict = None, cat_map: dict = None) -> types.InlineKeyboardMarkup:
        """نمایش لیست پنل‌ها به صورت دو ستونه + نوع پنل + وضعیت نودها"""
        kb = self.create_markup(row_width=2)
        
        if panel_access is None: panel_access = {}
        if cat_map is None: cat_map = {}
        
        if not panels:
            kb.add(self.btn("⚠️ هیچ پنلی یافت نشد", "noop"))
            kb.add(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
            return kb

        buttons = []
        for p in panels:
            p_id = str(p['id'])
            allowed_codes = panel_access.get(p_id, [])
            
            flags = ""
            if allowed_codes:
                shown_flags = [cat_map.get(code, code) for code in allowed_codes[:2]] 
                flags = "".join(shown_flags)
                if len(allowed_codes) > 2: flags += "+"
                flags = f" {flags}"
            
            p_type_short = p.get('panel_type', '')[:3].upper()
            btn_text = f"📂 {p['name']} ({p_type_short}){flags}"
            
            callback = f"admin:us_acc_n_list:{identifier}:{p['id']}"
            buttons.append(self.btn(btn_text, callback))

        kb.add(*buttons)
        kb.row(self.btn("🔙 بازگشت", f"admin:us:{identifier}"))
        return kb

    async def user_access_nodes_menu(self, identifier: str, panel_id: int, panel_name: str, nodes: list, allowed_nodes: list) -> types.InlineKeyboardMarkup:
        """نمایش لیست نودهای اختصاصی آن پنل"""
        kb = self.create_markup(row_width=2)
        
        buttons = []
        for node in nodes:
            code = node['code']
            flag = node['flag']
            name = node['name']
            
            is_allowed = code in allowed_nodes
            status = "✅" if is_allowed else "❌"
            
            text = f"{status} {flag} {name}"
            cb = f"admin:us_acc_tgl:{identifier}:{panel_id}:{code}"
            buttons.append(self.btn(text, cb))
            
        if buttons:
            kb.add(*buttons)
        else:
            kb.add(self.btn("⚠️ هیچ نودی برای این پنل تعریف نشده است", "noop"))
            
        kb.row(self.btn("🔙 بازگشت به لیست پنل‌ها", f"admin:us_acc_p_list:{identifier}"))
        return kb

    async def user_access_aggregated_menu(self, target_id, panels_data, user_panel_access):
        """منوی تجمیعی مدیریت دسترسی"""
        markup = types.InlineKeyboardMarkup(row_width=2)

        for item in panels_data:
            panel = item['panel']
            nodes = item['nodes']
            flag = item['flag']
            panel_id = str(panel['id'])
            
            current_access = user_panel_access.get(panel_id, [])

            header_text = f"📂 {panel['name']} ({panel['panel_type']}) {flag}"
            markup.add(types.InlineKeyboardButton(header_text, callback_data="admin:none"))

            node_btns = []
            for node in nodes:
                is_enabled = node['code'] in current_access
                status_icon = "✅" if is_enabled else "❌"
                
                btn_text = f"{status_icon} {node['flag']} {node['name']}"
                callback = f"admin:tgl_n_acc:{target_id}:{panel['id']}:{node['code']}"
                
                node_btns.append(types.InlineKeyboardButton(btn_text, callback_data=callback))
            
            if node_btns:
                markup.add(*node_btns)

        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data=f"admin:us:{target_id}"))
        
        return markup
    
    async def shop_management_menu(self, addons_list):
        """منوی لیست محصولات (کلیک برای جزئیات)"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        
        if not addons_list:
            keyboard.add(types.InlineKeyboardButton("❌ محصولی یافت نشد", callback_data="ignore"))
        else:
            for item in addons_list:
                # نمایش وضعیت با ایموجی
                status_icon = "🟢" if item['is_active'] else "🔴"
                btn_text = f"{status_icon} {item['name']} | 💰 {int(item['price'])}"
                
                # کلیک روی دکمه -> باز شدن جزئیات
                callback = f"admin:shop:detail:{item['id']}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=callback))

        keyboard.add(types.InlineKeyboardButton("➕ افزودن محصول جدید", callback_data="admin:shop:add"))
        keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin:panel"))
        return keyboard

    async def shop_item_detail_menu(self, item):
        """منوی جزئیات محصول (فعال‌سازی/حذف)"""
        kb = types.InlineKeyboardMarkup(row_width=2)
        
        # دکمه تغییر وضعیت
        status_text = "فعال ✅" if item['is_active'] else "غیرفعال ❌"
        kb.add(self.btn(f"وضعیت: {status_text}", f"admin:shop:toggle:{item['id']}"))
        
        # دکمه حذف
        kb.add(self.btn("🗑 حذف محصول", f"admin:shop:del:{item['id']}"))
        
        # دکمه بازگشت به لیست
        kb.add(self.btn("🔙 بازگشت به لیست", "admin:shop:main"))
        return kb

    # ✅ اصلاح شد: اضافه کردن self به عنوان آرگومان اول
    async def shop_cancel_menu(self):
        """دکمه انصراف هنگام ساخت محصول"""
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:shop:cancel"))
        return kb