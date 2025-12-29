# bot/services/account_service.py

import uuid
import random
import logging
import asyncio
from bot.database import db
from bot.services.panels.factory import PanelFactory
from bot.services import cache_manager
from bot.config import BOT_DOMAIN

logger = logging.getLogger(__name__)

class AccountService:
    """
    سرویس مرکزی مدیریت اکانت‌ها.
    وظایف: ساخت، خواندن اطلاعات، تولید لینک، تغییر نام و حذف.
    """

    async def create_test_account(self, user_id: int, username: str, country_code: str):
        """
        ساخت اکانت تست (فقط روی سرور کشور انتخاب شده).
        
        Args:
            user_id: آیدی عددی کاربر تلگرام
            username: نام انتخابی کاربر
            country_code: کد کشور (مثلا de, tr)
            
        Returns:
            dict: {success, error, uuid, panel_name}
        """
        try:
            # 1. دریافت پنل‌های فعال
            active_panels = await db.get_active_panels()
            
            # 2. فیلتر سخت‌گیرانه (Strict Mode): فقط پنل‌های همان کشور
            candidate_panels = [p for p in active_panels if p.get('category') == country_code]
            
            if not candidate_panels:
                logger.warning(f"No active panel found for country: {country_code}")
                return {"success": False, "error": "no_panel_for_country"}

            # 3. انتخاب رندوم یکی از سرورهای همان کشور (Load Balancing)
            target_panel_data = random.choice(candidate_panels)
            
            # 4. اتصال به پنل و ساخت کاربر
            panel_inst = await PanelFactory.get_panel(target_panel_data['name'])
            
            # تنظیمات اکانت تست (می‌تواند از کانفیگ خوانده شود)
            TEST_GIGS = 0.2  # 200 MB
            TEST_DAYS = 1    # 1 Day
            new_uuid = str(uuid.uuid4())
            
            result = await panel_inst.add_user(
                name=username,
                limit_gb=TEST_GIGS,
                expire_days=TEST_DAYS,
                uuid=new_uuid
            )
            
            if result:
                # 5. ثبت در دیتابیس ربات
                await db.add_uuid(user_id, new_uuid, username)
                
                # اعمال محدودیت دسترسی به نودهای همان کشور (اگر سیستم نودبندی فعال باشد)
                if hasattr(db, 'set_uuid_access_categories'):
                    await db.set_uuid_access_categories(new_uuid, [country_code])
                
                # 6. آپدیت کش در پس‌زمینه (Fire and Forget)
                asyncio.create_task(cache_manager.fetch_and_update_cache())
                
                return {
                    "success": True, 
                    "uuid": new_uuid, 
                    "panel_name": target_panel_data['name']
                }
            else:
                return {"success": False, "error": "panel_api_failed"}
                
        except Exception as e:
            logger.error(f"Error in AccountService.create_test_account: {e}")
            return {"success": False, "error": "exception"}

    async def get_service_details(self, uuid_str: str, user_id: int):
        """
        دریافت اطلاعات مصرف و انقضا برای نمایش در ربات.
        ابتدا مالکیت را چک می‌کند، سپس از کش می‌خواند.
        """
        # 1. احراز هویت مالکیت
        owner = await db.get_uuid_owner(uuid_str)
        if not owner or owner != user_id:
            return None

        # 2. خواندن از کش (که توسط کران‌جاب آپدیت می‌شود)
        info = await cache_manager.get_user_info(uuid_str)
        
        if not info:
            # حالت پیش‌فرض اگر دیتا در کش نبود
            return {
                "name": "Unknown",
                "usage_gb": 0,
                "limit_gb": 0,
                "expire_date": "نامشخص",
                "enable": True
            }
            
        return info

    async def generate_subscription_links(self, uuid_str: str):
        """
        تولید لینک‌های اشتراک (Subscription) برای اتصال.
        """
        domain = BOT_DOMAIN if BOT_DOMAIN else "http://example.com"
        # حذف اسلش اضافی اگر در کانفیگ باشد
        domain = domain.rstrip('/')
        
        # فرمت استاندارد لینک سابسکریپشن
        sub_link = f"{domain}/sub/{uuid_str}"
        
        # لینک Base64 شده (برخی کلاینت‌های قدیمی نیاز دارند)
        sub_link_b64 = f"{sub_link}?base64=True"
        
        return {
            "sub_link": sub_link,
            "sub_b64": sub_link_b64
        }

    async def rename_service(self, uuid_str: str, new_name: str, user_id: int):
        """
        تغییر نام سرویس (فعلاً فقط در دیتابیس ربات).
        """
        # آپدیت در دیتابیس لوکال ربات
        await db.update_uuid_name(user_id, uuid_str, new_name)
        
        # نکته: اگر بخواهید نام در پنل اصلی هم عوض شود، باید متد rename_user را
        # در کلاس‌های Panel پیاده‌سازی کرده و اینجا فراخوانی کنید.
        return True

    async def delete_service(self, uuid_str: str, user_id: int):
        """
        حذف سرویس از دیتابیس ربات.
        (توجه: این متد سرویس را از پنل اصلی پاک نمی‌کند تا کاربر دیتاش نپرد، فقط از دید ربات مخفی می‌شود)
        """
        result = await db.delete_uuid(user_id, uuid_str)
        return result

# نمونه‌سازی شده برای استفاده در هندلرها
account_service = AccountService()