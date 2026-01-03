# bot/services/report_strategies.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, and_, or_, String
from sqlalchemy.orm import Session

# ایمپورت‌های پروژه شما
from bot.db.base import User, UserUUID, UsageSnapshot, Panel
from bot.db import queries
from bot.utils.date_helpers import to_shamsi, format_relative_time, days_until_next_birthday
from bot.utils.formatters import escape_markdown
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

LRM = "\u200e"
RLM = "\u200f"

class ReportStrategy(ABC):
    """کلاس پایه برای تمام گزارش‌ها"""
    @abstractmethod
    async def generate(self, session: Session, params: list, offset: int, limit: int) -> tuple[list, int, str]:
        """
        خروجی: (لیست آیتم‌های فرمت شده، تعداد کل، عنوان گزارش)
        """
        pass

# =========================================================
# استراتژی‌های مبتنی بر پنل (Panel Based)
# =========================================================

class BasePanelStrategy(ReportStrategy):
    """کلاس والد برای گزارش‌های مربوط به پنل جهت جلوگیری از تکرار کد"""
    
    async def _fetch_and_parse_users(self, session, panel_id):
        """دریافت کاربران از پنل و پردازش اولیه"""
        panel_obj = await session.get(Panel, panel_id)
        if not panel_obj:
            raise ValueError("Panel not found")

        panel_service = await PanelFactory.get_panel(panel_obj.name)
        all_users = await panel_service.get_all_users()
        
        parsed_users = []
        for u in all_users:
            # استانداردسازی زمان اتصال
            last_seen_raw = u.get('online_at') or u.get('last_online') or u.get('last_connection')
            last_seen_dt = None
            if last_seen_raw:
                try:
                    if isinstance(last_seen_raw, (int, float)):
                        last_seen_dt = datetime.utcfromtimestamp(float(last_seen_raw))
                    elif isinstance(last_seen_raw, str):
                        clean_time = last_seen_raw.replace('Z', '').split('.')[0]
                        last_seen_dt = datetime.fromisoformat(clean_time)
                except: pass
            
            u['_parsed_last_seen'] = last_seen_dt
            u['_used_bytes'] = u.get('used_traffic') or (u.get('current_usage_GB', 0) * 1024**3)
            u['_limit_bytes'] = u.get('transfer_enable') or (u.get('usage_limit_GB', 0) * 1024**3)
            parsed_users.append(u)
            
        return parsed_users, panel_obj

    async def _enrich_with_db_info(self, session, users_list, panel_id):
        """افزودن اطلاعات تلگرام (لینک پروفایل) به لیست کاربران پنل"""
        idents = [u.get('uuid') or u.get('username') for u in users_list]
        idents = [i for i in idents if i]
        
        telegram_map = {}
        db_id_map = {} # map ident -> db_id (for usage calculation)
        
        if idents:
            stmt = select(UserUUID).where(
                and_(
                    UserUUID.allowed_panels.any(id=panel_id),
                    or_(UserUUID.uuid.cast(String).in_(idents), UserUUID.name.in_(idents))
                )
            )
            db_users = (await session.execute(stmt)).scalars().all()
            for du in db_users:
                key = str(du.uuid) if du.uuid else du.name
                if du.user_id: telegram_map[key] = du.user_id
                db_id_map[key] = du.id
                
        return telegram_map, db_id_map

    def _format_user_line(self, user, display_name, telegram_id=None):
        """ساخت نام لینک‌دار"""
        clean_name = display_name.replace('<', '').replace('>', '').replace('[', '').replace(']', '')
        name_esc = escape_markdown(clean_name)
        if telegram_id:
            return f"[{name_esc}](tg://user?id={telegram_id})"
        return name_esc

class OnlineUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        # فیلتر آنلاین‌ها (۳ دقیقه اخیر)
        window = timedelta(minutes=3)
        now_utc = datetime.utcnow()
        filtered = [u for u in users if u['_parsed_last_seen'] and (now_utc - u['_parsed_last_seen']) < window]
        
        # دریافت اطلاعات تکمیلی
        tg_map, db_id_map = await self._enrich_with_db_info(session, filtered, panel_id)
        
        # محاسبه مصرف امروز (فقط برای آنلاین‌ها)
        daily_usage = {}
        if db_id_map:
            start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            snap_stmt = select(UsageSnapshot).where(
                and_(
                    UsageSnapshot.uuid_id.in_(list(db_id_map.values())),
                    UsageSnapshot.taken_at >= start_of_day
                )
            )
            snapshots = (await session.execute(snap_stmt)).scalars().all()
            
            first_usage_today = {}
            for snap in snapshots:
                if snap.uuid_id not in first_usage_today:
                    total_gb = (snap.hiddify_usage_gb or 0) + (snap.marzban_usage_gb or 0)
                    first_usage_today[snap.uuid_id] = total_gb * (1024**3)

            for u in filtered:
                ident = u.get('uuid') or u.get('username')
                if ident and ident in db_id_map:
                    db_id = db_id_map[ident]
                    if db_id in first_usage_today:
                        daily = u['_used_bytes'] - first_usage_today[db_id]
                        daily_usage[ident] = max(0, daily)

        # صفحه‌بندی
        total_count = len(filtered)
        paged_users = filtered[offset : offset + limit]
        
        items = []
        for u in paged_users:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            # فرمت مصرف
            usage_bytes = daily_usage.get(ident, 0)
            usage_str = f"{usage_bytes / (1024**3):.2f} GB" if usage_bytes >= 0.01 * (1024**3) else f"{usage_bytes / (1024**2):.0f} MB"
            
            # روزهای مانده
            days_str = "?"
            try:
                if 'remaining_days' in u and u['remaining_days'] is not None:
                    days_str = f"{int(u['remaining_days'])}d"
                elif 'expire' in u and u['expire']:
                    rem = int((float(u['expire']) - datetime.now().timestamp()) / 86400)
                    days_str = f"{rem}d" if rem >= 0 else "Exp"
            except: pass

            items.append(f"• {link} \| `{escape_markdown(usage_str)}` \| `{escape_markdown(days_str)}`")

        return items, total_count, f"⚡️ *{escape_markdown(f'کاربران آنلاین ({panel_obj.name})')}*"

class ActiveUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        # فعال (۲۴ ساعت اخیر)
        window = timedelta(hours=24)
        now_utc = datetime.utcnow()
        filtered = [u for u in users if u['_parsed_last_seen'] and (now_utc - u['_parsed_last_seen']) < window]
        
        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []
        
        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            last_seen = to_shamsi(u['_parsed_last_seen'])
            percent = int((u['_used_bytes'] / u['_limit_bytes']) * 100) if u['_limit_bytes'] > 0 else 0
            
            items.append(f"• {link}{LRM} \| {RLM}{escape_markdown(last_seen)} {RLM}\| {RLM}`{percent}%`")
            
        return items, total_count, f"✅ *{escape_markdown(f'کاربران فعال ({panel_obj.name})')}*"

class InactiveUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        # غیرفعال (بین ۱ تا ۷ روز پیش)
        now = datetime.utcnow()
        filtered = []
        for u in users:
            dt = u['_parsed_last_seen']
            if dt:
                diff = now - dt
                if timedelta(days=1) <= diff < timedelta(days=7):
                    filtered.append(u)

        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            time_ago = format_relative_time(u['_parsed_last_seen'])
            
            items.append(f"• {link}{LRM} \| {RLM}{escape_markdown(time_ago)}")
            
        return items, total_count, f"⏳ *{escape_markdown(f'کاربران غیرفعال ({panel_obj.name})')}*"

class NeverConnectedStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        filtered = [u for u in users if not u['_parsed_last_seen'] or u['_used_bytes'] == 0]
        
        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            limit_gb = u.get('_limit_bytes', 0) / (1024**3)
            limit_str = f"{limit_gb:.0f}GB" if limit_gb.is_integer() else f"{limit_gb:.1f}GB"
            
            items.append(f"• {link}{LRM} \| `0/{limit_str}`")
            
        return items, total_count, f"🚫 *{escape_markdown(f'هرگز متصل نشده ({panel_obj.name})')}*"

class PanelUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        # همه کاربران
        filtered = users
        
        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            items.append(f"• {link}")
            
        return items, total_count, f"👥 *{escape_markdown(f'همه کاربران پنل {panel_obj.name}')}*"


# =========================================================
# استراتژی‌های مبتنی بر دیتابیس (DB Based)
# =========================================================

class BirthdayStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        stmt = select(User).where(User.birthday.isnot(None))
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        # سورت پایتونی
        users_sorted = sorted(users, key=lambda u: days_until_next_birthday(u.birthday) if u.birthday else 999)
        total_count = len(users_sorted)
        paged = users_sorted[offset : offset + limit]
        
        items = []
        for user in paged:
            name = escape_markdown((user.first_name or 'ناشناس').replace('|', ''))
            shamsi = to_shamsi(user.birthday)
            rem = days_until_next_birthday(user.birthday)
            days_str = "امروز! 🎉" if rem == 0 else f"{rem} روز"
            
            items.append(f"🎂 {name} \| {shamsi} \| {escape_markdown(days_str)}")
            
        return items, total_count, f"🎂 *{escape_markdown('لیست تولد کاربران')}*"

class PlanReportStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        plan_id = int(params[1])
        stmt = queries.get_users_by_plan_query(plan_id)
        
        # شمارش
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = await session.scalar(count_stmt) or 0
        
        # دریافت دیتا
        result = await session.execute(stmt.offset(offset).limit(limit))
        users = result.scalars().all()
        
        items = []
        for user in users:
            name = escape_markdown(user.first_name or "بدون نام")
            link = f"[{name}](tg://user?id={user.user_id})"
            items.append(f"• {link}{LRM} \(`{user.user_id}`\)")
            
        return items, total_count, f"📊 *{escape_markdown('گزارش بر اساس پلن')}*"

class BotUsersStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        stmt = select(User).order_by(User.user_id.desc())
        
        count_stmt = select(func.count(User.user_id))
        total_count = await session.scalar(count_stmt)
        
        result = await session.execute(stmt.offset(offset).limit(limit))
        users = result.scalars().all()
        
        items = []
        for user in users:
            name = escape_markdown(user.first_name or "بدون نام")
            link = f"[{name}](tg://user?id={user.user_id})"
            items.append(f"• {link}{LRM} \(`{user.user_id}`\)")
            
        return items, total_count, f"👥 *{escape_markdown('کل کاربران ربات')}*"