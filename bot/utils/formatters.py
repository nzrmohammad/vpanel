# bot/utils/formatters.py
import re
import uuid
import csv
from datetime import datetime, date
# اگر فایل کانفیگ شما رنگ‌ها را ندارد، می‌توانید خط زیر را کامنت کنید
from bot.config import PROGRESS_COLORS 

# ---------------------------------------------------------
# توابع فرمت‌دهی متن و اعداد
# ---------------------------------------------------------

def escape_markdown(text: str) -> str:
    """ایمن‌سازی متن برای پروتکل MarkdownV2 تلگرام"""
    text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def bytes_to_gb(bytes_value: int) -> float:
    """تبدیل بایت به گیگابایت (عدد خام)"""
    if not bytes_value: return 0.0
    return round(bytes_value / (1024**3), 2)

def format_volume(gb: float) -> str:
    """فرمت حجم به گیگابایت برای نمایش (مثلاً: 10.5 GB یا 100 GB)"""
    if gb is None: return "0 GB"
    val = float(gb)
    # اگر عدد صحیح است (مثلاً 10.0)، اعشار را حذف کن
    num_str = f"{int(val)}" if val.is_integer() else f"{val:.2f}"
    return f"{num_str} GB"

# نام جایگزین برای سازگاری با کدهای قدیمی
format_usage = format_volume 

def format_daily_usage(gb: float) -> str:
    """فرمت هوشمند مصرف روزانه (زیر ۱ گیگ را به مگابایت تبدیل می‌کند)"""
    if gb is None: return "0 MB"
    if gb < 1: 
        return f"{gb * 1024:.0f} MB"
    return f"{gb:.2f} GB"

def format_price(amount: float) -> str:
    """فرمت قیمت به تومان با جداکننده کاما (مثلاً: 10,000 تومان)"""
    try:
        return "{:,.0f} تومان".format(float(amount))
    except (ValueError, TypeError):
        return "0 تومان"
    
def format_gb_ltr(value):
    """
    تبدیل عدد به فرمت LTR برای نمایش صحیح در متن فارسی.
    مثال: 8.68 -> ‎8.68 GB (با حفظ ترتیب صحیح)
    """
    if value is None:
        value = 0
    
    # \u200e کاراکتر نامرئی LTR Mark است
    # باعث می‌شود عدد و واحد GB به هم بچسبند و در متن فارسی جابجا نشوند
    return f"\u200e{float(value):.2f} GB"

# نام جایگزین برای سازگاری با کدهای قدیمی
format_currency = format_price

def format_date(dt) -> str:
    """فرمت کردن تاریخ به شمسی (همراه با ساعت)"""
    # ایمپورت داخلی برای جلوگیری از مشکل Circular Import
    from bot.utils.date_helpers import to_shamsi
    return to_shamsi(dt, include_time=True)

def get_status_emoji(is_active: bool) -> str:
    """دریافت ایموجی وضعیت (✅ یا ❌)"""
    return "✅" if is_active else "❌"

# ---------------------------------------------------------
# توابع گرافیکی و ابزارها
# ---------------------------------------------------------

def create_progress_bar(percent: float, length: int = 16) -> str:
    """خروجی: 🔴 88% ███████░░░ (قسمت پر در سمت چپِ نوار)"""
    percent = max(0, min(100, percent))
    
    if percent < 60: color = "🟢"
    elif percent < 85: color = "🟡"
    else: color = "🔴"
        
    filled = int(percent / 100 * length)
    
    bar = ('█' * filled) + ('░' * (length - filled))
    
    return f"\u200f{color} `{bar} {int(percent)}%`"

def json_serializer(obj):
    """تابع کمکی برای تبدیل آبجکت‌های datetime و UUID به رشته در JSON"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def write_csv_sync(filepath, users_data):
    """
    ذخیره لیست کاربران در فایل CSV (برای استفاده در ترد جداگانه)
    """
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['UserID', 'Username', 'Name', 'Wallet Balance', 'Active Services', 'Referral Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(users_data)