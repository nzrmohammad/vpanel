# bot/consts.py

class Callback:
    ADMIN_PANEL = "admin:panel"
    USER_MANAGE = "manage"
    WALLET_MAIN = "wallet:main"
    BACK = "back"

# --- ایموجی‌ها و رنگ‌ها ---
EMOJIS = {
    "fire": "🔥", "chart": "📊", "warning": "⚠️", "error": "❌",
    "success": "✅", "info": "ℹ️", "key": "🔑", "bell": "🔔",
    "time": "⏰", "calendar": "📅", "money": "💰", "lightning": "⚡",
    "star": "⭐", "rocket": "🚀", "gear": "⚙️", "book": "📖",
    "home": "🏠", "user": "👤", "globe": "🌍", "wifi": "📡",
    "download": "📥", "upload": "📤", "database": "💾",
    "shield": "🛡️", "crown": "👑", "trophy": "🏆",
    "back": "🔙"
}

PROGRESS_COLORS = {
    "safe": "🟢", "warning": "🟡", "danger": "🟠", "critical": "🔴"
}

# --- سیستم وفاداری ---
LOYALTY_REWARDS = {
    3: {"gb": 6, "days": 3},   # هدیه در سومین تمدید
    6: {"gb": 12, "days": 6},  # هدیه در ششمین تمدید
    9: {"gb": 18, "days": 9},  # هدیه در نهمین تمدید
    12: {"gb": 24, "days": 12} # هدیه در دوازدهمین تمدید
}

# --- آیتم‌های فروشگاه امتیاز ---
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

# --- لیست افتخارات ---
ACHIEVEMENTS = {
    "vip_friend": {
        "name": "حامی ویژه", "icon": "💎", "points": 1500,
        "description": "این نشان به تمام کاربران VIP اهدا می‌شود."
    },
    "legend": {
        "name": "اسطوره", "icon": "🌟", "points": 1000,
        "description": "نشان برای کاربران افسانه‌ای."
    },
    "serial_champion": {
        "name": "قهرمان بی چون و چرا", "icon": "👑", "points": 500,
        "description": "۸ هفته متوالی قهرمان هفته."
    },
    "collector": {
        "name": "کلکسیونر", "icon": "🗃️", "points": 400,
        "description": "کسب ۱۰ نشان مختلف."
    },
    "ambassador": {
        "name": "سفیر", "icon": "🤝", "points": 300,
        "description": "دعوت موفق تعداد زیادی کاربر."
    },
    "veteran": {
        "name": "کهنه‌کار", "icon": "🎖️", "points": 250,
        "description": "عضویت بیش از ۳۶۵ روز."
    },
    "media_partner": {
        "name": "یار رسانه‌ای", "icon": "📣", "points": 200,
        "description": "تبلیغ داوطلبانه سرویس."
    },
    "support_contributor": {
        "name": "همیار پشتیبانی", "icon": "🛠️", "points": 150,
        "description": "گزارش باگ و کمک به پشتیبانی."
    },
    "pro_consumer": {
        "name": "مصرف‌کننده حرفه‌ای", "icon": "🔥", "points": 150,
        "description": "مصرف بیش از ۲۰۰ گیگ در ماه."
    },
    "loyal_supporter": {
        "name": "حامی وفادار", "icon": "💖", "points": 100,
        "description": "بیش از ۵ بار تمدید سرویس."
    },
    "weekly_champion": {
        "name": "قهرمان هفته", "icon": "🏆", "points": 60,
        "description": "پرمصرف‌ترین کاربر هفته."
    },
    "night_owl": {
        "name": "شب‌زنده‌دار", "icon": "🦉", "points": 30,
        "description": "مصرف عمده در ساعات بامداد."
    },
    "early_bird": {
        "name": "سحرخیز", "icon": "🌅", "points": 30,
        "description": "مصرف عمده در ساعات صبح."
    },
    "lucky_one": {
        "name": "خوش‌شانس", "icon": "🍀", "points": 5,
        "description": "اهدای کاملاً تصادفی."
    }
}