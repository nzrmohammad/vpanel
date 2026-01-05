# bot/formatters/user/services.py
from datetime import datetime
from bot.language import get_string
from bot.utils.formatters import escape_markdown, format_price, format_volume

class ServiceFormatter:

    @staticmethod
    def plan_list(plans: list, lang_code: str) -> str:
        if not plans:
            return escape_markdown(get_string("fmt_plans_none_in_category", lang_code))
        
        lines = [f"*{escape_markdown(get_string('fmt_plans_title', lang_code))}*", "`────────────────────`"]

        for plan in plans:
            total = plan.get('total_volume') or plan.get('volume_gb')
            lines.append(f"*{escape_markdown(plan.get('name'))}*")
            lines.append(f"📦 حجم: {format_volume(total)}")
            lines.append(f"⏳ مدت: {plan.get('days', 0)} روز")
            lines.append(f"💰 قیمت: {format_price(plan.get('price', 0))}")
            lines.append("`────────────────────`")

        lines.append(f"\n{escape_markdown(get_string('fmt_plans_footer_contact_admin', lang_code))}")
        return "\n".join(lines)

    @staticmethod
    def format_plan_btn(plan: dict, user_balance: float) -> str:
        """متن دکمه شیشه‌ای پلن"""
        raw_vol = plan.get('volume_gb') or plan.get('total_volume') or 0
        name = plan.get('name', 'General').replace("سرویس", "").strip()
        days = f"{plan.get('days', 0)}d" 
        price_val = plan.get('price', 0)
        status = "✅" if user_balance >= price_val else "❌"
        
        return f"{name} » {float(raw_vol):g}GB » {days} » {int(price_val):,} {status}"

    @staticmethod
    def new_service_preview(plan, cat_emoji) -> str:
        """پیش‌نمایش خرید سرویس جدید"""
        name = escape_markdown(plan['name'])
        display_name = name if cat_emoji in plan['name'] else f"{name} {cat_emoji}"
        
        return (
            "🔍 *پیش‌نمایش خرید سرویس جدید*\n"
            "──────────────────\n"
            "پلن انتخابی:\n"
            f"{display_name}\n"
            f"📦 {format_volume(plan['volume_gb'])} \| ⏳ {plan['days']} روز\n\n"
            f"💰 مبلغ: {format_price(plan['price'])}\n"
            "──────────────────\n"
            "❓ آیا از ایجاد سرویس جدید اطمینان دارید؟"
        )

    @staticmethod
    def renewal_preview(current_stats, plan, cat_emoji) -> str:
        """پیش‌نمایش تمدید"""
        # محاسبه مقادیر فعلی
        limit = current_stats.get('traffic_limit', 0)
        used = current_stats.get('traffic_used', 0)
        curr_gb = max(0.0, limit - used)
        
        # محاسبه روز باقیمانده
        curr_days = 0
        expire = current_stats.get('expire_date')
        if expire:
            now = datetime.now()
            # هندل کردن timestamp یا datetime
            if isinstance(expire, (int, float)):
                if expire > 1000000000:
                     expire = datetime.fromtimestamp(expire)
            if isinstance(expire, datetime) and expire.replace(tzinfo=None) > now:
                curr_days = (expire.replace(tzinfo=None) - now).days

        # مقادیر جدید
        add_gb = plan['volume_gb']
        add_days = plan['days']
        total_gb = curr_gb + add_gb
        total_days = curr_days + add_days

        def fmt(n): return f"{int(n)}" if n == int(n) else f"{n:.1f}"

        display_name = escape_markdown(plan['name'])
        if cat_emoji and cat_emoji not in plan['name']:
            display_name += f" {cat_emoji}"

        return (
            "🔄 *پیش‌نمایش تمدید سرویس*\n"
            "➖➖➖➖➖➖➖➖\n"
            "🏷 *پلن انتخابی*\n"
            f"{display_name}\n"
            f"📊 {format_volume(add_gb)}\n"
            f"⏳ {add_days} Day\n"
            "➖➖➖➖➖➖➖➖\n"
            "📦 *تغییرات حجم*\n"
            f"{fmt(curr_gb)}GB ➔ \+{fmt(add_gb)} GB ➔ *{fmt(total_gb)} GB*\n"
            "⏳ *تغییرات زمان*\n"
            f"{curr_days} ➔ \+{add_days} ➔ *{total_days}*\n"
            "➖➖➖➖➖\n"
            f"💰 *مبلغ قابل پرداخت :* {format_price(plan['price'])}\n"
            "❓ آیا عملیات تایید است؟"
        )