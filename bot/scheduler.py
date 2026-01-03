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
            # گزارش شبانه به ادمین (مثلاً ساعت 23:55)
            self.scheduler.add_job(
                reports.send_daily_admin_report, # نام تابعی که گزارش جامع ادمین را می‌فرستد
                trigger=CronTrigger(hour=23, minute=55),
                args=[self.bot],
                id="job_nightly_report_admin",
                replace_existing=True
            )
            
            # گزارش شبانه به کاربران (اختیاری - ساعت 21:00)
            # self.scheduler.add_job(
            #     reports.send_nightly_user_reports,
            #     trigger=CronTrigger(hour=21, minute=0),
            #     args=[self.bot],
            #     id="job_nightly_report_users"
            # )

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

        # -----------------------------------------------------------
        # 4. امور مالی (Financials)
        # -----------------------------------------------------------
        if financials:
            # بررسی تمدیدهای خودکار (مثلاً ساعت 4:30 صبح)
            self.scheduler.add_job(
                financials.process_auto_renewals,
                trigger=CronTrigger(hour=4, minute=30),
                args=[self.bot],
                id="job_auto_renewals"
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