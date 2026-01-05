# bot/formatters/admin/users.py
from bot.utils.formatters import escape_markdown, format_volume, get_status_emoji
from bot.utils.date_helpers import to_shamsi, days_until_next_birthday

class AdminUserFormatter:
    
    @staticmethod
    def user_details(user_data: dict, panel_name: str) -> str:
        """نمایش ریز جزئیات کاربر (کانفیگ)"""
        # استفاده از .get برای جلوگیری از ارور
        name = escape_markdown(user_data.get('name', "بی‌نام"))
        uuid_str = user_data.get('uuid', "---")
        is_active = user_data.get('is_active', True)
        status = "🟢 فعال" if is_active else "🔴 غیرفعال"
        
        # تاریخ اتصال
        last_online = user_data.get('last_online') or user_data.get('online_at')
        if last_online:
            online_str = f"🕒 {to_shamsi(last_online, include_time=True)}"
        else:
            online_str = "⚫️ آفلاین"

        # مصرف
        usage = user_data.get('current_usage_GB', 0)
        limit = user_data.get('usage_limit_GB', 0)
        usage_str = f"{format_volume(usage)} / {format_volume(limit)}"
        
        # انقضا
        expire_days = user_data.get('expire_days')
        if expire_days is None:
             expire_days = user_data.get('remaining_days')
        
        expire_str = f"{expire_days} روز" if expire_days is not None else "نامحدود"

        return (
            f"👤 <b>اطلاعات کاربر در {escape_markdown(panel_name)}</b>\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"🔖 <b>نام:</b> {name}\n"
            f"🔑 <b>UUID:</b> <code>{uuid_str}</code>\n"
            f"📡 <b>وضعیت:</b> {status}\n"
            f"🔋 <b>آخرین اتصال:</b> {online_str}\n"
            f"📊 <b>مصرف:</b> {usage_str}\n"
            f"⏳ <b>اعتبار:</b> {expire_str}\n"
        )

    @staticmethod
    def user_list_row(user: dict, index: int) -> str:
        """یک خط خلاصه برای لیست کاربران"""
        is_active = user.get('is_active', False)
        status_icon = "✅" if is_active else "❌"
        name = escape_markdown(user.get('name') or user.get('first_name') or 'Unknown')
        
        # نمایش موجودی یا مصرف بسته به نوع آبجکت
        if 'wallet_balance' in user:
            balance = user.get('wallet_balance', 0)
            extra_info = f"{int(balance):,} T"
        else:
            usage = user.get('current_usage_GB', 0)
            extra_info = f"{usage:.1f}GB"

        return f"{index}. {status_icon} <b>{name}</b> | {extra_info}"

    @staticmethod
    def birthdays_list(users: list, page: int, total_count: int, page_size: int = 15) -> str:
        """لیست تولد کاربران"""
        title = "🎂 لیست تولد کاربران (مرتب شده بر اساس ماه)"
        if not users:
            return f"<b>{title}</b>\n\nهیچ کاربری تاریخ تولد خود را ثبت نکرده است."
        
        total_pages = (total_count + page_size - 1) // page_size
        header = f"<b>{title}</b>\n(صفحه {page + 1} از {total_pages} | کل: {total_count})\n➖➖➖➖➖➖➖➖"
        lines = [header]
        
        for user in users:
            name = escape_markdown(user.get('first_name') or user.get('name') or "بی‌نام")
            # برای HTML باید تگ‌ها را اسکیپ کنیم (متفاوت از Markdown)
            name = name.replace('<', '&lt;').replace('>', '&gt;')
            
            birthday = user.get('birthday')
            date_str = to_shamsi(birthday)
            days = days_until_next_birthday(birthday)
            
            days_str = "امروز! 🎉" if days == 0 else (f"{days} روز" if days is not None else "نامشخص")
            
            lines.append(f"🎂 <b>{name}</b> | {date_str} | {days_str}")
            
        return "\n".join(lines)