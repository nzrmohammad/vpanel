import logging
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telebot.async_telebot import AsyncTeleBot

# تنظیمات و کانفیگ‌ها
try:
    from bot.config import TEHRAN_TZ
except ImportError:
    TEHRAN_TZ = pytz.timezone('Asia/Tehran')

# ایمپورت جاب‌ها (وظایف)
# نکته: مطمئن شوید که فایل‌های مربوطه در پوشه bot/scheduler_jobs وجود دارند
from bot.scheduler_jobs import warnings, reports
# ایمپورت‌های اختیاری (اگر فایل‌هایشان را نساخته‌اید، ارور ندهد)
try:
    from bot.scheduler_jobs import rewards, maintenance, financials
except ImportError:
    rewards = maintenance = financials = None

logger = logging.getLogger(__name__)

class SchedulerManager:
    """
    مدیریت زمان‌بندی وظایف ربات با استفاده از APScheduler
    سازگار با توابع Async و دیتابیس
    """
    def __init__(self, bot: AsyncTeleBot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=TEHRAN_TZ)
        self.running = False

    def start(self):
        """شروع زمان‌بندی‌ها"""
        if self.running:
            return
            
        logger.info("SCHEDULER: Starting up...")

        # -----------------------------------------------------------
        # 1. هشدارها (Warnings)
        # -----------------------------------------------------------
        # چک کردن هشدارها (حجم، انقضا، عدم فعالیت) هر 10 دقیقه
        self.scheduler.add_job(
            warnings.check_and_send_warnings,
            trigger=IntervalTrigger(minutes=10),
            args=[self.bot],
            id="job_warnings",
            replace_existing=True
        )

        # -----------------------------------------------------------
        # 2. گزارش‌های سیستمی (Reports)
        # -----------------------------------------------------------
        if reports:
            # ارسال گزارش شبانه (هم ادمین و هم کاربران)
            self.scheduler.add_job(
                reports.nightly_report,  # نام صحیح تابع
                trigger=CronTrigger(hour=13, minute=31),
                args=[self.bot],
                id="job_nightly_report",
                replace_existing=True
            )

        # -----------------------------------------------------------
        # 3. نگهداری و تعمیرات (Maintenance)
        # -----------------------------------------------------------
        if maintenance:
            # همگام‌سازی کاربران با پنل هر 1 ساعت
            self.scheduler.add_job(
                maintenance.sync_users_with_panels,
                trigger=IntervalTrigger(hours=1),
                args=[self.bot],
                id="job_sync_panels"
            )
            
            # پاکسازی گزارشات قدیمی هر 24 ساعت
            self.scheduler.add_job(
                maintenance.cleanup_old_logs,
                trigger=IntervalTrigger(hours=24),
                args=[],
                id="job_cleanup"
            )

        # شروع موتور زمان‌بندی
        self.scheduler.start()
        self.running = True
        logger.info(f"SCHEDULER: Started successfully with {len(self.scheduler.get_jobs())} active jobs.")

    def shutdown(self):
        """توقف زمان‌بندی"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.running = False
            logger.info("SCHEDULER: Shut down.")