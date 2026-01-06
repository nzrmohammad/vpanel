from bot.utils.formatters import escape_markdown, format_gb_ltr, format_daily_usage
from datetime import datetime

class NotificationFormatter:
    
    @staticmethod
    def nightly_report(user_data: dict, daily_usage: dict, type_flags_map: dict = None) -> str:
        """
        تولید گزارش شبانه به صورت تفکیک شده (هر سرویس یک بخش مجزا)
        """
        if type_flags_map is None: type_flags_map = {}
        
        name = escape_markdown(user_data.get('name', 'User'))
        breakdown = user_data.get('breakdown', {})
        
        # تابع کمکی برای اسکیپ کردن اعداد در MarkdownV2
        def esc(val):
            return str(val).replace('.', '\\.').replace('-', '\\-')

        # شروع ساخت متن گزارش
        lines = []
        
        # 1. نام اکانت و سپس خط جداکننده (طبق درخواست شما)
        lines.append(f"👤 اکانت : *{name}*")
        lines.append("──────────────────")
        
        if not breakdown:
            lines.append("❌ هیچ سرویس فعالی یافت نشد\\.")
            return "\n".join(lines)

        # مرتب‌سازی سرویس‌ها
        sorted_items = sorted(breakdown.items(), key=lambda x: x[0])

        for p_key, p_info in sorted_items:
            p_type = p_info.get('type', 'unknown')
            data = p_info.get('data', {})
            
            # --- 1. تعیین پرچم ---
            flag = data.get('flag')
            if not flag:
                flag = type_flags_map.get(p_type, '🏳️')
            
            # --- 2. استخراج اعداد ---
            limit = float(data.get('usage_limit_GB', 0) or 0)
            used = float(data.get('current_usage_GB', 0) or 0)
            remain = max(0, limit - used)
            
            # مصرف امروز
            today_usage = daily_usage.get(p_type, 0.0)
            
            # --- 3. محاسبات انقضا ---
            expire_str = "نامحدود"
            expire_val = data.get('expire')
            pkg_days = data.get('package_days')
            start_date = data.get('start_date')

            if isinstance(expire_val, (int, float)) and expire_val > 100_000_000:
                try:
                    dt = datetime.fromtimestamp(expire_val)
                    diff = (dt - datetime.now()).days
                    if diff < 0:
                        expire_str = "منقضی شده"
                    else:
                        expire_str = f"{diff} روز"
                except: pass
            elif pkg_days is not None:
                try:
                    if start_date:
                        start = datetime.strptime(str(start_date).split(' ')[0], "%Y-%m-%d")
                        passed = (datetime.now() - start).days
                        rem = int(pkg_days) - passed
                        expire_str = f"{max(0, rem)} روز"
                    else:
                        expire_str = f"{int(pkg_days)} روز"
                except:
                    expire_str = f"{int(pkg_days)} روز"

            # --- 4. ساخت بلوک نمایشی ---
            lines.append(f"سرور {flag}")
            
            lines.append(f"📊 حجم‌کل : {esc(format_gb_ltr(limit))}")
            lines.append(f"🔥 حجم‌مصرف شده : {esc(format_gb_ltr(used))}")
            lines.append(f"📥 حجم‌باقی‌مانده : {esc(format_gb_ltr(remain))}")
            
            # === اصلاح نمایش در موبایل ===
            raw_daily = format_daily_usage(today_usage)
            daily_fmt = f"\u200e{raw_daily}".replace('.', '\\.')
            
            lines.append(f"⚡️ حجم مصرف شده امروز : {daily_fmt}")
            
            lines.append(f"📅 انقضا : {esc(expire_str)}")
            
            lines.append("──────────────────")

        return "\n".join(lines)