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
from bot.scheduler_jobs import warnings, reports
# ایمپورت‌های اختیاری
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
        # چک کردن هشدارها هر 10 دقیقه
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
            # الف) گزارش شبانه (Nightly Report)
            # زمان اجرا: هر شب ساعت 23:59
            self.scheduler.add_job(
                reports.nightly_report,
                trigger=CronTrigger(hour=23, minute=59),
                args=[self.bot],
                id="job_nightly_report",
                replace_existing=True
            )

            # ب) گزارش هفتگی کاربران (Weekly Report)
            # زمان اجرا: جمعه‌ها ساعت 12:00 ظهر
            self.scheduler.add_job(
                reports.weekly_report,
                trigger=CronTrigger(day_of_week='fri', hour=12, minute=0),
                args=[self.bot],
                id="job_weekly_report",
                replace_existing=True
            )

            # ج) خلاصه هفتگی ادمین (Weekly Admin Summary)
            # زمان اجرا: جمعه‌ها ساعت 23:30 شب
            self.scheduler.add_job(
                reports.send_weekly_admin_summary,
                trigger=CronTrigger(day_of_week='fri', hour=23, minute=30),
                args=[self.bot],
                id="job_weekly_admin_summary",
                replace_existing=True
            )

            # د) نظرسنجی ماهانه (Monthly Survey)
            # زمان اجرا: جمعه‌ها ساعت 18:00 (تابع خودش چک می‌کند که جمعه آخر ماه باشد)
            self.scheduler.add_job(
                reports.send_monthly_satisfaction_survey,
                trigger=CronTrigger(day_of_week='fri', hour=18, minute=0),
                args=[self.bot],
                id="job_monthly_survey",
                replace_existing=True
            )

        # -----------------------------------------------------------
        # 3. نگهداری و تعمیرات (Maintenance)
        # -----------------------------------------------------------
        if maintenance:
            self.scheduler.add_job(
                maintenance.sync_users_with_panels,
                trigger=IntervalTrigger(hours=1),
                args=[self.bot],
                id="job_sync_panels"
            )
            
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