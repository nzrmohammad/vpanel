# bot/services/panels/factory.py
from typing import Dict
from .base import BasePanel
from .hiddify import HiddifyPanel
from .remnawave import RemnawavePanel
from .marzban import MarzbanPanel
from .pasarguard import PasarGuardPanel


class PanelFactory:
    _instances: Dict[str, BasePanel] = {}

    @classmethod
    async def get_panel(cls, panel_name: str) -> BasePanel:
        """
        اینستنس پنل را بر اساس نام آن از دیتابیس می‌سازد.
        """
        # 1. استفاده از کش برای سرعت بیشتر
        if panel_name in cls._instances:
            return cls._instances[panel_name]

        # 2. دریافت اطلاعات پنل از دیتابیس
        from bot.database import db
        panel_data = await db.get_panel_by_name(panel_name)
        
        if not panel_data:
            raise ValueError(f"Panel '{panel_name}' not found in database. Please add it via Admin Panel.")

        # 3. تشخیص نوع پنل و ساخت نمونه
        instance = None
        p_type = panel_data['panel_type']
        
        if p_type == 'marzban':
            instance = MarzbanPanel(
                api_url=panel_data['api_url'],
                username=panel_data['api_token1'], # در دیتابیس: توکن ۱ = نام کاربری
                password=panel_data['api_token2']  # در دیتابیس: توکن ۲ = رمز عبور
            )
        
        elif p_type == 'hiddify':
            extra = {}
            if panel_data.get('api_token2'):
                extra['proxy_path'] = panel_data['api_token2'] # در دیتابیس: توکن ۲ = مسیر پروکسی
            
            instance = HiddifyPanel(
                api_url=panel_data['api_url'],
                api_key=panel_data['api_token1'], # در دیتابیس: توکن ۱ = API Key
                extra_config=extra
            )
        elif p_type == 'remnawave':
            instance = RemnawavePanel(
                api_url=panel_data['api_url'],
                api_token=panel_data['api_token1'] # توکن در فیلد token1 ذخیره می‌شود
            )

        elif p_type == "pasarguard":
            instance = PasarGuardPanel(
                api_url=panel_data['api_url'],
                # نگاشت فیلدهای دیتابیس به ورودی‌های کلاس پاسارگاد
                username=panel_data['api_token1'],  # معمولاً توکن ۱ به عنوان یوزرنیم استفاده می‌شود
                password=panel_data['api_token2'],  # معمولاً توکن ۲ به عنوان پسورد استفاده می‌شود
                extra_config={} 
            )
            
        else:
            raise ValueError(f"Unknown panel type: {p_type}")

        # 4. ذخیره در کش
        cls._instances[panel_name] = instance
        return instance

    @classmethod
    def clear_cache(cls, panel_name: str = None):
        if panel_name and panel_name in cls._instances:
            del cls._instances[panel_name]
        elif panel_name is None:
            cls._instances.clear()