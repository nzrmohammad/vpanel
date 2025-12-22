import os
from dotenv import load_dotenv
from datetime import time
import pytz

load_dotenv()

def _parse_admin_ids(raw_ids: str | None) -> set[int]:
    if not raw_ids:
        return set()
    try:
        return {int(admin_id.strip()) for admin_id in raw_ids.split(',')}
    except ValueError:
        print("Warning: ADMIN_IDS environment variable contains non-integer values.")
        return set()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_UUID = os.getenv("ADMIN_UUID")
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS")) or {265455450}
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")

TELEGRAM_FILE_SIZE_LIMIT_BYTES = 50 * 1024 * 1024
API_TIMEOUT = 45
API_RETRY_COUNT = 3

TEHRAN_TZ = pytz.timezone("Asia/Tehran")
DAILY_REPORT_TIME = time(23, 57)
CLEANUP_TIME = time(00, 1)

ADMIN_SUPPORT_CONTACT = os.getenv("ADMIN_SUPPORT_CONTACT", "@Nzrmohammad")
PAGE_SIZE = 35

RANDOM_SERVERS_COUNT = 10

TUTORIAL_LINKS = {
    "android": {
        "v2rayng": "https://telegra.ph/Your-V2rayNG-Tutorial-Link-Here-01-01",
        "hiddify": "https://telegra.ph/Hiddify-08-19",
        "happ": "https://telegra.ph/Happ-08-08-5"
    },
    "windows": {
        "v2rayn": "https://telegra.ph/V2rayN-08-18-2",
        "hiddify": "https://telegra.ph/Hiddify-08-19",
        "happ": "https://telegra.ph/Happ-08-08-5"
    },
    "ios": {
        "streisand": "https://telegra.ph/Your-Streisand-Tutorial-Link-Here-01-01",
        "shadowrocket": "https://telegra.ph/Your-Shadowrocket-Tutorial-Link-Here-01-01",
        "hiddify": "https://telegra.ph/Hiddify-08-19",
        "happ": "https://telegra.ph/Happ-08-08-5"
    }
}

# --- Loyalty Program ---
# دیکشنری برای تعریف پاداش‌ها
# کلید: شماره پرداخت (تمدید)
# مقدار: یک دیکشنری شامل حجم (gb) و روز (days) هدیه
LOYALTY_REWARDS = {
    3: {"gb": 6, "days": 3},  # هدیه در سومین تمدید
    6: {"gb": 12, "days": 6}, # هدیه در ششمین تمدید
    9: {"gb": 18, "days": 9}, # هدیه در دهمین تمدید
    12: {"gb": 24, "days": 12}
}

# --- Traffic Transfer Settings ---
ENABLE_TRAFFIC_TRANSFER = True  # قابلیت را فعال یا غیرفعال می‌کند
MIN_TRANSFER_GB = 1             # حداقل حجم قابل انتقال
MAX_TRANSFER_GB = 20             # حداکثر حجم قابل انتقال
TRANSFER_COOLDOWN_DAYS = 10     # هر کاربر هر چند روز یکبار می‌تواند انتقال دهد

# --- Referral System Settings ---
ENABLE_REFERRAL_SYSTEM = True
REFERRAL_REWARD_GB = 10          # حجم هدیه برای هر معرفی موفق (به گیگابایت)
REFERRAL_REWARD_DAYS = 5        # روز هدیه برای هر معرفی موفق
AMBASSADOR_BADGE_THRESHOLD = 5  # تعداد معرفی لازم برای دریافت نشان سفیر

ACHIEVEMENTS = {
    "vip_friend": {
        "name": "حامی ویژه", "icon": "💎", "points": 1500,
        "description": "این نشان به تمام کاربران VIP به نشانه قدردانی از حمایت ویژه‌شان اهدا می‌شود."
    },
    "legend": {
        "name": "اسطوره", "icon": "🌟", "points": 1000,
        "description": "به کاربرانی که همزمان نشان‌های کهنه‌کار، حامی وفادار و مصرف‌کننده حرفه‌ای را داشته باشند."
    },
    "serial_champion": {
        "name": "قهرمان بی چون و چرا", "icon": "👑", "points": 500,
        "description": "به کاربری که ۸ هفته متوالی عنوان قهرمان هفته را از آن خود کند."
    },
    "collector": {
        "name": "کلکسیونر", "icon": "🗃️", "points": 400,
        "description": "به کاربری که موفق به کسب ۱۰ نشان مختلف شده باشد، اهدا می‌شود."
    },
    "ambassador": {
        "name": "سفیر", "icon": "🤝", "points": 300,
        "description": f"به کاربرانی که بیش از {AMBASSADOR_BADGE_THRESHOLD} نفر را با موفقیت به سرویس دعوت کرده باشند."
    },
    "veteran": {
        "name": "کهنه‌کار", "icon": "🎖️", "points": 250,
        "description": "به کاربرانی که بیش از ۳۶۵ روز از اولین اتصالشان گذشته باشد، اهدا می‌شود."
    },
    "media_partner": {
        "name": "یار رسانه‌ای", "icon": "📣", "points": 200,
        "description": "این نشان توسط ادمین به کاربرانی که به صورت داوطلبانه سرویس را تبلیغ می‌کنند، اهدا می‌شود."
    },
    "support_contributor": {
        "name": "همیار پشتیبانی", "icon": "🛠️", "points": 150,
        "description": "این نشان توسط ادمین به کاربری که یک باگ مهم را گزارش کرده یا بازخورد مفیدی ارائه داده است، اهدا می‌شود."
    },
    "pro_consumer": {
        "name": "مصرف‌کننده حرفه‌ای", "icon": "🔥", "points": 150,
        "description": "به کاربرانی که در یک دوره ۳۰ روزه، بیش از ۲۰۰ گیگابایت ترافیک مصرف کنند."
    },
    "loyal_supporter": {
        "name": "حامی وفادار", "icon": "💖", "points": 100,
        "description": "به کاربرانی که بیش از ۵ بار سرویس خود را تمدید کرده باشند، اهدا می‌شود."
    },
    "weekly_champion": {
        "name": "قهرمان هفته", "icon": "🏆", "points": 60,
        "description": "به کاربری که در گزارش هفتگی، به عنوان پرمصرف‌ترین کاربر هفته معرفی شود."
    },
    "night_owl": {
        "name": "شب‌زنده‌دار", "icon": "🦉", "points": 30,
        "description": "به کاربرانی که بیش از ۵۰٪ ترافیک ماهانه خود را بین ساعت ۰۰:۰۰ تا ۰۶:۰۰ بامداد مصرف کنند."
    },
    "early_bird": {
        "name": "سحرخیز", "icon": "🌅", "points": 30,
        "description": "به کاربرانی که بیش از ۵۰٪ ترافیک هفتگی خود را بین ساعت ۰۶:۰۰ تا ۱۲:۰۰ ظهر مصرف کنند."
    },
    "lucky_one": {
        "name": "خوش‌شانس", "icon": "🍀", "points": 5,
        "description": "این نشان به صورت کاملاً تصادفی به برخی از کاربران اهدا می‌شود!"
    }
}


ENABLE_LUCKY_LOTTERY = True
LUCKY_LOTTERY_BADGE_REQUIREMENT = 20

ACHIEVEMENT_SHOP_ITEMS = {
    "buy_7days":        {"name": "۷ روز", "cost": 150, "days": 7, "target": "all"},
    "buy_30days":       {"name": "۳۰ روز", "cost": 450, "days": 30, "target": "all"},
    
    "buy_de_15gb":      {"name": "۱۵ گیگ (🇩🇪)", "cost": 120, "gb": 15, "target": "de"},
    "buy_de_60gb":      {"name": "۶۰ گیگ (🇩🇪)", "cost": 180, "gb": 60, "target": "de"},
    
    "buy_fr_10gb":      {"name": "۱۰ گیگ (🇫🇷)", "cost": 120, "gb": 10, "target": "fr"},
    "buy_fr_30gb":      {"name": "۳۰ گیگ (🇫🇷)", "cost": 300, "gb": 30, "target": "fr"},

    "buy_tr_10gb":      {"name": "۱۰ گیگ (🇹🇷)", "cost": 120, "gb": 10, "target": "tr"},
    "buy_tr_30gb":      {"name": "۳۰ گیگ (🇹🇷)", "cost": 300, "gb": 30, "target": "tr"},

    "buy_us_15gb":      {"name": "۱۵ گیگ (🇺🇸)", "cost": 150, "gb": 15, "target": "us"},
    "buy_us_25gb":      {"name": "۲۵ گیگ (🇺🇸)", "cost": 220, "gb": 25, "target": "us"},
    "buy_ro_15gb":      {"name": "۱۵ گیگ (🇷🇴)", "cost": 150, "gb": 15, "target": "ro"},
    "buy_ro_25gb":      {"name": "۲۵ گیگ (🇷🇴)", "cost": 220, "gb": 25, "target": "ro"},
    "buy_fi_10gb":      {"name": "۱۰ گیگ (🇫🇮)", "cost": 120, "gb": 10, "target": "fi"},
    "buy_fi_30gb":      {"name": "۳۰ گیگ (🇫🇮)", "cost": 300, "gb": 30, "target": "fi"},

    "buy_lottery_ticket": {"name": "🎟️ بلیط قرعه‌کشی", "cost": 100, "target": "all"},
}

# ✨ قالب‌های دسترسی بر اساس نوع پلن
ACCESS_TEMPLATES = {
    # --- پلن‌های تک کشوره ---
    'de': {
        'has_access_de': True, 'has_access_fr': False, 'has_access_tr': False, 
        'has_access_us': False, 'has_access_ro': False, 'has_access_supp': False
    },
    'fr': {
        'has_access_de': False, 'has_access_fr': True, 'has_access_tr': False, 
        'has_access_us': False, 'has_access_ro': False, 'has_access_supp': False
    },
    'tr': {
        'has_access_de': False, 'has_access_fr': False, 'has_access_tr': True, 
        'has_access_us': False, 'has_access_ro': False, 'has_access_supp': False
    },
    'us': {
        'has_access_de': False, 'has_access_fr': False, 'has_access_tr': False, 
        'has_access_us': True, 'has_access_ro': False, 'has_access_supp': False
    },
    'ro': {
        'has_access_de': False, 'has_access_fr': False, 'has_access_tr': False, 
        'has_access_us': False, 'has_access_ro': True, 'has_access_supp': False
    },
    'fi': {
        'has_access_de': False, 'has_access_fr': False, 'has_access_tr': False, 
        'has_access_us': False, 'has_access_ro': False, 'has_access_supp': True
    },

    # --- پلن ترکیبی (آلمان، فرانسه، ترکیه) ---
    'combined': {
        'has_access_de': True, 'has_access_fr': True, 'has_access_tr': True, 
        'has_access_us': False, 'has_access_ro': False,
        'has_access_supp': False
    },
    
    # --- قالب پیش‌فرض ---
    # اگر پلنی خارج از دسته‌های بالا ساخته شود، همه دسترسی‌ها را فعال می‌کند
    'default': {
        'has_access_de': False, 'has_access_fr': False, 'has_access_tr': False, 
        'has_access_us': False, 'has_access_ro': False, 'has_access_supp': False
    }
}

# --- Emojis & Visuals ---
EMOJIS = {
    "fire": "🔥", "chart": "📊", "warning": "⚠️", "error": "❌",
    "success": "✅", "info": "ℹ️", "key": "🔑", "bell": "🔔",
    "time": "⏰", "calendar": "📅", "money": "💰", "lightning": "⚡",
    "star": "⭐", "rocket": "🚀", "gear": "⚙️", "book": "📖",
    "home": "🏠", "user": "👤", "globe": "🌍", "wifi": "📡",
    "download": "📥", "upload": "📤", "database": "💾",
    "shield": "🛡️", "crown": "👑", "trophy": "🏆",
    "database": "🗂️", "back": "🔙"
}

PROGRESS_COLORS = {
    "safe": "🟢", "warning": "🟡", "danger": "🟠", "critical": "🔴"
}

# --- Logging ---
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
