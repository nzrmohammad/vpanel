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
BOT_DOMAIN = os.getenv("BOT_DOMAIN")

TELEGRAM_FILE_SIZE_LIMIT_BYTES = 50 * 1024 * 1024
API_TIMEOUT = 45
API_RETRY_COUNT = 3

TEHRAN_TZ = pytz.timezone("Asia/Tehran")
PAGE_SIZE = 35

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
