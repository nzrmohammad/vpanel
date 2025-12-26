# bot/db/user.py

import logging
import secrets
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
import pytz

from sqlalchemy import select, update, delete, func, and_, or_, case, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

# وارد کردن مدل‌ها
from .base import (
    User, UserUUID, ClientUserAgent, LoginToken, MarzbanMapping, 
    UsageSnapshot, Panel, DatabaseManager
)

# تلاش برای ایمپورت تابع کمکی
try:
    from ..utils import parse_user_agent
except ImportError:
    def parse_user_agent(ua_string):
        return {'client': 'unknown', 'os': 'unknown'}

logger = logging.getLogger(__name__)

class UserDB:
    """
    کلاسی برای مدیریت تمام عملیات مربوط به کاربران و UUID های آن‌ها در دیتابیس.
    این کلاس با پشتیبانی از تنظیمات داینامیک (JSON) و دسترسی‌های دسته‌بندی‌شده بازنویسی شده است.
    """

    async def user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        اطلاعات کامل یک کاربر را با استفاده از کش واکشی می‌کند.
        """
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if user:
                # تبدیل آبجکت SQLAlchemy به دیکشنری
                user_data = {c.name: getattr(user, c.name) for c in user.__table__.columns}
                # اطمینان از اینکه settings یک دیکشنری است
                if user_data.get('settings') is None:
                    user_data['settings'] = {}
                self._user_cache[user_id] = user_data
                return user_data
            return None

    async def add_or_update_user(self, user_id: int, username: str = None, 
                                 first: str = None, last: str = None) -> bool:
        async with self.get_session() as session:
            # روش استاندارد (بدون وابستگی به پستگرس)
            user = await session.get(User, user_id)
            if user:
                if username is not None: user.username = username
                if first is not None: user.first_name = first
                if last is not None: user.last_name = last
            else:
                new_user = User(
                    user_id=user_id, 
                    username=username, 
                    first_name=first, 
                    last_name=last
                )
                session.add(new_user)
            
            await session.commit()
            if hasattr(self, 'clear_user_cache'):
                self.clear_user_cache(user_id)
            return True

    # --- تنظیمات داینامیک (Dynamic Settings) ---

# جایگزین متد فعلی get_user_settings در UserDB شوید:

    async def get_user_settings(self, user_id: int) -> Dict[str, bool]:
        """
        تنظیمات کاربر را می‌خواند.
        ✅ هوشمند: فقط دکمه‌های کشورهایی را اضافه می‌کند که کاربر حداقل در یک اکانتش به آن‌ها دسترسی داشته باشد.
        """
        user_data = await self.user(user_id)
        
        defaults = {
            'daily_reports': True, 'weekly_reports': True, 'monthly_reports': True,
            'expiry_warnings': True, 'show_info_config': True, 
            'achievement_alerts': True, 'promotional_alerts': True,
            'auto_delete_reports': False,
        }

        async with self.get_session() as session:
            # 1. دریافت تمام دسته‌بندی‌های موجود در سیستم
            from .base import ServerCategory 
            all_cats_stmt = select(ServerCategory.code)
            all_cats_result = await session.execute(all_cats_stmt)
            all_cats = [c for c in all_cats_result.scalars()]

            # 2. دریافت دسترسی‌های واقعی کاربر از جدول UserUUID
            # (اگر کاربر چند اکانت داشت، اجتماع دسترسی‌ها را می‌گیریم)
            user_access_stmt = select(UserUUID.allowed_categories).where(
                and_(UserUUID.user_id == user_id, UserUUID.is_active == True)
            )
            access_result = await session.execute(user_access_stmt)
            
            user_allowed_cats = set()
            for row in access_result.scalars():
                if row: # اگر لیست پر بود
                    user_allowed_cats.update(row)
            
            # اگر کاربر هیچ سرویسی ندارد یا لیست خالی است، شاید بخواهید همه را نشان دهید یا هیچکدام
            # اینجا فرض می‌کنیم اگر خالی بود، پیش‌فرض همه را نشان بده (برای کاربران جدید)
            # اما اگر سرویس دارد، فقط همان‌ها را نشان بده.
            final_cats_to_show = user_allowed_cats if user_allowed_cats else all_cats

            # اضافه کردن کلیدهای تنظیمات فقط برای کشورهای مجاز
            for code in all_cats:
                if code in final_cats_to_show or not user_allowed_cats:
                    defaults[f'data_warning_{code}'] = True
        
        if not user_data:
            return defaults
            
        saved_settings = user_data.get('settings', {}) or {}
        
        # ترکیب تنظیمات ذخیره شده با پیش‌فرض‌های هوشمند
        return {**defaults, **saved_settings}

    async def update_user_setting(self, user_id: int, setting: str, value: bool) -> None:
        """
        یک تنظیم خاص را در ستون JSON کاربر به‌روزرسانی می‌کند.
        این تابع کاملاً داینامیک است و هر تنظیم جدیدی را می‌پذیرد.
        """
        async with self.get_session() as session:
            user = await session.get(User, user_id)
            if user:
                if user.settings is None:
                    user.settings = {}
                
                # به‌روزرسانی دیکشنری
                user.settings[setting] = value
                
                # اعلام تغییر به SQLAlchemy برای اعمال در دیتابیس
                flag_modified(user, "settings")
                await session.commit()
                
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    # --- سایر متدهای کاربر ---

    async def update_user_birthday(self, user_id: int, birthday_date: date):
        """تاریخ تولد کاربر را به‌روزرسانی می‌کند."""
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(birthday=birthday_date))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def get_users_with_birthdays(self):
        """تمام کاربرانی که تاریخ تولد ثبت کرده‌اند را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name, User.username, User.birthday)
                .where(User.birthday.is_not(None))
                .order_by(func.to_char(User.birthday, 'MM-DD'))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def reset_user_birthday(self, user_id: int) -> None:
        """تاریخ تولد کاربر را حذف (ریست) می‌کند."""
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(birthday=None))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def set_user_language(self, user_id: int, lang_code: str):
        """زبان انتخابی کاربر را ذخیره می‌کند."""
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(lang_code=lang_code))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def get_user_language(self, user_id: int) -> str:
        """زبان کاربر را از دیتابیس می‌خواند."""
        async with self.get_session() as session:
            result = await session.execute(select(User.lang_code).where(User.user_id == user_id))
            lang = result.scalar_one_or_none()
            return lang if lang else 'fa'

    async def update_user_note(self, user_id: int, note: Optional[str]) -> None:
        """یادداشت ادمین برای یک کاربر را به‌روزرسانی می‌کند."""
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(admin_note=note))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def get_all_bot_users(self) -> List[Dict[str, Any]]:
        """لیست تمام کاربران ربات را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(User.user_id, User.username, User.first_name, User.last_name).order_by(User.user_id)
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def get_user_by_telegram_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """یک کاربر را بر اساس شناسه تلگرام او پیدا می‌کند."""
        return await self.user(user_id)

    async def get_all_user_ids(self):
        """تمام شناسه‌های کاربری تلگرام را برمی‌گرداند."""
        async with self.get_session() as session:
            result = await session.execute(select(User.user_id))
            for row in result.scalars().all():
                yield row

    async def purge_user_by_telegram_id(self, user_id: int) -> bool:
        """یک کاربر را به طور کامل از جدول users و تمام جداول وابسته حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            await session.commit()
            
            if hasattr(self, 'clear_user_cache'):
                self.clear_user_cache(user_id)
                
            return result.rowcount > 0

    # --- توابع مربوط به UUID ---

    async def add_uuid(self, user_id: int, uuid_str: str, name: str) -> Any:
        """یک UUID جدید برای کاربر اضافه می‌کند یا وضعیت‌های مختلف را مدیریت می‌کند."""
        uuid_str = uuid_str.lower()
        async with self.get_session() as session:
            # 1. بررسی UUID غیرفعال متعلق به همین کاربر
            stmt_inactive = select(UserUUID).where(
                and_(UserUUID.user_id == user_id, UserUUID.uuid == uuid_str, UserUUID.is_active == False)
            )
            result_inactive = await session.execute(stmt_inactive)
            existing_inactive = result_inactive.scalar_one_or_none()

            if existing_inactive:
                existing_inactive.is_active = True
                existing_inactive.name = name
                existing_inactive.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return "db_msg_uuid_reactivated"

            # 2. بررسی UUID فعال (تکراری)
            stmt_active = select(UserUUID).where(
                and_(UserUUID.uuid == uuid_str, UserUUID.is_active == True)
            )
            result_active = await session.execute(stmt_active)
            existing_active = result_active.scalar_one_or_none()

            if existing_active:
                if existing_active.user_id == user_id:
                    return "db_err_uuid_already_active_self"
                else:
                    return {
                        "status": "confirmation_required",
                        "owner_id": existing_active.user_id,
                        "uuid_id": existing_active.id
                    }

            # 3. افزودن UUID جدید
            new_uuid = UserUUID(user_id=user_id, uuid=uuid_str, name=name)
            session.add(new_uuid)
            await session.commit()
            return "db_msg_uuid_added"

    async def add_shared_uuid(self, user_id: int, uuid_str: str, name: str) -> bool:
        """یک اکانت اشتراکی را بدون بررسی مالکیت، برای کاربر ثبت می‌کند."""
        uuid_str = uuid_str.lower()
        async with self.get_session() as session:
            stmt = select(UserUUID).where(
                and_(UserUUID.user_id == user_id, UserUUID.uuid == uuid_str, UserUUID.is_active == False)
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.is_active = True
                existing.name = name
                existing.updated_at = datetime.now()
            else:
                new_uuid = UserUUID(user_id=user_id, uuid=uuid_str, name=name, is_active=True)
                session.add(new_uuid)
            
            await session.commit()
            return True

    async def uuids(self, user_id: int) -> List[Dict[str, Any]]:
        """تمام UUID های فعال یک کاربر را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(UserUUID).where(
                and_(UserUUID.user_id == user_id, UserUUID.is_active == True)
            ).order_by(UserUUID.created_at)
            result = await session.execute(stmt)
            # تبدیل به دیکشنری
            return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in result.scalars().all()]

    async def uuid_by_id(self, user_id: int, uuid_id: int) -> Optional[Dict[str, Any]]:
        """یک UUID خاص را با شناسه داخلی آن برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(UserUUID).where(
                and_(UserUUID.user_id == user_id, UserUUID.id == uuid_id, UserUUID.is_active == True)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return {c.name: getattr(row, c.name) for c in row.__table__.columns}
            return None

    async def get_uuid_id_by_uuid(self, uuid_str: str) -> Optional[int]:
        """شناسه داخلی رکورد UUID را پیدا می‌کند."""
        async with self.get_session() as session:
            stmt = select(UserUUID.id).where(UserUUID.uuid == uuid_str)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def deactivate_uuid(self, uuid_id: int) -> bool:
        """یک UUID را غیرفعال می‌کند."""
        async with self.get_session() as session:
            stmt = update(UserUUID).where(UserUUID.id == uuid_id).values(is_active=False)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def delete_user_by_uuid(self, uuid: str) -> None:
        """یک رکورد UUID را از دیتابیس حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(UserUUID).where(UserUUID.uuid == uuid)
            await session.execute(stmt)
            await session.commit()

    async def all_active_uuids(self):
        """تمام UUID های فعال را به همراه اطلاعاتشان برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(
                UserUUID.id, UserUUID.user_id, UserUUID.uuid, UserUUID.created_at, 
                UserUUID.first_connection_time, UserUUID.welcome_message_sent, 
                UserUUID.renewal_reminder_sent, UserUUID.name
            ).where(UserUUID.is_active == True)
            
            result = await session.execute(stmt)
            for row in result.all():
                yield dict(row._mapping)

    async def get_user_id_by_uuid(self, uuid: str) -> Optional[int]:
        """شناسه تلگرام کاربر را با استفاده از UUID پیدا می‌کند."""
        async with self.get_session() as session:
            stmt = select(UserUUID.user_id).where(UserUUID.uuid == uuid)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_bot_user_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """اطلاعات پایه کاربر را با استفاده از UUID پیدا می‌کند."""
        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name, User.username)
                .join(UserUUID, User.user_id == UserUUID.user_id)
                .where(UserUUID.uuid == uuid)
            )
            result = await session.execute(stmt)
            row = result.first()
            if row:
                return dict(row._mapping)
            return None
            
    async def get_uuid_to_user_id_map(self) -> Dict[str, int]:
        async with self.get_session() as session:
            stmt = select(UserUUID.uuid, UserUUID.user_id).where(UserUUID.is_active == True)
            result = await session.execute(stmt)
            return {str(row.uuid): row.user_id for row in result.all()}
    
    async def get_uuid_to_bot_user_map(self) -> Dict[str, Dict[str, Any]]:
        """مپینگ UUID به اطلاعات پایه کاربر."""
        async with self.get_session() as session:
            stmt = (
                select(UserUUID.uuid, User.user_id, User.first_name, User.username)
                .outerjoin(User, UserUUID.user_id == User.user_id)
                .where(UserUUID.is_active == True)
            )
            result = await session.execute(stmt)
            return {str(row.uuid): {"user_id": row.user_id, "first_name": row.first_name, "username": row.username} for row in result.all()}

    async def set_first_connection_time(self, uuid_id: int, time: datetime):
        async with self.get_session() as session:
            await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(first_connection_time=time))
            await session.commit()

    async def mark_welcome_message_as_sent(self, uuid_id: int):
        async with self.get_session() as session:
            await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(welcome_message_sent=True))
            await session.commit()
            
    async def reset_welcome_message_sent(self, uuid_id: int):
        async with self.get_session() as session:
            await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(welcome_message_sent=False))
            await session.commit()

    async def set_renewal_reminder_sent(self, uuid_id: int):
        async with self.get_session() as session:
            await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(renewal_reminder_sent=True))
            await session.commit()
            
    async def reset_renewal_reminder_sent(self, uuid_id: int):
        async with self.get_session() as session:
            await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(renewal_reminder_sent=False))
            await session.commit()
            
    async def get_user_uuid_record(self, uuid_str: str) -> dict | None:
        """اطلاعات کامل رکورد UUID."""
        async with self.get_session() as session:
            stmt = select(UserUUID).where(and_(UserUUID.uuid == uuid_str, UserUUID.is_active == True))
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                return {c.name: getattr(row, c.name) for c in row.__table__.columns}
            return None
            
    async def get_all_user_uuids(self) -> List[Dict[str, Any]]:
        """تمام رکوردهای UUID برای پنل ادمین."""
        async with self.get_session() as session:
            stmt = select(UserUUID).order_by(desc(UserUUID.created_at))
            result = await session.execute(stmt)
            return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in result.scalars().all()]

    async def update_config_name(self, uuid_id: int, new_name: str) -> bool:
        """نام نمایشی کانفیگ را تغییر می‌دهد."""
        if not new_name or len(new_name) < 2:
            return False
        async with self.get_session() as session:
            stmt = update(UserUUID).where(UserUUID.id == uuid_id).values(name=new_name)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def toggle_user_vip(self, uuid: str) -> None:
        """وضعیت VIP را تغییر می‌دهد (Toggle)."""
        async with self.get_session() as session:
            stmt = update(UserUUID).where(UserUUID.uuid == uuid).values(is_vip=~UserUUID.is_vip)
            await session.execute(stmt)
            await session.commit()
            
    async def get_all_bot_users_with_uuids(self) -> List[Dict[str, Any]]:
        """
        اطلاعات کاربران و کانفیگ‌ها به همراه وضعیت مرزبان.
        حالا که ستون‌های دسترسی حذف شده‌اند، باید لیست دسترسی‌ها را از رابطه بخوانیم.
        """
        async with self.get_session() as session:
            # از selectinload برای لود کردن پنل‌های مجاز استفاده می‌کنیم
            stmt = (
                select(
                    User.user_id, User.first_name, User.username,
                    UserUUID.id.label('uuid_id'), UserUUID.name.label('config_name'), 
                    UserUUID.uuid, UserUUID.is_vip, UserUUID, # خود آبجکت UUID را می‌گیریم
                    case((MarzbanMapping.hiddify_uuid != None, 1), else_=0).label('is_on_marzban')
                )
                .join(UserUUID, User.user_id == UserUUID.user_id)
                .outerjoin(MarzbanMapping, UserUUID.uuid == MarzbanMapping.hiddify_uuid)
                .options(selectinload(UserUUID.allowed_panels)) # لود پنل‌ها
                .where(UserUUID.is_active == True)
                .order_by(User.user_id, UserUUID.created_at)
            )
            
            result = await session.execute(stmt)
            output = []
            for row in result:
                data = dict(row._mapping)
                uuid_obj = data.pop('UserUUID') # آبجکت UUID را جدا می‌کنیم
                
                # استخراج دسترسی‌ها بر اساس دسته‌بندی پنل‌ها
                # خروجی مثلاً: {'has_access_de': True, 'has_access_fr': False, ...}
                access_flags = {}
                # اگر پنلی در دسته خاصی باشد، فلگ مربوطه True می‌شود
                if uuid_obj.allowed_panels:
                    for panel in uuid_obj.allowed_panels:
                        if panel.category:
                            access_flags[f"has_access_{panel.category}"] = True
                
                # ترکیب داده‌ها
                output.append({**data, **access_flags})
            
            return output

    async def update_user_server_access(self, uuid_id: int, category: str, status: bool) -> bool:
        """
        دسترسی کاربر به یک دسته‌بندی خاص را فعال/غیرفعال می‌کند (همراه با رفرش کش).
        """
        try:
            from bot.db.base import UserUUID, Panel
            
            uid_to_clear = None
            async with self.get_session() as session:
                uuid_obj = await session.get(UserUUID, uuid_id)
                if not uuid_obj: return False
                
                uid_to_clear = uuid_obj.user_id
                
                await session.refresh(uuid_obj, ["allowed_panels"])
                
                if status: # فعال‌سازی
                    stmt = select(Panel).where(Panel.category == category)
                    result = await session.execute(stmt)
                    panels_to_add = result.scalars().all()
                    
                    current_ids = {p.id for p in uuid_obj.allowed_panels}
                    for p in panels_to_add:
                        if p.id not in current_ids:
                            uuid_obj.allowed_panels.append(p)
                else: # غیرفعال‌سازی
                    uuid_obj.allowed_panels = [
                        p for p in uuid_obj.allowed_panels if p.category != category
                    ]
                
                await session.commit()

            # پاکسازی کش
            if uid_to_clear and hasattr(self, 'clear_user_cache'):
                self.clear_user_cache(uid_to_clear)
                
            return True
        except Exception as e:
            logger.error(f"DB Error (update_user_server_access): {e}")
            return False
                
    async def get_user_access_rights(self, user_id: int) -> dict:
        """
        حقوق دسترسی کاربر را بر اساس دسته‌بندی پنل‌ها و نودهای مجاز برمی‌گرداند.
        ✅ نسخه اصلاح شده (بدون نیاز به تغییر در base.py)
        """
        access_rights = {}
        async with self.get_session() as session:
            from .base import UserUUID, Panel, PanelNode
            
            # 1️⃣ استخراج دسته‌بندی پنل‌هایی که کاربر به آن‌ها دسترسی دارد
            stmt_panels = (
                select(Panel.category)
                .join(UserUUID.allowed_panels)
                .where(and_(
                    UserUUID.user_id == user_id,
                    UserUUID.is_active == True,
                    Panel.is_active == True
                ))
                .distinct()
            )
            
            res_panels = await session.execute(stmt_panels)
            for cat in res_panels.scalars().all():
                if cat:
                    access_rights[f"has_access_{cat}"] = True

            # 2️⃣ استخراج کدهای کشور نودها (PanelNode)
            # ✅ تغییر: استفاده از جوین دستی به جای PanelNode.panel
            stmt_nodes = (
                select(PanelNode.country_code)
                .join(Panel, Panel.id == PanelNode.panel_id) # اتصال نود به پنل از طریق ID
                .join(UserUUID, Panel.allowed_uuids)         # اتصال پنل به کاربر
                .where(and_(
                    UserUUID.user_id == user_id,
                    UserUUID.is_active == True,
                    Panel.is_active == True,
                    PanelNode.is_active == True
                ))
                .distinct()
            )
            
            res_nodes = await session.execute(stmt_nodes)
            for code in res_nodes.scalars().all():
                if code:
                    access_rights[f"has_access_{code}"] = True
                    
        return access_rights

    # --- توابع مربوط به دستگاه‌های کاربر (User Agents) ---

    async def record_user_agent(self, uuid_id: int, user_agent: str):
        """دستگاه کاربر را ثبت یا به‌روزرسانی می‌کند."""
        new_parsed = parse_user_agent(user_agent)
        if not new_parsed or not new_parsed.get('client'):
            return

        async with self.get_session() as session:
            existing_agents = await self.get_user_agents_for_uuid(uuid_id)
            for agent in existing_agents:
                existing_parsed = parse_user_agent(agent['user_agent'])
                if (existing_parsed and 
                    existing_parsed.get('client') == new_parsed.get('client') and 
                    existing_parsed.get('os') == new_parsed.get('os')):
                    
                    stmt = (
                        update(ClientUserAgent)
                        .where(and_(ClientUserAgent.uuid_id == uuid_id, ClientUserAgent.user_agent == agent['user_agent']))
                        .values(user_agent=user_agent, last_seen=datetime.now(timezone.utc))
                    )
                    await session.execute(stmt)
                    await session.commit()
                    return

            try:
                new_ua = ClientUserAgent(uuid_id=uuid_id, user_agent=user_agent, last_seen=datetime.now())
                session.add(new_ua)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                stmt = (
                    update(ClientUserAgent)
                    .where(and_(ClientUserAgent.uuid_id == uuid_id, ClientUserAgent.user_agent == user_agent))
                    .values(last_seen=datetime.now())
                )
                await session.execute(stmt)
                await session.commit()

    async def delete_all_user_agents(self) -> int:
        async with self.get_session() as session:
            stmt = delete(ClientUserAgent)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def get_user_agents_for_uuid(self, uuid_id: int) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(ClientUserAgent).where(ClientUserAgent.uuid_id == uuid_id).order_by(desc(ClientUserAgent.last_seen))
            result = await session.execute(stmt)
            return [{"user_agent": r.user_agent, "last_seen": r.last_seen} for r in result.scalars().all()]

    async def get_all_user_agents(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = (
                select(
                    ClientUserAgent.user_agent, ClientUserAgent.last_seen,
                    UserUUID.name.label('config_name'), User.first_name, User.user_id
                )
                .join(UserUUID, ClientUserAgent.uuid_id == UserUUID.id)
                .outerjoin(User, UserUUID.user_id == User.user_id)
                .order_by(desc(ClientUserAgent.last_seen))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def count_user_agents(self, uuid_id: int) -> int:
        async with self.get_session() as session:
            stmt = select(func.count(ClientUserAgent.id)).where(ClientUserAgent.uuid_id == uuid_id)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def delete_user_agents_by_uuid_id(self, uuid_id: int) -> int:
        async with self.get_session() as session:
            stmt = delete(ClientUserAgent).where(ClientUserAgent.uuid_id == uuid_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
            
    # --- توابع مربوط به سیستم معرفی (Referral) ---

    async def get_or_create_referral_code(self, user_id: int) -> str:
        user_data = await self.user(user_id)
        if user_data and user_data.get('referral_code'):
            return user_data['referral_code']
            
        async with self.get_session() as session:
            while True:
                new_code = "REF-" + secrets.token_urlsafe(4).upper().replace("_", "").replace("-", "")
                exists = await session.execute(select(User).where(User.referral_code == new_code))
                if not exists.first():
                    await session.execute(update(User).where(User.user_id == user_id).values(referral_code=new_code))
                    await session.commit()
                    if hasattr(self, 'clear_user_cache'):
                        self.clear_user_cache(user_id)
                    return new_code

    async def set_referrer(self, user_id: int, referrer_code: str):
        async with self.get_session() as session:
            stmt = select(User.user_id).where(User.referral_code == referrer_code)
            result = await session.execute(stmt)
            referrer_id = result.scalar_one_or_none()
            if referrer_id:
                await session.execute(update(User).where(User.user_id == user_id).values(referred_by_user_id=referrer_id))
                await session.commit()
                if hasattr(self, 'clear_user_cache'):
                    self.clear_user_cache(user_id)

    async def get_referrer_info(self, user_id: int) -> Optional[dict]:
        async with self.get_session() as session:
            Referrer = User
            stmt = (
                select(
                    User.referred_by_user_id, 
                    User.referral_reward_applied, 
                    Referrer.first_name.label('referrer_name')
                )
                .select_from(User)
                .join(Referrer, User.referred_by_user_id == Referrer.user_id)
                .where(User.user_id == user_id)
            )
            result = await session.execute(stmt)
            row = result.first()
            return dict(row._mapping) if row else None

    async def mark_referral_reward_as_applied(self, user_id: int):
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(referral_reward_applied=True))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)
        
    async def get_referred_users(self, referrer_user_id: int) -> list[dict]:
        async with self.get_session() as session:
            stmt = select(User.user_id, User.first_name, User.referral_reward_applied).where(User.referred_by_user_id == referrer_user_id)
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]
        
    async def get_user_ids_by_uuids(self, uuids: List[str]) -> List[int]:
        if not uuids: return []
        async with self.get_session() as session:
            stmt = select(UserUUID.user_id).where(UserUUID.uuid.in_(uuids)).distinct()
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_login_token(self, user_uuid: str) -> str:
        token = secrets.token_urlsafe(32)
        async with self.get_session() as session:
            obj = LoginToken(token=token, uuid=user_uuid, created_at=datetime.now(timezone.utc))
            session.add(obj)
            await session.commit()
        return token

    async def validate_login_token(self, token: str) -> Optional[str]:
        five_mins_ago = datetime.now() - timedelta(minutes=5)
        async with self.get_session() as session:
            await session.execute(delete(LoginToken).where(LoginToken.created_at < five_mins_ago))
            stmt = select(LoginToken).where(LoginToken.token == token)
            result = await session.execute(stmt)
            token_obj = result.scalar_one_or_none()
            
            if token_obj:
                uuid = token_obj.uuid
                await session.delete(token_obj)
                await session.commit()
                return uuid
            
            await session.commit()
        return None

    async def update_auto_renew_setting(self, user_id: int, status: bool):
        async with self.get_session() as session:
            await session.execute(update(User).where(User.user_id == user_id).values(auto_renew=status))
            await session.commit()
        if hasattr(self, 'clear_user_cache'):
            self.clear_user_cache(user_id)

    async def get_all_active_uuids_with_user_id(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(UserUUID.id, UserUUID.user_id).where(UserUUID.is_active == True)
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def get_all_user_uuids_and_panel_data(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            subq = (
                select(UsageSnapshot.uuid_id, func.max(UsageSnapshot.taken_at).label('last_taken'))
                .group_by(UsageSnapshot.uuid_id)
                .subquery()
            )
            stmt = (
                select(
                    UserUUID.uuid, UserUUID.user_id, UserUUID.name,
                    func.coalesce(UsageSnapshot.hiddify_usage_gb, 0).label('used_traffic_hiddify'),
                    func.coalesce(UsageSnapshot.marzban_usage_gb, 0).label('used_traffic_marzban'),
                    UsageSnapshot.taken_at.label('last_online_jalali')
                )
                .join(subq, UserUUID.id == subq.c.uuid_id, isouter=True)
                .join(UsageSnapshot, and_(subq.c.uuid_id == UsageSnapshot.uuid_id, subq.c.last_taken == UsageSnapshot.taken_at), isouter=True)
                .where(UserUUID.is_active == True)
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def add_or_update_user_from_panel(self, uuid: str, name: str, telegram_id: Optional[int], 
                                            expire_days_hiddify: Optional[int], expire_days_marzban: Optional[int], 
                                            last_online_jalali: Optional[datetime], 
                                            used_traffic_hiddify: float, used_traffic_marzban: float):
        async with self.get_session() as session:
            stmt = select(UserUUID).where(UserUUID.uuid == uuid)
            result = await session.execute(stmt)
            uuid_record = result.scalar_one_or_none()
            
            if not uuid_record: return

            uuid_record.name = name
            
            if telegram_id:
                user_exists = await session.get(User, telegram_id)
                if not user_exists:
                    new_user = User(user_id=telegram_id, first_name=name)
                    session.add(new_user)
            
            await session.commit()

    async def get_todays_birthdays(self) -> list:
        today_str = datetime.now().strftime('%m-%d')
        async with self.get_session() as session:
            stmt = select(User.user_id).where(func.to_char(User.birthday, 'MM-DD') == today_str)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_vip_users(self) -> int:
        async with self.get_session() as session:
            stmt = select(func.count(UserUUID.id)).where(and_(UserUUID.is_active == True, UserUUID.is_vip == True))
            result = await session.execute(stmt)
            return result.scalar_one()

    async def get_new_vips_last_7_days(self) -> list[dict]:
        seven_days_ago = datetime.now() - timedelta(days=7)
        async with self.get_session() as session:
            stmt = (
                select(User.user_id, User.first_name)
                .join(UserUUID, User.user_id == UserUUID.user_id)
                .where(and_(UserUUID.is_vip == True, UserUUID.updated_at >= seven_days_ago))
            )
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def update_user_panel_access_by_id(self, uuid_id: int, panel_id: int, allow: bool) -> bool:
        """آپدیت دسترسی پنل با استفاده از ID دقیق پنل (همراه با رفرش کش)"""
        try:
            from bot.db.base import UserUUID, Panel
            
            uid_to_clear = None
            async with self.get_session() as session:
                user_uuid = await session.get(UserUUID, uuid_id)
                if not user_uuid: return False
                
                uid_to_clear = user_uuid.user_id # ذخیره شناسه کاربر برای پاکسازی کش
                
                await session.refresh(user_uuid, ["allowed_panels"])
                panel = await session.get(Panel, panel_id)
                if not panel: return False
                
                if allow:
                    if panel not in user_uuid.allowed_panels:
                        user_uuid.allowed_panels.append(panel)
                else:
                    if panel in user_uuid.allowed_panels:
                        user_uuid.allowed_panels.remove(panel)
                
                await session.commit()
            
            # پاکسازی کش
            if uid_to_clear and hasattr(self, 'clear_user_cache'):
                self.clear_user_cache(uid_to_clear)
                
            return True
        except Exception as e:
            logger.error(f"DB Error (update_user_panel_access_by_id): {e}")
            return False

    async def set_uuid_access_categories(self, uuid: str, categories: List[str]) -> bool:
        """دسترسی‌های مجاز (کشورها) را برای یک UUID تنظیم می‌کند (همراه با رفرش کش)"""
        try:
            uid_to_clear = None
            async with self.get_session() as session:
                stmt = select(UserUUID).where(UserUUID.uuid == uuid)
                result = await session.execute(stmt)
                user_uuid_obj = result.scalar_one_or_none()
                
                if user_uuid_obj:
                    uid_to_clear = user_uuid_obj.user_id
                    user_uuid_obj.allowed_categories = categories
                    flag_modified(user_uuid_obj, "allowed_categories")
                    await session.commit()
            
            # پاکسازی کش
            if uid_to_clear and hasattr(self, 'clear_user_cache'):
                self.clear_user_cache(uid_to_clear)
                
            return True if uid_to_clear else False
        except Exception as e:
            logger.error(f"DB Error (set_uuid_access_categories): {e}")
            return False
        
    async def has_ever_had_account(self, user_id: int) -> bool:
        """
        بررسی می‌کند که آیا کاربر تا به حال هیچ اکانتی (فعال یا حذف شده) داشته است؟
        این متد برای جلوگیری از دریافت مجدد سرویس تست استفاده می‌شود.
        """
        async with self.get_session() as session:
            # جستجو در جدول UserUUID بدون شرط is_active
            stmt = select(UserUUID.id).where(UserUUID.user_id == user_id).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None