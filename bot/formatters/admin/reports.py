# bot/formatters/admin/reports.py
import time
from bot.utils.formatters import escape_markdown, format_price, format_volume

class AdminReportFormatter:

    @staticmethod
    def purchase_log(data: dict) -> str:
        """گزارش خرید برای کانال لاگ ادمین"""
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
    def daily_server_stats(users_info: list) -> str:
        """گزارش جامع وضعیت سرور (شبانه)"""
        total_users = len(users_info)
        active_users = sum(1 for u in users_info if u.get('enable', True))
        
        total_used = sum(u.get('current_usage_GB', 0) for u in users_info)
        total_limit = sum(u.get('usage_limit_GB', 0) for u in users_info)
        
        expired_count = 0
        expiring_soon_count = 0
        now_ts = time.time()
        
        # محاسبه منقضی‌ها
        for u in users_info:
            expire_ts = u.get('expire')
            if expire_ts:
                try:
                    expire_ts = float(expire_ts)
                    if expire_ts < now_ts:
                        expired_count += 1
                    elif (expire_ts - now_ts) < (3 * 86400): # کمتر از 3 روز
                        expiring_soon_count += 1
                except: pass

        return (
            f"📊 *آمار کلی سرور*\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"👥 کل کاربران: `{total_users}`\n"
            f"✅ فعال: `{active_users}`\n"
            f"❌ غیرفعال: `{total_users - active_users}`\n"
            f"\n"
            f"📉 مصرف کل: `{total_used:,.2f} GB`\n"
            f"📈 حجم کل مجاز: `{total_limit:,.2f} GB`\n"
            f"\n"
            f"⚠️ منقضی شده: `{expired_count}`\n"
            f"⏳ انقضای نزدیک (۳ روز): `{expiring_soon_count}`\n"
        )

    @staticmethod
    def weekly_top_consumers(top_users: list) -> str:
        """گزارش پرمصرف‌ترین کاربران"""
        if not top_users:
            return "📊 *گزارش هفتگی*\n\nهیچ مصرفی در هفته گذشته ثبت نشده است."
            
        lines = ["📊 *برترین مصرف‌کنندگان هفته*", "➖➖➖➖➖➖➖➖"]
        
        for idx, user in enumerate(top_users[:15], 1):
            name = escape_markdown(user.get('name', 'Unknown'))
            usage = user.get('total_usage', 0)
            lines.append(f"{idx}\\. {name}: `{usage:.2f} GB`")
            
        return "\n".join(lines)