# bot/utils/formatters.py
import re
from bot.config import PROGRESS_COLORS

def bytes_to_gb(bytes_value: int) -> float:
    """تبدیل بایت به گیگابایت با دقت ۲ رقم اعشار"""
    if not bytes_value: return 0.0
    return round(bytes_value / (1024**3), 2)

def format_usage(usage_gb: float) -> str:
    """فرمت کردن حجم به گیگابایت یا مگابایت"""
    if usage_gb is None: return "0 MB"
    if usage_gb < 1: return f"{usage_gb * 1024:.0f} MB"
    return f"{usage_gb:.2f} GB"

def format_daily_usage(gb: float) -> str:
    """فرمت کردن مصرف روزانه"""
    return format_usage(gb)

def format_currency(amount) -> str:
    """فرمت کردن مبالغ پولی با جداکننده کاما"""
    try: return f"{int(amount):,}"
    except (ValueError, TypeError): return "0"

def format_date(dt) -> str:
    """فرمت کردن تاریخ (استفاده از تابع مبدل شمسی)"""
    from .date_helpers import to_shamsi
    return to_shamsi(dt, include_time=True)

def get_status_emoji(is_active: bool) -> str:
    """نمایش ایموجی وضعیت فعال یا غیرفعال"""
    return "✅" if is_active else "❌"

def escape_markdown(text: str) -> str:
    """ایمن‌سازی متن برای پروتکل MarkdownV2 تلگرام"""
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def create_progress_bar(percent: float, length: int = 16) -> str:
    """خروجی: 🔴 88% ███████░░░ (قسمت پر در سمت چپِ نوار)"""
    percent = max(0, min(100, percent))
    
    # تعیین رنگ
    if percent < 60: color = "🟢"
    elif percent < 85: color = "🟡"
    else: color = "🔴"
        
    filled = int(percent / 100 * length)
    
    # جابه‌جایی: ابتدا قسمت پر (█) و سپس قسمت خالی (░)
    bar = ('█' * filled) + ('░' * (length - filled))
    
    # چیدمان: عدد درصد را هم قبل از نوار (bar) قرار دادم تا در کنار قسمت پر باشد
    # خروجی نهایی داخل کدبلاک: "88% ███░░"
    return f"\u200f{color} `{bar} {int(percent)}%`"