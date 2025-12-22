# bot/utils/parsers.py

import re
from typing import Optional, Dict
import re

# ریجکس برای چک کردن صحت ساختار UUID
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

def validate_uuid(uuid_str: str) -> bool:
    """بررسی اینکه آیا رشته ورودی یک UUID معتبر است یا خیر"""
    if not uuid_str:
        return False
    return bool(_UUID_RE.match(uuid_str.strip()))

def parse_user_agent(user_agent: str) -> Optional[Dict[str, Optional[str]]]:
    """
    تحلیل رشته User-Agent برای تشخیص نام اپلیکیشن (کلاینت) و سیستم‌عامل کاربر.
    """
    if not user_agent or "TelegramBot" in user_agent:
        return None
    
    # الگوهای شناسایی کلاینت‌های مختلف V2Ray
    CLIENT_PATTERNS = [
        {"regex": re.compile(r"v2rayNG/([\d.]+)"), "extractor": lambda m: {"client": "v2rayNG", "version": m.group(1), "os": "Android"}},
        {"regex": re.compile(r"v2rayN/([\d.]+)"), "extractor": lambda m: {"client": "v2rayN", "version": m.group(1), "os": "Windows"}},
        {"regex": re.compile(r"HiddifyNextX?/([\d.]+)\s+\((\w+)\)"), "extractor": lambda m: {"client": "Hiddify", "version": m.group(1), "os": m.group(2).capitalize()}},
        {"regex": re.compile(r"^(Happ)/([\d.]+)(?:/(\w+))?"), "extractor": lambda m: {"client": "Happ", "version": m.group(2), "os": m.group(3).capitalize() if m.group(3) else "Unknown"}},
        {"regex": re.compile(r"Shadowrocket/([\d.]+)"), "extractor": lambda m: {"client": "Shadowrocket", "version": m.group(1), "os": "iOS"}},
        {"regex": re.compile(r"^(NekoBox)/(\w+)/([\d.]+)"), "extractor": lambda m: {"client": "NekoBox", "version": m.group(3), "os": m.group(2).upper()}},
        {"regex": re.compile(r"^(V2Box)/([\d.]+)"), "extractor": lambda m: {"client": "V2Box", "version": m.group(2), "os": "Unknown"}},
        {"regex": re.compile(r"Streisand/([\d.]+)"), "extractor": lambda m: {"client": "Streisand", "version": m.group(1), "os": "iOS"}},
    ]

    for item in CLIENT_PATTERNS:
        match = item["regex"].search(user_agent)
        if match:
            return item["extractor"](match)

    # اگر کلاینت در لیست بالا نبود، بخش اول یوزر ایجنت را برمی‌گرداند
    generic_client = user_agent.split('/')[0].split(' ')[0]
    return {"client": generic_client, "os": "Unknown", "version": None}

def extract_country_code_from_flag(text: str) -> str:
    """
    تبدیل ایموجی پرچم به کد دو حرفی کشور (مثلاً 🇩🇪 به de).
    اگر ورودی پرچم نباشد، همان متن را کوچک شده برمی‌گرداند.
    """
    text = text.strip()
    
    # پرچم‌ها در واقع ترکیبی از دو کاراکتر Regional Indicator هستند
    if len(text) == 2:
        if all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in text):
            # محاسبه کد حروف انگلیسی از روی کدهای یونیکد ریجنال
            code = "".join([chr(ord(c) - 127397) for c in text])
            return code.lower()
            
    return text.lower()

def parse_volume_string(volume_str: str) -> int:
    """
    استخراج عدد از رشته‌های حجمی (مثلاً از '10 GB' عدد 10 را برمی‌گرداند).
    """
    if not isinstance(volume_str, str):
        return 0
    numbers = re.findall(r'\d+', volume_str)
    return int(numbers[0]) if numbers else 0