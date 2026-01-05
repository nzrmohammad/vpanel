from bot.utils.formatters import escape_markdown, format_daily_usage

class NotificationFormatter:
    
    @staticmethod
    def nightly_report(user_data: dict, daily_usage: dict, type_flags_map: dict = None) -> str:
        """
        تولید گزارش شبانه با فرمت دقیق و تفکیک شده.
        """
        if type_flags_map is None: type_flags_map = {}
        
        name = escape_markdown(user_data.get('name', 'User'))
        breakdown = user_data.get('breakdown', {})
        
        # تابع کمکی داخلی برای اسکیپ کردن اعداد در MarkdownV2
        # نقطه و منفی را به فرمت قابل قبول تلگرام تبدیل می‌کند
        def esc_num(val):
            return str(val).replace('.', '\\.').replace('-', '\\-')

        stats_by_flag = {}
        total_limit_all = 0.0
        total_used_all = 0.0
        
        for p_uuid, p_info in breakdown.items():
            p_type = p_info.get('type', 'unknown')
            data = p_info.get('data', {})
            
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
        
        lines.append(f"👤 اکانت : *{name}*")
        
        # اصلاح: استفاده از replace برای اسکیپ کردن نقطه در اعداد اعشاری
        lines.append(f"📊 حجم‌کل : {esc_num(f'{total_limit_all:.2f}')} GB")
        for flag, info in stats_by_flag.items():
            if info['limit'] > 0:
                lines.append(f"{flag} : {esc_num(f'{info['limit']:.2f}')} GB")
        
        lines.append(f"🔥 حجم‌مصرف شده : {esc_num(f'{total_used_all:.2f}')} GB")
        for flag, info in stats_by_flag.items():
            if info['used'] > 0:
                lines.append(f"{flag} : {esc_num(f'{info['used']:.2f}')} GB")

        lines.append(f"📥 حجم‌باقی‌مانده : {esc_num(f'{total_remain_all:.2f}')} GB")
        for flag, info in stats_by_flag.items():
            remain = max(0, info['limit'] - info['used'])
            if info['limit'] > 0:
                lines.append(f"{flag} : {esc_num(f'{remain:.2f}')} GB")

        lines.append(f"⚡️ حجم مصرف شده امروز:")
        
        daily_by_flag = {}
        for d_type, d_val in daily_usage.items():
            flag = type_flags_map.get(d_type, '🏳️')
            daily_by_flag[flag] = daily_by_flag.get(flag, 0.0) + d_val

        if stats_by_flag:
            for flag in stats_by_flag.keys():
                val = daily_by_flag.get(flag, 0.0)
                # فرض بر این است که format_daily_usage خودش خروجی امن می‌دهد
                # اما اگر آن تابع هم نقطه دارد، باید آن را هم اسکیپ کنید:
                formatted_val = format_daily_usage(val).replace('.', '\\.')
                lines.append(f"{flag} : {formatted_val}")
        else:
             # اصلاح: دبل بک‌اسلش برای ارسال صحیح کاراکتر اسکیپ شده
             lines.append("   \\(بدون سرویس\\)")

        expire_days = user_data.get('remaining_days')
        if expire_days is not None:
            # اصلاح: اسکیپ کردن علامت منفی احتمالی
            lines.append(f"📅 انقضا : {esc_num(expire_days)} روز")
        else:
            lines.append(f"📅 انقضا : نامحدود")

        lines.append("") 
        
        # اصلاح نهایی برای مجموع مصرف امروز
        final_daily = format_daily_usage(total_daily_all).replace('.', '\\.')
        lines.append(f"⚡️ مجموع کل مصرف امروز : {final_daily}")

        return "\n".join(lines)