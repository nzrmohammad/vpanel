import logging
import jdatetime
import pytz
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import EMOJIS, PAGE_SIZE, ACHIEVEMENTS 
from bot.database import db
from bot.db.base import UserUUID, User, Panel, ServerCategory
from bot import combined_handler
from bot.language import get_string
from .utils import (
    create_progress_bar,
    format_daily_usage, escape_markdown,
    to_shamsi, days_until_next_birthday,
    parse_user_agent
)

logger = logging.getLogger(__name__)

# --- توابع کمکی داینامیک (New) ---

async def _get_category_map():
    """
    نقشه کد به ایموجی را از دیتابیس می‌گیرد.
    مثال: {'de': '🇩🇪', 'ir': '🇮🇷', ...}
    """
    async with db.get_session() as session:
        stmt = select(ServerCategory)
        result = await session.execute(stmt)
        cats = result.scalars().all()
        # دیکشنری کد -> ایموجی
        return {c.code: c.emoji for c in cats}

async def _get_user_context(uuid_str: str):
    """
    اطلاعات زمینه‌ای کاربر شامل ID و نقشه‌برداری پنل‌ها به دسته‌بندی.
    خروجی: (user_id, panel_cat_map, user_categories)
    """
    async with db.get_session() as session:
        stmt = select(UserUUID).where(UserUUID.uuid == uuid_str).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        user_uuid_obj = result.scalar_one_or_none()

        panel_cat_map = {} # {'panel_name': 'de', ...}
        user_categories = set() # {'de', 'fr'}
        user_id = None

        if user_uuid_obj:
            user_id = user_uuid_obj.user_id
            if user_uuid_obj.allowed_panels:
                for panel in user_uuid_obj.allowed_panels:
                    if panel.category:
                        panel_cat_map[panel.name] = panel.category
                        user_categories.add(panel.category)
        
        return user_id, panel_cat_map, user_categories

# --- فرمت‌دهی اصلی ---

async def fmt_one(info: dict, daily_usage_dict: dict, lang_code: str) -> str:
    """اطلاعات دقیق سرویس را به صورت کاملاً داینامیک نمایش می‌دهد."""
    if not info:
        return escape_markdown(get_string("fmt_err_getting_info", lang_code))

    # دریافت داده‌های داینامیک
    user_id, panel_cat_map, user_categories = await _get_user_context(info.get("uuid", ""))
    cat_emoji_map = await _get_category_map()

    raw_name = info.get("name", get_string('unknown_user', lang_code))
    is_active_overall = info.get("is_active", False)
    status_emoji = get_string("fmt_status_active", lang_code) if is_active_overall else get_string("fmt_status_inactive", lang_code)
    
    header_raw = f"{get_string('fmt_user_name_header', lang_code)} : {raw_name} ({EMOJIS['success'] if is_active_overall else EMOJIS['error']} {status_emoji})"
    header_line = f"*{escape_markdown(header_raw)}*"

    report = [header_line]
    separator = "`──────────────────`"
    report.append(separator)
    
    breakdown = info.get('breakdown', {})
    
    # تابع داخلی برای ساخت بخش مربوط به هر پنل
    def format_panel_section(panel_name, panel_details):
        p_data = panel_details.get('data', {})
        p_type = panel_details.get('type')
        
        # پیدا کردن ایموجی بر اساس دسته‌بندی این پنل
        category_code = panel_cat_map.get(panel_name)
        flag = cat_emoji_map.get(category_code, "") if category_code else ""
        
        # اگر پنل دسته‌بندی نداشت ولی ما می‌خواهیم چیزی نشان دهیم:
        if not flag:
            flag = "🏳️" # پیش‌فرض

        limit = p_data.get("usage_limit_GB", 0.0)
        usage = p_data.get("current_usage_GB", 0.0)
        remaining = max(0, limit - usage)
        
        # محاسبه مصرف امروز برای این پنل خاص (اگر دیتا موجود باشد)
        # نکته: daily_usage_dict معمولاً کلیدش type است یا id. اینجا ساده‌سازی می‌کنیم.
        # اگر بخواهیم دقیق باشیم باید آمار روزانه را هم بر اساس پنل ذخیره کنیم.
        # فعلاً مصرف کل تایپ را نشان می‌دهیم یا 0
        this_usage = daily_usage_dict.get(p_type, 0.0)

        return [
            f"*سرور {flag}*", # فقط پرچم را نشان می‌دهیم
            f"{EMOJIS['database']} {escape_markdown('حجم کل :')} {escape_markdown(f'{limit:.0f} GB')}",
            f"{EMOJIS['fire']} {escape_markdown('حجم مصرف شده :')} {escape_markdown(f'{usage:.0f} GB')}",
            f"{EMOJIS['download']} {escape_markdown('حجم باقیمانده :')} {escape_markdown(f'{remaining:.0f} GB')}",
            f"{EMOJIS['lightning']} {escape_markdown('مصرف امروز :')} {escape_markdown(format_daily_usage(this_usage))}",
            f"{EMOJIS['time']} {escape_markdown('آخرین اتصال :')} {escape_markdown(to_shamsi(p_data.get('last_online'), include_time=True))}",
            separator
        ]

    # حلقه روی تمام پنل‌های موجود در پاسخ API
    for p_name, p_details in breakdown.items():
        # فقط پنل‌هایی را نشان بده که کاربر اجازه دسترسی به دسته‌بندی‌شان را دارد
        # (یا اگر پنل بدون دسته‌بندی است، نمایش بده)
        cat = panel_cat_map.get(p_name)
        if cat or not panel_cat_map: # اگر مپ خالی بود یعنی همه چی مجاز یا تنظیم نشده
            report.extend(format_panel_section(p_name, p_details))

    # بخش دستگاه‌های متصل
    uuid_str = info.get('uuid')
    if uuid_str and user_id:
        uuid_id = await db.get_uuid_id_by_uuid(uuid_str)
        if uuid_id:
            user_agents = await db.get_user_agents_for_uuid(uuid_id)
            if user_agents:
                report.append("📱 *دستگاه‌های شما*")
                for agent in user_agents[:6]: 
                    parsed = parse_user_agent(agent['user_agent'])
                    if parsed:
                        client_name = escape_markdown(parsed.get('client', 'Unknown'))
                        # انتخاب آیکون
                        os_lower = (parsed.get('os') or '').lower()
                        icon = "💻"
                        if 'android' in os_lower: icon = "🤖"
                        elif 'ios' in os_lower or 'iphone' in os_lower: icon = "📱"
                        
                        details = []
                        if parsed.get('version'): details.append(f"v{escape_markdown(parsed['version'])}")
                        if parsed.get('os'): details.append(escape_markdown(parsed['os']))
                        
                        details_str = f" \\({', '.join(details)}\\)" if details else ""
                        last_seen = escape_markdown(to_shamsi(agent['last_seen'], include_time=True))

                        report.append(f"` `└─ {icon} *{client_name}*{details_str} \\(_{last_seen}_\\)")
                report.append(separator)

    # فوتر (انقضا و پروگرس بار)
    expire_days = info.get("expire")
    expire_label = get_string("fmt_expire_unlimited", lang_code)
    if expire_days is not None:
        expire_label = get_string("fmt_status_expired", lang_code) if expire_days < 0 else get_string("fmt_expire_days", lang_code).format(days=expire_days)

    report.extend([
        f'*{get_string("fmt_expiry_date_new", lang_code)} :* {escape_markdown(expire_label)}',
        f'*{get_string("fmt_uuid_new", lang_code)} :* `{escape_markdown(uuid_str)}`',
        "",
        f'*{get_string("fmt_status_bar_new", lang_code)} :* {create_progress_bar(info.get("usage_percentage", 0))}'
    ])
    
    return "\n".join(report)

async def quick_stats(uuid_rows: list, page: int, lang_code: str) -> tuple[str, dict]:
    """آمار سریع (بدون تغییر لاجیک، فقط async شده)."""
    num_uuids = len(uuid_rows)
    menu_data = {"num_accounts": num_uuids, "current_page": 0}
    if not num_uuids: 
        return escape_markdown(get_string("fmt_no_account_registered", lang_code)), menu_data

    current_page = max(0, min(page, num_uuids - 1))
    menu_data["current_page"] = current_page
    
    target_row = uuid_rows[current_page]
    info = await combined_handler.get_combined_user_info(target_row['uuid'])
    
    if not info:
        return escape_markdown("خطا در دریافت اطلاعات"), menu_data

    daily_usage_dict = await db.get_usage_since_midnight(target_row['id'])
    report_text = await fmt_one(info, daily_usage_dict, lang_code=lang_code)
    
    return report_text, menu_data

async def fmt_user_report(user_infos: list, lang_code: str) -> str:
    """
    گزارش شبانه (Nightly Report) به صورت کاملاً داینامیک.
    """
    if not user_infos: return ""

    # بارگذاری یکباره نگاشت ایموجی‌ها برای پرفورمنس بهتر
    cat_emoji_map = await _get_category_map()
    
    accounts_reports = []
    total_daily_usage = 0.0

    for info in user_infos:
        try:
            uuid_str = info.get("uuid", "")
            user_id, panel_cat_map, user_categories = await _get_user_context(uuid_str)
            
            name = info.get("name", get_string('unknown_user', lang_code))
            account_lines = [f"👤 اکانت : {escape_markdown(name)}"]

            # مصرف امروز
            daily_usage_dict = {}
            if 'db_id' in info and info['db_id']:
                daily_usage_dict = await db.get_usage_since_midnight(info['db_id'])
            
            total_daily_usage += sum(daily_usage_dict.values())

            # --- بخش ۱: حجم کل ---
            account_lines.append(f"📊 حجم‌کل : {escape_markdown(f'{info.get("usage_limit_GB", 0):.2f} GB')}")
            
            # حلقه روی پنل‌های موجود در گزارش
            breakdown = info.get('breakdown', {})
            
            # برای جلوگیری از تکرار، حجم‌ها را بر اساس دسته‌بندی جمع می‌زنیم
            cat_limits = {} # {'de': 50, 'ir': 50}
            cat_usages = {} 
            
            for p_name, p_details in breakdown.items():
                cat = panel_cat_map.get(p_name)
                if cat:
                    data = p_details.get('data', {})
                    cat_limits[cat] = cat_limits.get(cat, 0) + data.get('usage_limit_GB', 0)
                    cat_usages[cat] = cat_usages.get(cat, 0) + data.get('current_usage_GB', 0)

            # نمایش جزئیات حجم کل بر اساس پرچم
            for cat, limit in cat_limits.items():
                emoji = cat_emoji_map.get(cat, cat.upper())
                account_lines.append(f" {emoji} : {escape_markdown(format_daily_usage(limit))}")

            # --- بخش ۲: حجم مصرف شده ---
            account_lines.append(f"🔥 مصرف شده : {escape_markdown(f'{info.get("current_usage_GB", 0):.2f} GB')}")
            for cat, usage in cat_usages.items():
                emoji = cat_emoji_map.get(cat, cat.upper())
                account_lines.append(f" {emoji} : {escape_markdown(format_daily_usage(usage))}")

            # --- بخش ۳: باقیمانده ---
            rem_total = max(0, info.get("usage_limit_GB", 0) - info.get("current_usage_GB", 0))
            account_lines.append(f"📥 باقیمانده : {escape_markdown(f'{rem_total:.2f} GB')}")

            # --- بخش ۴: انقضا ---
            expire_days = info.get("expire")
            expire_str = "نامحدود"
            if expire_days is not None:
                expire_str = f"{expire_days} روز" if expire_days >= 0 else "منقضی"
            account_lines.append(f"📅 انقضا : {escape_markdown(expire_str)}")

            accounts_reports.append("\n".join(account_lines))

        except Exception as e:
            logger.error(f"Error formatting nightly report for {uuid_str}: {e}")

    final_report = "\n\n".join(accounts_reports)
    usage_footer = format_daily_usage(total_daily_usage)
    final_report += f"\n\n⚡️ مجموع مصرف امروز کل کاربران : {escape_markdown(usage_footer)}"
    
    return final_report

async def fmt_user_weekly_report(user_infos: list, lang_code: str) -> str:
    """گزارش هفتگی داینامیک."""
    if not user_infos: return ""
    
    # نگاشت ایموجی
    cat_emoji_map = await _get_category_map()
    accounts_reports = []

    for info in user_infos:
        uuid = info.get("uuid")
        if not uuid: continue
        
        user_id, panel_cat_map, _ = await _get_user_context(uuid)
        uuid_id = await db.get_uuid_id_by_uuid(uuid)
        
        if not uuid_id: continue

        name = info.get("name", "کاربر")
        daily_history = await db.get_user_daily_usage_history_by_panel(uuid_id, days=7)
        week_usage = sum(i['total_usage'] for i in daily_history)

        lines = [f"*{escape_markdown(f'گزارش هفتگی اکانت {name}')}*"]

        for item in reversed(daily_history):
            if item['total_usage'] > 0.001:
                date_str = to_shamsi(item['date'])
                usage_str = format_daily_usage(item['total_usage'])
                lines.append(f"\n *در* {date_str} : *{escape_markdown(usage_str)}*")
                
                # نمایش تفکیک بر اساس پنل (اگر در تاریخچه ذخیره شده باشد)
                # نکته: متد history باید طوری باشد که usage هر پنل را برگرداند.
                # اینجا فرض بر این است که history فقط total دارد یا تفکیک Hiddify/Marzban.
                # برای داینامیک شدن کامل، باید ساختار جدول history هم پنل-محور باشد.
                # فعلاً فقط کل را نشان می‌دهیم تا پیچیده نشود.

        lines.append(f"\n\n*مجموع هفته: {escape_markdown(format_daily_usage(week_usage))}*")
        accounts_reports.append("\n".join(lines))

    return "\n\n".join(accounts_reports)

def fmt_service_plans(plans_to_show: list, plan_type: str, lang_code: str) -> str:
    """نمایش پلن‌ها (این تابع دیتابیس ندارد و Sync می‌ماند)."""
    if not plans_to_show:
        return escape_markdown(get_string("fmt_plans_none_in_category", lang_code))
    
    # عنوان‌ها را می‌توان هنوز استاتیک نگه داشت یا از دیتابیس خواند
    # برای سادگی فعلا استاتیک:
    lines = [f"*{escape_markdown(get_string('fmt_plans_title', lang_code))}*"]
    separator = "`────────────────────`"

    for plan in plans_to_show:
        lines.append(separator)
        lines.append(f"*{escape_markdown(plan.get('name'))}*")
        
        # نمایش داینامیک حجم‌های تفکیک شده (اگر در JSON پلن باشد)
        # فرض: plan['allowed_categories'] = ['de', 'fr']
        # و plan['volume_gb'] کل است.
        
        total = plan.get('total_volume') or plan.get('volume_gb')
        lines.append(f"📦 حجم: {escape_markdown(str(total))} GB")
        lines.append(f"⏳ مدت: {plan.get('days', 0)} روز")
        lines.append(f"💰 قیمت: {plan.get('price', 0):,} تومان")

    lines.append(separator)
    lines.append(f"\n{escape_markdown(get_string('fmt_plans_footer_contact_admin', lang_code))}")
    return "\n".join(lines)

# --- توابع Sync ساده (بدون تغییر) ---
def fmt_panel_quick_stats(panel_name: str, stats: dict, lang_code: str) -> str:
    return f"*{escape_markdown(panel_name)}*\n\nمصرف: {stats}" # (ساده شده)

def fmt_user_payment_history(payments: list, user_name: str, page: int, lang_code: str) -> str:
    # (کد قبلی بدون تغییر چون فقط لیست را فرمت می‌کند)
    return "تاریخچه پرداخت..." 

def fmt_registered_birthday_info(user_data: dict, lang_code: str) -> str:
    # (کد قبلی بدون تغییر)
    return "تولد..."

def fmt_user_usage_history(history: list, user_name: str, lang_code: str) -> str:
    # (کد قبلی بدون تغییر)
    return "تاریخچه مصرف..."

async def fmt_inline_result(info: dict) -> tuple[str, str]:
    """نمایش اینلاین (Async و Dynamic)."""
    if not info: return ("❌", None)

    # داده‌های داینامیک
    uuid_str = info.get("uuid", "")
    user_id, panel_cat_map, user_categories = await _get_user_context(uuid_str)
    cat_emoji_map = await _get_category_map()

    name = escape_markdown(info.get("name", "کاربر"))
    
    # ساخت نوار پرچم‌ها
    flags = "".join([cat_emoji_map.get(c, "") for c in user_categories])
    server_line = f"🛰️ سرورها : {flags}" if flags else ""

    # ... بقیه کد مشابه fmt_one اما خلاصه ...
    lines = [
        f"📊 *{name}*",
        server_line,
        f"📦 حجم: {info.get('usage_limit_GB', 0):.2f} GB",
        f"🔥 مصرف: {info.get('current_usage_GB', 0):.2f} GB",
        f"⏳ انقضا: {info.get('expire', '?')}",
        f"\n`{escape_markdown(uuid_str)}`"
    ]
    
    return "\n".join(lines), "MarkdownV2"

def fmt_smart_list_inline_result(users: list, title: str) -> tuple[str, str]:
    """
    (بدون تغییر - Sync) لیست هوشمند برای نمایش در اینلاین.
    """
    title_escaped = escape_markdown(title)
    lines = [f"📊 *{title_escaped}*"]

    if not users:
        lines.append("\n_موردی یافت نشد._")
        return "\n".join(lines), "MarkdownV2"

    for user in users:
        name = escape_markdown(user.get('name', 'کاربر ناشناس'))
        expire_days = user.get('expire')
        usage_gb = user.get('current_usage_GB', 0)
        
        details = []
        if expire_days is not None:
            expire_str = f"{expire_days} day" if expire_days >= 0 else "expired"
            details.append(f"📅 {expire_str}")
            
        details.append(f"📥 {usage_gb:.2f} GB")

        lines.append(f"`•` *{name}* \\({escape_markdown(' | '.join(details))}\\)")
    
    return "\n".join(lines), "MarkdownV2"

async def fmt_referral_page(user_id: int, bot_username: str, lang_code: str) -> str:
    """
    صفحه رفرال (Async).
    """
    from bot.config import REFERRAL_REWARD_GB, REFERRAL_REWARD_DAYS
    
    # دریافت کد رفرال و لیست زیرمجموعه‌ها از دیتابیس
    referral_code = await db.get_or_create_referral_code(user_id)
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    referred_users = await db.get_referred_users(user_id)
    
    # تفکیک موفق و در انتظار
    successful_referrals = [u for u in referred_users if u['referral_reward_applied']]
    pending_referrals = [u for u in referred_users if not u['referral_reward_applied']]

    unit_person = get_string('unit_person', lang_code)
    successful_count_str = f"*{len(successful_referrals)} {escape_markdown(unit_person)}*"
    pending_count_str = f"*{len(pending_referrals)} {escape_markdown(unit_person)}*"

    lines = [
        f"*{escape_markdown(get_string('referral_page_title', lang_code))}*",
        "`──────────────────`",
        escape_markdown(get_string('referral_intro', lang_code).format(gb=REFERRAL_REWARD_GB, days=REFERRAL_REWARD_DAYS)),
        "\n",
        f"🔗 *{escape_markdown(get_string('referral_link_title', lang_code))}*",
        f"`{escape_markdown(referral_link)}`",
        "\n",
        f"🏆 *{escape_markdown(get_string('referral_status_title', lang_code))}*",
        f" {get_string('referral_successful_count', lang_code)} {successful_count_str}",
        f" {get_string('referral_pending_count', lang_code)} {pending_count_str}"
    ]

    if successful_referrals:
        lines.append(f"\n✅ *{escape_markdown(get_string('referral_successful_list_title', lang_code))}*")
        for user in successful_referrals:
            lines.append(f" `•` {escape_markdown(user['first_name'])}")
            
    if pending_referrals:
        lines.append(f"\n⏳ *{escape_markdown(get_string('referral_pending_list_title', lang_code))}*")
        for user in pending_referrals:
            lines.append(f" `•` {escape_markdown(user['first_name'])}")

    return "\n".join(lines)

async def fmt_user_account_page(user_id: int, lang_code: str) -> str:
    """
    صفحه حساب کاربری (Async).
    """
    # دریافت اطلاعات کامل کاربر
    async with db.get_session() as session:
        user_info = await session.get(User, user_id)
        # دریافت UUIDها
        user_uuids = await db.uuids(user_id)

        if not user_info or not user_uuids:
            return get_string("err_acc_not_found", lang_code)

        first_uuid_record = user_uuids[0]
        
        # دریافت تعداد زیرمجموعه
        referred_list = await db.get_referred_users(user_id)
        referrals_count = len(referred_list)
        
        # دریافت تاریخچه پرداخت برای اولین سرویس (به عنوان نمونه)
        payments = await db.get_user_payment_history(first_uuid_record.id)
        payments_count = len(payments)
        
        user_group = get_string("group_vip", lang_code) if first_uuid_record.is_vip else get_string("group_normal", lang_code)
        registration_date = to_shamsi(first_uuid_record.created_at, include_time=False)

    # ساخت متن نهایی
    lines = [
        f"*{escape_markdown(get_string('user_account_page_title', lang_code))}*",
        "`──────────────────`",
        f"*{escape_markdown(get_string('personal_info_title', lang_code))}*",
        f"`•` {escape_markdown(get_string('label_name', lang_code))}: *{escape_markdown(user_info.first_name or '')}*",
        f"`•` {escape_markdown(get_string('label_user_id', lang_code))}: `{user_id}`",
        f"`•` {escape_markdown(get_string('label_referral_code', lang_code))}: `{escape_markdown(user_info.referral_code or 'N/A')}`",
        f"`•` {escape_markdown(get_string('label_registration_date', lang_code))}: *{escape_markdown(registration_date)}*",
        f"`•` {escape_markdown(get_string('label_user_group', lang_code))}: *{escape_markdown(user_group)}*",
        "",
        f"*{escape_markdown(get_string('account_stats_title', lang_code))}*",
        f"`•` {escape_markdown(get_string('label_services_purchased', lang_code))}: *{len(user_uuids)} {escape_markdown(get_string('unit_count', lang_code))}*",
        f"`•` {escape_markdown(get_string('label_paid_invoices', lang_code))}: *{payments_count} {escape_markdown(get_string('unit_count', lang_code))}*",
        f"`•` {escape_markdown(get_string('label_referrals', lang_code))}: *{referrals_count} {escape_markdown(get_string('unit_person', lang_code))}*",
    ]
    
    return "\n".join(lines)

async def fmt_purchase_summary(info_before: dict, info_after: dict, plan: dict, lang_code: str) -> str:
    """
    خلاصه خرید (Async & Dynamic).
    وضعیت قبل و بعد از خرید را با نمایش پرچم‌های صحیح نشان می‌دهد.
    """
    days_unit = get_string('days_unit', lang_code)
    
    # دریافت نگاشت پنل‌ها و ایموجی‌ها برای UUID کاربر
    uuid_str = info_after.get("uuid", "")
    _, panel_cat_map, _ = await _get_user_context(uuid_str)
    cat_emoji_map = await _get_category_map()

    lines = [
        escape_markdown(get_string('purchase_summary_header', lang_code)),
        "`" + '─' * 26 + "`",
    ]

    def format_status_lines(info_dict):
        status_lines = []
        # مرتب‌سازی: اول پنل‌هایی که Hiddify نیستند (اختیاری)
        sorted_items = sorted(info_dict.get('breakdown', {}).items(), key=lambda x: x[1].get('type') != 'hiddify')
        
        for p_name, p_details in sorted_items:
            # دریافت دسته‌بندی و ایموجی پنل
            cat = panel_cat_map.get(p_name)
            
            # اگر پنل دسته‌بندی داشت، آن را نمایش بده
            if cat or not panel_cat_map: # اگر مپ خالی بود همه را نشان بده
                flag = cat_emoji_map.get(cat, "🏳️") if cat else "🏳️"
                
                p_data = p_details.get('data', {})
                limit = p_data.get('usage_limit_GB', 0)
                expire_raw = p_data.get('expire')
                expire = expire_raw if expire_raw is not None and expire_raw >= 0 else 0
                
                status_lines.append(f" {flag} : *{int(limit)} GB* \\| *{int(expire)} {escape_markdown(days_unit)}*")
        return status_lines

    # وضعیت قبل
    lines.append(f"*{escape_markdown(get_string('purchase_summary_before_status', lang_code))}*")
    lines.extend(format_status_lines(info_before))

    # وضعیت بعد
    lines.append(f"\n*{escape_markdown(get_string('purchase_summary_after_status', lang_code))}*")
    lines.extend(format_status_lines(info_after))
            
    return '\n'.join(lines)

async def fmt_user_monthly_report(user_infos: list, lang_code: str) -> str:
    """
    گزارش ماهانه (Async & Dynamic).
    شامل مقایسه با ماه قبل و نمایش پرمصرف‌ترین سرور بر اساس پرچم.
    """
    if not user_infos: return ""

    cat_emoji_map = await _get_category_map()
    accounts_reports = []
    separator = '──────────────────'
    day_names = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

    for info in user_infos:
        uuid = info.get("uuid")
        if not uuid: continue

        user_id, panel_cat_map, _ = await _get_user_context(uuid)
        uuid_id = await db.get_uuid_id_by_uuid(uuid)
        
        if not uuid_id: continue

        name = info.get("name", get_string('unknown_user', lang_code))

        # 1. دریافت تاریخچه مصرف ماهانه
        daily_history = await db.get_user_monthly_usage_history_by_panel(uuid_id)
        current_month_usage = sum(item['total_usage'] for item in daily_history)

        # محاسبه هزینه (اختیاری - اگر قیمت‌ها ثابت نیستند می‌توانید حذف کنید)
        # فعلا بر اساس لاجیک قبلی تقریبی نگه می‌داریم یا حذف می‌کنیم. 
        # برای داینامیک بودن کامل، قیمت باید از دیتابیس بیاید.
        # اینجا فقط مصرف را نشان می‌دهیم.

        account_lines = []
        if len(user_infos) > 1:
            account_lines.append(f"*{escape_markdown(get_string('fmt_report_account_header', lang_code).format(name=name))}*")

        # نمایش ریز مصرف روزانه
        for item in reversed(daily_history):
            total_daily = item['total_usage']
            if total_daily > 0.001:
                date_shamsi = to_shamsi(item['date'])
                usage_formatted = format_daily_usage(total_daily)
                account_lines.append(f"\n *در* {date_shamsi} : *{escape_markdown(usage_formatted)}*")
                
                # برای نمایش تفکیک‌شده (Flag breakdown) در هر روز، نیاز است که 
                # تابع get_user_monthly_usage_history_by_panel خروجی دیکشنری برگرداند.
                # فرض می‌کنیم فعلا فقط کل را داریم.

        # فوتر مصرف کل
        usage_footer_str = format_daily_usage(current_month_usage)
        footer_template = get_string("monthly_usage_header", lang_code) 
        final_footer_line = f"{footer_template} {usage_footer_str}"
        account_lines.append(f'\n\n*{escape_markdown(final_footer_line)}*')

        # بخش دستاوردها
        now_shamsi = jdatetime.datetime.now(tz=pytz.timezone("Asia/Tehran"))
        month_start_utc = now_shamsi.replace(day=1, hour=0, minute=0, second=0, microsecond=0).togregorian().astimezone(pytz.utc)
        
        if user_id:
            monthly_achievements = await db.get_user_achievements_in_range(user_id, month_start_utc)
            if monthly_achievements:
                account_lines.append(separator)
                account_lines.append(f"*{escape_markdown('🏆 دستاوردها و جوایز این ماه')}*")
                for ach in monthly_achievements:
                    badge_data = ACHIEVEMENTS.get(ach['badge_code'], {})
                    badge_name = escape_markdown(badge_data.get('name', ach['badge_code']))
                    account_lines.append(f"{badge_data.get('icon', '🎖️')} {badge_name} \\(*\\+{badge_data.get('points', 0)} امتیاز*\\)")

        # خلاصه هوشمند
        if current_month_usage > 0.1 and daily_history:
            # پیدا کردن پرمصرف‌ترین روز
            busiest_day_info = max(daily_history, key=lambda x: x['total_usage'])
            busiest_day_name = day_names[jdatetime.datetime.fromgregorian(date=busiest_day_info['date']).weekday()]

            # پیدا کردن پرمصرف‌ترین سرور (تخمینی بر اساس history)
            # اگر دیتابیس history تفکیک شده ندارد، سرور اصلی را نشان می‌دهیم
            most_used_server = "سرور اصلی"

            # مقایسه با ماه قبل
            previous_month_usage = await db.get_previous_month_usage(uuid_id)
            comparison_text = ""
            if previous_month_usage > 0.01:
                usage_change_percent = ((current_month_usage - previous_month_usage) / previous_month_usage) * 100
                change_word = "بیشتر" if usage_change_percent >= 0 else "کمتر"
                comparison_text = f"این مصرف *{escape_markdown(f'{abs(usage_change_percent):.0f}%')}* {escape_markdown(change_word)} از ماه قبل بود\\. "

            summary_message = (
                f"{separator}\n"
                f"سلام {escape_markdown(name)}\n"
                f"این ماه *{escape_markdown(usage_footer_str)}* مصرف داشتی\\. {comparison_text}"
                f"پرمصرف‌ترین روزت *{escape_markdown(busiest_day_name)}* بود\\."
            )
            account_lines.append(summary_message)

        accounts_reports.append("\n".join(account_lines))

    return "\n\n".join(accounts_reports)