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

# --- توابع کمکی داخلی (Private Helpers) ---
# این توابع چون مستقیماً به دیتابیس وصل می‌شوند و مستقل هستند،
# می‌توانند بیرون کلاس یا به عنوان متدهای استاتیک باقی بمانند.

async def _get_category_map():
    """نقشه کد به ایموجی را از دیتابیس می‌گیرد."""
    async with db.get_session() as session:
        stmt = select(ServerCategory)
        result = await session.execute(stmt)
        cats = result.scalars().all()
        return {c.code: c.emoji for c in cats}

async def _get_user_context(uuid_str: str):
    """اطلاعات زمینه‌ای کاربر شامل ID و نقشه‌برداری پنل‌ها به دسته‌بندی."""
    async with db.get_session() as session:
        stmt = select(UserUUID).where(UserUUID.uuid == uuid_str).options(selectinload(UserUUID.allowed_panels))
        result = await session.execute(stmt)
        user_uuid_obj = result.scalar_one_or_none()

        panel_cat_map = {} 
        user_categories = set()
        user_id = None

        if user_uuid_obj:
            user_id = user_uuid_obj.user_id
            if user_uuid_obj.allowed_panels:
                for panel in user_uuid_obj.allowed_panels:
                    if panel.category:
                        panel_cat_map[panel.name] = panel.category
                        user_categories.add(panel.category)
        
        return user_id, panel_cat_map, user_categories


# --- کلاس اصلی فرمتر (Main Class) ---

class UserFormatter:
    """
    مسئول تولید متن‌ها و پیام‌های نمایشی برای کاربران.
    تمام متدها به صورت یکپارچه در این کلاس قرار دارند.
    """

    async def profile_info(self, info: dict, lang_code: str) -> str:
        """
        نمایش اطلاعات دقیق سرویس (پرچم داینامیک از دیتابیس + انقضای هوشمند).
        """
        if not info:
            return escape_markdown(get_string("fmt_err_getting_info", lang_code))

        # 1. دریافت مصرف روزانه
        daily_usage_dict = {} 
        if 'db_id' in info and info['db_id']:
             daily_usage_dict = await db.get_usage_since_midnight(info['db_id'])

        # 2. دریافت نقشه ایموجی‌ها از دیتابیس (برای پرچم‌های داینامیک)
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
        
        def format_panel_section(panel_name, panel_details):
            p_data = panel_details.get('data', {})
            p_type = panel_details.get('type')
            
            # --- بخش ۱: پرچم داینامیک از دیتابیس ---
            # این مقدار category را باید قبلاً در combined_handler به دیکشنری اضافه کرده باشید
            category_code = panel_details.get('category')
            
            # جستجو در مپ دیتابیس
            flag = cat_emoji_map.get(category_code, "") if category_code else ""
            if not flag: 
                flag = "🏳️" # پرچم پیش‌فرض اگر پیدا نشد

            # محاسبات حجم
            limit = p_data.get("usage_limit_GB", 0.0)
            usage = p_data.get("current_usage_GB", 0.0)
            remaining = max(0, limit - usage)
            this_usage = daily_usage_dict.get(p_type, 0.0)

            # --- بخش ۲: تشخیص هوشمند انقضا ---
            expire_val = p_data.get('expire')
            
            # پیش‌فرض: نامحدود
            expire_str = get_string("fmt_expire_unlimited", lang_code)

            if expire_val is not None:
                # حالت الف: Timestamp (عدد بزرگ - مثل مرزبان)
                if isinstance(expire_val, (int, float)) and expire_val > 100_000_000:
                    try:
                        # تبدیل تایم‌ستمپ به آبجکت زمان
                        expire_dt = datetime.fromtimestamp(expire_val)
                        now = datetime.now()
                        remaining_days = (expire_dt - now).days
                        
                        if remaining_days < 0:
                            expire_str = get_string("fmt_status_expired", lang_code)
                        else:
                            expire_str = get_string("fmt_expire_days", lang_code).format(days=remaining_days)
                    except:
                        pass # اگر خطا داد همان نامحدود بماند
                
                # حالت ب: تعداد روز (عدد کوچک - مثل هیدیفای)
                elif isinstance(expire_val, (int, float)) and expire_val > 0:
                     expire_str = get_string("fmt_expire_days", lang_code).format(days=int(expire_val))
                
                # حالت ج: اگر صفر یا منفی بود (و تایم‌ستمپ نبود) معمولاً یعنی منقضی یا نامحدود
                # اما طبق منطق قبلی شما، اگر None نباشد و >0 نباشد، احتمالاً منقضی است (مگر اینکه 0 به معنی نامحدود باشد)
                # اینجا فرض می‌کنیم 0 یا منفی یعنی منقضی
                elif isinstance(expire_val, (int, float)) and expire_val <= 0:
                     # چک کنیم شاید پنل 0 را نامحدود می‌دهد، اما معمولاً Expired است
                     # برای اطمینان کد "نامحدود" پیش‌فرض را تغییر نمی‌دهیم مگر اینکه مطمئن باشیم Expired است
                     # اما شما در کد قدیمی برای < 0 زده بودید expired.
                     if expire_val < 0:
                         expire_str = get_string("fmt_status_expired", lang_code)

            return [
                f"*سرور {flag}*",
                f"{EMOJIS['database']} {escape_markdown('حجم کل :')} {escape_markdown(f'{limit:.0f} GB')}",
                f"{EMOJIS['fire']} {escape_markdown('حجم مصرف شده :')} {escape_markdown(f'{usage:.0f} GB')}",
                f"{EMOJIS['download']} {escape_markdown('حجم باقیمانده :')} {escape_markdown(f'{remaining:.0f} GB')}",
                f"{EMOJIS['lightning']} {escape_markdown('مصرف امروز :')} {escape_markdown(format_daily_usage(this_usage))}",
                f"{EMOJIS['time']} {escape_markdown('آخرین اتصال :')} {escape_markdown(to_shamsi(p_data.get('last_online'), include_time=True))}",
                f"📅 {escape_markdown('انقضا :')} {escape_markdown(expire_str)}", # ✅ نمایش صحیح در باکس
                separator
            ]

        for p_name, p_details in breakdown.items():
            report.extend(format_panel_section(p_name, p_details))

        # --- بخش دستگاه‌های متصل (بدون تغییر) ---
        uuid_str = info.get('uuid')
        # تبدیل به رشته برای اطمینان
        safe_uuid_str = str(uuid_str) if uuid_str else ""
        
        user_id = None
        if safe_uuid_str:
             user_id = await db.get_user_id_by_uuid(safe_uuid_str)

        if safe_uuid_str and user_id:
            uuid_id_db = await db.get_uuid_id_by_uuid(safe_uuid_str)
            if uuid_id_db:
                user_agents = await db.get_user_agents_for_uuid(uuid_id_db)
                if user_agents:
                    report.append("📱 *دستگاه‌های شما*")
                    for agent in user_agents[:6]: 
                        parsed = parse_user_agent(agent['user_agent'])
                        if parsed:
                            client_name = escape_markdown(parsed.get('client', 'Unknown'))
                            icon = "💻"
                            last_seen = escape_markdown(to_shamsi(agent['last_seen'], include_time=True))
                            report.append(f"` `└─ {icon} *{client_name}* \\(_{last_seen}_\\)")
                    report.append(separator)

        # --- بخش پایانی: فقط نوار وضعیت و UUID (انقضا حذف شد چون بالا نمایش دادیم) ---
        report.extend([
            f'*{get_string("fmt_uuid_new", lang_code)} :* `{escape_markdown(safe_uuid_str)}`',
            "",
            f'*{get_string("fmt_status_bar_new", lang_code)} :* {create_progress_bar(info.get("usage_percentage", 0))}'
        ])
        
        return "\n".join(report)

    async def quick_stats(self, uuid_rows: list, page: int, lang_code: str) -> tuple[str, dict]:
        """آمار فوری."""
        num_uuids = len(uuid_rows)
        menu_data = {"num_accounts": num_uuids, "current_page": 0}
        if not num_uuids: 
            return escape_markdown(get_string("fmt_no_account_registered", lang_code)), menu_data

        current_page = max(0, min(page, num_uuids - 1))
        menu_data["current_page"] = current_page
        
        target_row = uuid_rows[current_page]
        
        uuid_str = str(target_row['uuid']) 
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if not info:
            return escape_markdown("خطا در دریافت اطلاعات"), menu_data

        report_text = await self.profile_info(info, lang_code)
        return report_text, menu_data

    async def nightly_report(self, user_infos: list, lang_code: str) -> str:
        """گزارش شبانه (نام قبلی: fmt_user_report)."""
        if not user_infos: return ""
        cat_emoji_map = await _get_category_map()
        accounts_reports = []
        total_daily_usage = 0.0

        for info in user_infos:
            try:
                uuid_str = info.get("uuid", "")
                user_id, panel_cat_map, user_categories = await _get_user_context(uuid_str)
                name = info.get("name", get_string('unknown_user', lang_code))
                account_lines = [f"👤 اکانت : {escape_markdown(name)}"]

                daily_usage_dict = {}
                if 'db_id' in info and info['db_id']:
                    daily_usage_dict = await db.get_usage_since_midnight(info['db_id'])
                
                total_daily_usage += sum(daily_usage_dict.values())

                account_lines.append(f"📊 حجم‌کل : {escape_markdown(f'{info.get("usage_limit_GB", 0):.2f} GB')}")
                
                breakdown = info.get('breakdown', {})
                cat_limits = {} 
                cat_usages = {} 
                
                for p_name, p_details in breakdown.items():
                    cat = panel_cat_map.get(p_name)
                    if cat:
                        data = p_details.get('data', {})
                        cat_limits[cat] = cat_limits.get(cat, 0) + data.get('usage_limit_GB', 0)
                        cat_usages[cat] = cat_usages.get(cat, 0) + data.get('current_usage_GB', 0)

                for cat, limit in cat_limits.items():
                    emoji = cat_emoji_map.get(cat, cat.upper())
                    account_lines.append(f" {emoji} : {escape_markdown(format_daily_usage(limit))}")

                account_lines.append(f"🔥 مصرف شده : {escape_markdown(f'{info.get("current_usage_GB", 0):.2f} GB')}")
                for cat, usage in cat_usages.items():
                    emoji = cat_emoji_map.get(cat, cat.upper())
                    account_lines.append(f" {emoji} : {escape_markdown(format_daily_usage(usage))}")

                rem_total = max(0, info.get("usage_limit_GB", 0) - info.get("current_usage_GB", 0))
                account_lines.append(f"📥 باقیمانده : {escape_markdown(f'{rem_total:.2f} GB')}")

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

    def service_plans(self, plans_to_show: list, plan_type: str, lang_code: str) -> str:
        """نمایش لیست پلن‌ها."""
        if not plans_to_show:
            return escape_markdown(get_string("fmt_plans_none_in_category", lang_code))
        
        lines = [f"*{escape_markdown(get_string('fmt_plans_title', lang_code))}*"]
        separator = "`────────────────────`"

        for plan in plans_to_show:
            lines.append(separator)
            lines.append(f"*{escape_markdown(plan.get('name'))}*")
            total = plan.get('total_volume') or plan.get('volume_gb')
            lines.append(f"📦 حجم: {escape_markdown(str(total))} GB")
            lines.append(f"⏳ مدت: {plan.get('days', 0)} روز")
            lines.append(f"💰 قیمت: {plan.get('price', 0):,} تومان")

        lines.append(separator)
        lines.append(f"\n{escape_markdown(get_string('fmt_plans_footer_contact_admin', lang_code))}")
        return "\n".join(lines)

    async def purchase_summary(self, info_before: dict, info_after: dict, plan: dict, lang_code: str) -> str:
        """خلاصه خرید (قبل و بعد)."""
        days_unit = get_string('days_unit', lang_code)
        uuid_str = info_after.get("uuid", "")
        _, panel_cat_map, _ = await _get_user_context(uuid_str)
        cat_emoji_map = await _get_category_map()
        
        lines = [
            escape_markdown(get_string('purchase_summary_header', lang_code)),
            "`" + '─' * 26 + "`",
        ]
        
        def format_status_lines(info_dict):
            status_lines = []
            sorted_items = sorted(info_dict.get('breakdown', {}).items(), key=lambda x: x[1].get('type') != 'hiddify')
            for p_name, p_details in sorted_items:
                cat = panel_cat_map.get(p_name)
                if cat or not panel_cat_map: 
                    flag = cat_emoji_map.get(cat, "🏳️") if cat else "🏳️"
                    p_data = p_details.get('data', {})
                    limit = p_data.get('usage_limit_GB', 0)
                    expire_raw = p_data.get('expire')
                    expire = expire_raw if expire_raw is not None and expire_raw >= 0 else 0
                    status_lines.append(f" {flag} : *{int(limit)} GB* \\| *{int(expire)} {escape_markdown(days_unit)}*")
            return status_lines
            
        lines.append(f"*{escape_markdown(get_string('purchase_summary_before_status', lang_code))}*")
        lines.extend(format_status_lines(info_before))
        lines.append(f"\n*{escape_markdown(get_string('purchase_summary_after_status', lang_code))}*")
        lines.extend(format_status_lines(info_after))
        return '\n'.join(lines)

    async def user_account_page(self, user_id: int, lang_code: str) -> str:
        """صفحه حساب کاربری."""
        async with db.get_session() as session:
            user_info = await session.get(User, user_id)
            user_uuids = await db.uuids(user_id)
            if not user_info or not user_uuids:
                return get_string("err_acc_not_found", lang_code)
            
            first_uuid_record = user_uuids[0]
            referred_list = await db.get_referred_users(user_id)
            referrals_count = len(referred_list)
            payments = await db.get_user_payment_history(first_uuid_record.id)
            payments_count = len(payments)
            user_group = get_string("group_vip", lang_code) if first_uuid_record.is_vip else get_string("group_normal", lang_code)
            registration_date = to_shamsi(first_uuid_record.created_at, include_time=False)
            
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

    def wallet_page(self, balance: float, transactions: list, lang_code: str) -> str:
        """صفحه اصلی کیف پول."""
        tx_list = ""
        if transactions:
            for t in transactions:
                amount = t.get('amount', 0)
                desc = t.get('type', '') # یا description
                icon = "➕" if amount > 0 else "➖"
                tx_list += f"{icon} {int(abs(amount)):,} ({desc})\n"
        else:
            tx_list = "تراکنشی یافت نشد"
            
        return (
            f"💰 <b>{get_string('wallet', lang_code)}</b>\n"
            f"──────────────────\n"
            f"💵 موجودی: {int(balance):,} تومان\n\n"
            f"📜 <b>{get_string('transaction_history', lang_code)}:</b>\n{tx_list}"
        )

    def purchase_confirmation(self, plan_name: str, price: float, current_balance: float, lang_code: str) -> str:
        """متن تایید خرید."""
        return (
            f"🧾 <b>تایید نهایی خرید</b>\n\n"
            f"📦 سرویس: {plan_name}\n"
            f"💰 قیمت: {int(price):,} تومان\n"
            f"💳 موجودی شما: {int(current_balance):,} تومان\n\n"
            f"آیا از خرید اطمینان دارید؟"
        )

    async def referral_page(self, user_id: int, bot_username: str, lang_code: str) -> str:
        """صفحه رفرال."""
        from bot.config import REFERRAL_REWARD_GB, REFERRAL_REWARD_DAYS
        referral_code = await db.get_or_create_referral_code(user_id)
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        referred_users = await db.get_referred_users(user_id)
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

    async def inline_result(self, info: dict) -> tuple[str, str]:
        """فرمت خروجی اینلاین."""
        if not info: return ("❌", None)
        uuid_str = info.get("uuid", "")
        _, panel_cat_map, user_categories = await _get_user_context(uuid_str)
        cat_emoji_map = await _get_category_map()
        name = escape_markdown(info.get("name", "کاربر"))
        flags = "".join([cat_emoji_map.get(c, "") for c in user_categories])
        server_line = f"🛰️ سرورها : {flags}" if flags else ""
        lines = [
            f"📊 *{name}*",
            server_line,
            f"📦 حجم: {info.get('usage_limit_GB', 0):.2f} GB",
            f"🔥 مصرف: {info.get('current_usage_GB', 0):.2f} GB",
            f"⏳ انقضا: {info.get('expire', '?')}",
            f"\n`{escape_markdown(uuid_str)}`"
        ]
        return "\n".join(lines), "MarkdownV2"

# --- توابع قدیمی که هنوز استفاده نشده‌اند ولی شاید نیاز شوند ---
# این‌ها را هم می‌توان به کلاس اضافه کرد یا اگر استفاده نمی‌شوند حذف کرد.
# فعلاً برای سازگاری حذف نمی‌کنیم اما به کلاس اضافه نکردیم چون context دیتابیس ندارند.

def fmt_panel_quick_stats(panel_name: str, stats: dict, lang_code: str) -> str:
    return f"*{escape_markdown(panel_name)}*\n\nمصرف: {stats}" 

def fmt_user_payment_history(payments: list, user_name: str, page: int, lang_code: str) -> str:
    return "تاریخچه پرداخت..." 

def fmt_registered_birthday_info(user_data: dict, lang_code: str) -> str:
    return "تولد..."

def fmt_user_usage_history(history: list, user_name: str, lang_code: str) -> str:
    return "تاریخچه مصرف..."