# bot/admin_handlers/navigation.py

from telebot import types
from bot.bot_instance import bot
from bot.utils import _safe_edit
from bot.keyboards import admin as admin_menu
from bot.admin_handlers import reporting

# توابع ساده نویگیشن (نمایش منوها)

async def handle_show_panel(call, params):
    """نمایش پنل اصلی"""
    await _safe_edit(call.from_user.id, call.message.message_id, "👑 پنل مدیریت", reply_markup=await admin_menu.main())

async def handle_management_menu(call, params):
    """نمایش منوی مدیریت کاربران"""
    await _safe_edit(call.from_user.id, call.message.message_id, "👥 مدیریت کاربران", reply_markup=await admin_menu.management_menu())

async def handle_search_menu(call, params):
    """نمایش منوی جستجو"""
    await _safe_edit(call.from_user.id, call.message.message_id, "🔎 لطفاً نوع جستجو را انتخاب کنید:", reply_markup=await admin_menu.search_menu())

async def handle_group_actions_menu(call, params):
    """نمایش منوی دستورات گروهی"""
    await _safe_edit(call.from_user.id, call.message.message_id, "⚙️ لطفاً نوع دستور گروهی را انتخاب کنید:", reply_markup=await admin_menu.group_actions_menu())

async def handle_user_analysis_menu(call, params):
    """هدایت به تحلیل کاربر"""
    await reporting.handle_select_plan_for_report_menu(call, params)

async def handle_system_status_menu(call, params):
    """نمایش منوی وضعیت سیستم"""
    await _safe_edit(call.from_user.id, call.message.message_id, "📊 لطفاً پنل مورد نظر برای مشاهده وضعیت را انتخاب کنید:", reply_markup=await admin_menu.system_status_menu())

async def handle_panel_management_menu(call, params):
    """نمایش منوی مدیریت پنل‌ها"""
    # پاک کردن استپ هندلر قبلی اگر وجود داشته باشد (اختیاری)
    # bot.clear_step_handler_by_chat_id(call.from_user.id) # در async نیازی نیست چون خودمان مدیریت می‌کنیم
    
    if params:
        panel_type = params[0]
        panel_name = "Hiddify" if panel_type == "hiddify" else "Marzban"
        await _safe_edit(
            call.from_user.id, 
            call.message.message_id, 
            f"مدیریت کاربران پنل‌های نوع *{panel_name}*", 
            reply_markup=await admin_menu.panel_management_menu(panel_type)
        )
    else:
        # هندل کردن حالت بدون پارامتر (منوی اصلی پنل‌ها)
        # فرض بر این است که هندلری در panel_management وجود دارد، اگر نه همینجا نمایش دهید
        from bot.admin_handlers import panel_management
        await panel_management.handle_panel_management_menu(call, params)

async def handle_server_selection(call, params):
    """منوی انتخاب سرور عمومی"""
    base_callback = params[0]
    text_map = {
        "reports_menu": "لطفاً نوع پنل را برای گزارش‌گیری انتخاب کنید:",
        "analytics_menu": "لطفاً نوع پنل را برای تحلیل و آمار انتخاب کنید:"
    }
    text = text_map.get(base_callback, "لطفا انتخاب کنید:")
    
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        text,
        reply_markup=await admin_menu.server_selection_menu(f"admin:{base_callback}")
    )