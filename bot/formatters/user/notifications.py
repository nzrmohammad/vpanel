# bot/formatters/user/notifications.py

from bot.utils.formatters import escape_markdown, format_daily_usage

class NotificationFormatter:
    
    @staticmethod
    def nightly_report(user_data: dict, daily_usage: dict, type_flags_map: dict = None) -> str:
        """
        تولید گزارش شبانه با فرمت دقیق و تفکیک شده.
        پرچم‌ها از سیستم (type_flags_map) یا دیتای پنل خوانده می‌شوند.
        """
        if type_flags_map is None: type_flags_map = {}
        
        name = escape_markdown(user_data.get('name', 'User'))
        breakdown = user_data.get('breakdown', {})
        
        # دیکشنری برای ذخیره مجموع هر نوع پنل برای گروه‌بندی
        # کلید گروه‌بندی: "پرچم" (Flag) است تا پنل‌های هم‌پرچم تجمیع شوند.
        # ساختار: '🇫🇷': {'limit': 100, 'used': 20, ...}
        stats_by_flag = {}

        total_limit_all = 0.0
        total_used_all = 0.0
        
        # 1. پردازش داده‌های کلی و تجمیع بر اساس پرچم
        for p_uuid, p_info in breakdown.items():
            p_type = p_info.get('type', 'unknown')
            data = p_info.get('data', {})
            
            # اولویت پرچم: 1. دیتای خود پنل 2. مپینگ سیستم 3. پیش‌فرض ساده
            flag = data.get('flag') 
            if not flag:
                flag = type_flags_map.get(p_type, '🏳️')
            
            l = float(data.get('usage_limit_GB', 0) or 0)
            u = float(data.get('current_usage_GB', 0) or 0)
            
            if flag not in stats_by_flag:
                stats_by_flag[flag] = {'limit': 0.0, 'used': 0.0}

            stats_by_flag[flag]['limit'] += l
            stats_by_flag[flag]['used'] += u
            
            total_limit_all += l
            total_used_all += u

        total_remain_all = max(0, total_limit_all - total_used_all)
        total_daily_all = sum(daily_usage.values())

        lines = []
        
        # هدر
        lines.append(f"👤 اکانت : *{name}*")
        
        # بخش ۱: حجم کل
        lines.append(f"📊 حجم‌کل : {total_limit_all:.2f} GB")
        for flag, info in stats_by_flag.items():
            if info['limit'] > 0:
                lines.append(f"{flag} : {info['limit']:.2f} GB")
        
        # بخش ۲: حجم مصرف شده
        lines.append(f"🔥 حجم‌مصرف شده : {total_used_all:.2f} GB")
        for flag, info in stats_by_flag.items():
            if info['used'] > 0:
                lines.append(f"{flag} : {info['used']:.2f} GB")

        # بخش ۳: حجم باقی‌مانده
        lines.append(f"📥 حجم‌باقی‌مانده : {total_remain_all:.2f} GB")
        for flag, info in stats_by_flag.items():
            remain = max(0, info['limit'] - info['used'])
            if info['limit'] > 0:
                lines.append(f"{flag} : {remain:.2f} GB")

        # بخش ۴: مصرف امروز (daily_usage کلیدش نوع پنل است، باید به پرچم تبدیل شود)
        lines.append(f"⚡️ حجم مصرف شده امروز:")
        
        # تبدیل daily_usage (که بر اساس تایپ است) به گروه‌بندی پرچمی
        daily_by_flag = {}
        for d_type, d_val in daily_usage.items():
            # تمام مقادیر را جمع می‌کنیم (حتی صفرها)
            flag = type_flags_map.get(d_type, '🏳️')
            daily_by_flag[flag] = daily_by_flag.get(flag, 0.0) + d_val

        # تغییر کلیدی: پیمایش روی تمام پرچم‌هایی که کاربر دارد (stats_by_flag)
        # این باعث می‌شود حتی اگر مصرف امروز 0 باشد، پرچم نمایش داده شود.
        if stats_by_flag:
            for flag in stats_by_flag.keys():
                val = daily_by_flag.get(flag, 0.0)
                lines.append(f"{flag} : {format_daily_usage(val)}")
        else:
             # حالت بسیار نادر که کاربر هیچ سرویسی ندارد
             lines.append("   \(بدون سرویس\)")

        # بخش ۵: انقضا
        expire_days = user_data.get('remaining_days')
        if expire_days is not None:
            # نمایش عدد داخل Code Block برای جلوگیری از بهم ریختگی اعداد منفی
            lines.append(f"📅 انقضا : {expire_days} روز")
        else:
            lines.append(f"📅 انقضا : نامحدود")

        lines.append("") 
        lines.append(f"⚡️ مجموع کل مصرف امروز : {format_daily_usage(total_daily_all)}")

        return "\n".join(lines)