# bot/formatters/admin/reports.py
import time
from collections import defaultdict
from bot.utils.formatters import escape_markdown, format_price, format_daily_usage

class AdminReportFormatter:

    @staticmethod
    def purchase_log(data: dict) -> str:
        """گزارش خرید"""
        return (
            f"🛒 <b>گزارش خرید جدید</b>\n"
            f"👤 کاربر : {escape_markdown(data.get('user_name', 'Unknown'))} (<code>{data.get('user_id')}</code>)\n"
            f"🔑 سرویس : <code>{escape_markdown(data.get('service_name'))}</code>\n"
            f"🏷 نوع : {data.get('type_text')}\n"
            f"📦 پلن : {escape_markdown(data.get('plan_name'))} ({data.get('limit_gb')}GB - {data.get('days')} روز)\n"
            f"💰 مبلغ : {format_price(data.get('price', 0))}\n"
            f"💳 <b>مانده کیف پول : {format_price(data.get('wallet_balance', 0))}</b>\n"
            f"🖥 <b>سرور : {escape_markdown(data.get('server_name'))}</b>\n"
            f"شناسه : <code>{data.get('uuid')}</code>\n"
            f"📅 تاریخ : {data.get('date_str')}"
        )

    @staticmethod
    def daily_server_stats(users_info: list, stats_data: dict = None) -> str:
        """
        گزارش جامع وضعیت سرور (کاملاً داینامیک).
        """
        if not stats_data: stats_data = {}
        
        daily_usage_map = stats_data.get('daily_usage_map', {})
        payments_today = stats_data.get('payments_today', 0)
        new_users_today = stats_data.get('new_users_today', 0)
        timestamp_str = stats_data.get('timestamp_str', '')
        type_flags_map = stats_data.get('type_flags_map', {}) # دریافت پرچم‌های سیستم

        total_accounts = len(users_info)
        active_accounts = sum(1 for u in users_info if u.get('enable', True) and u.get('is_active', True))
        
        # تجمیع مصرف بر اساس پرچم (Flag)
        usage_by_flag = defaultdict(float)
        active_daily_users = []

        for user in users_info:
            uuid = user.get('uuid')
            u_usage_data = daily_usage_map.get(uuid, {})
            
            user_total_daily = 0.0
            # لیست ریز مصرف کاربر برای نمایش جلو نامش
            user_flag_usages = defaultdict(float)
            
            for p_type, usage_val in u_usage_data.items():
                if usage_val > 0:
                    # پیدا کردن پرچم مربوط به این تایپ از سیستم
                    flag = type_flags_map.get(p_type, '🏳️')
                    
                    usage_by_flag[flag] += usage_val
                    user_total_daily += usage_val
                    user_flag_usages[flag] += usage_val

            if user_total_daily > 0.005:
                # ساخت استرینگ ریز مصرف کاربر
                parts = []
                for flag, val in user_flag_usages.items():
                    parts.append(f"{flag} {format_daily_usage(val)}")
                
                active_daily_users.append({
                    'name': user.get('name', 'Unknown'),
                    'total': user_total_daily,
                    'breakdown_str': " \\| ".join(parts)
                })

        total_daily_usage = sum(usage_by_flag.values())
        
        # پیدا کردن قهرمان
        top_user = max(active_daily_users, key=lambda x: x['total']) if active_daily_users else None
        top_user_text = "نداریم"
        if top_user:
            top_user_text = f"{escape_markdown(top_user['name'])} \\({format_daily_usage(top_user['total'])}\\)"

        active_daily_users.sort(key=lambda x: x['name'])

        lines = []
        lines.append(f"👑 *گزارش جامع* {escape_markdown('-')} {escape_markdown(timestamp_str)}")
        lines.append("──────────────────")
        
        # --- خلاصه ---
        lines.append("⚙️ *خلاصه وضعیت کل پنل*")
        lines.append(f"👤 تعداد کل اکانت‌ها : `{total_accounts}`")
        lines.append(f"✅ اکانت‌های فعال : `{active_accounts}`")
        lines.append(f"➕ کاربران جدید امروز : `{new_users_today}`")
        lines.append(f"💳 پرداخت‌های امروز : `{payments_today}`")
        lines.append(f"⚡️ مصرف کل امروز : `{total_daily_usage:.2f} GB`")
        
        # نمایش تفکیکی بر اساس پرچم‌ها
        for flag, val in usage_by_flag.items():
            if val > 0:
                lines.append(f" {flag} : `{val:.2f} GB`")
                
        lines.append(f"🔥 قهرمان امروز : {top_user_text}")
        lines.append("──────────────────")
        
        # --- لیست کاربران ---
        if active_daily_users:
            lines.append("✅ *کاربران فعال امروز و مصرفشان*")
            for u in active_daily_users:
                lines.append(f"👤 {escape_markdown(u['name'])} : {u['breakdown_str']}")
        else:
            lines.append("💤 هیچ کاربری امروز مصرف نداشته است\\.")

        return "\n".join(lines)

    @staticmethod
    def weekly_top_consumers(top_users: list) -> str:
        if not top_users:
            return "📊 *گزارش هفتگی*\n\nهیچ مصرفی در هفته گذشته ثبت نشده است."
        lines = ["📊 *برترین مصرف‌کنندگان هفته*", "➖➖➖➖➖➖➖➖"]
        for idx, user in enumerate(top_users[:15], 1):
            name = escape_markdown(user.get('name', 'Unknown'))
            usage = user.get('total_usage', 0)
            lines.append(f"{idx}\\. {name}: `{usage:.2f} GB`")
        return "\n".join(lines)