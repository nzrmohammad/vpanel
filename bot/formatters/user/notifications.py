# bot/formatters/user/notifications.py
from datetime import datetime
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

        lines = []
        
        lines.append(f"👤 اکانت : *{name}*")
        
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

        # نمایش مصرف روزانه فقط به صورت تفکیک شده (با پرچم)
        if stats_by_flag:
            for flag in stats_by_flag.keys():
                val = daily_by_flag.get(flag, 0.0)
                formatted_val = format_daily_usage(val).replace('.', '\\.')
                lines.append(f"{flag} : {formatted_val}")
        else:
             lines.append("   \\(بدون سرویس\\)")

        # اصلاح بخش انقضا: محاسبه روزهای باقی‌مانده از روی timestamp
        expire_ts = user_data.get('expire')
        if expire_ts:
            try:
                # تبدیل timestamp به datetime
                if isinstance(expire_ts, (int, float)):
                    expire_dt = datetime.fromtimestamp(expire_ts)
                else:
                    expire_dt = expire_ts # فرض بر اینکه شاید خودش datetime باشد

                now = datetime.now()
                # محاسبه اختلاف روز
                remaining_days = (expire_dt - now).days
                
                if remaining_days < 0:
                    lines.append(f"📅 انقضا : منقضی شده")
                else:
                    lines.append(f"📅 انقضا : {esc_num(remaining_days)} روز")
            except Exception:
                # در صورت خطا در تبدیل تاریخ
                lines.append(f"📅 انقضا : نامحدود")
        else:
            lines.append(f"📅 انقضا : نامحدود")

        return "\n".join(lines)