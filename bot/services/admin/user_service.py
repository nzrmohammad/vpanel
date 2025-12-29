# bot/services/admin/user_service.py

import logging
import uuid as uuid_lib
from sqlalchemy import select, or_, update
from sqlalchemy.orm import selectinload

from bot.database import db
from bot.db.base import User, UserUUID, Panel, PanelNode, ServerCategory
from bot.services.panels.factory import PanelFactory
from bot import combined_handler
from bot.utils.parsers import validate_uuid

logger = logging.getLogger(__name__)

class AdminUserService:
    """
    سرویس مرکزی مدیریت کاربران برای ادمین.
    شامل: جستجو، ساخت، ویرایش، حذف، مالی و دسترسی‌ها.
    """

    # ---------------------------------------------------------
    # 1. جستجو و دریافت اطلاعات
    # ---------------------------------------------------------
    
    async def search_users(self, query: str, search_type: str = 'global'):
        """جستجوی کاربر بر اساس کوئری"""
        async with db.get_session() as session:
            stmt = select(User).distinct().options(selectinload(User.uuids))
            
            if search_type == 'telegram_id':
                if not query.isdigit(): return []
                stmt = stmt.where(User.user_id == int(query))
            else:
                stmt = stmt.outerjoin(UserUUID).where(
                    or_(
                        User.username.ilike(f"%{query}%"),
                        User.first_name.ilike(f"%{query}%"),
                        User.last_name.ilike(f"%{query}%"),
                        UserUUID.uuid.ilike(f"%{query}%"),
                        UserUUID.name.ilike(f"%{query}%")
                    )
                )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_user_profile_data(self, target_id: int):
        """دریافت اطلاعات کامل پروفایل کاربر برای نمایش"""
        user = await db.get_user(target_id)
        if not user: return None
        
        uuids = await db.uuids(target_id)
        active_uuids = [u for u in uuids if u['is_active']]
        
        info = None
        if active_uuids:
            main_uuid = active_uuids[0]['uuid']
            info = await combined_handler.get_combined_user_info(str(main_uuid))
            if info: info['db_id'] = active_uuids[0]['id']
            
        history = await db.get_user_payment_history(uuids[0]['id']) if uuids else []
        
        return {
            "user": user,
            "uuids": uuids,
            "active_uuids": active_uuids,
            "combined_info": info,
            "payment_count": len(history)
        }

    async def purge_user(self, telegram_id: int):
        """حذف کامل کاربر از دیتابیس و پنل‌ها"""
        uuids = await db.uuids(telegram_id)
        if uuids:
            # حذف از پنل‌ها
            await combined_handler.delete_user_from_all_panels(str(uuids[0]['uuid']))
        # حذف از دیتابیس
        return await db.purge_user_by_telegram_id(telegram_id)

    # ---------------------------------------------------------
    # 2. ساخت کاربر جدید
    # ---------------------------------------------------------

    async def create_user(self, data: dict):
        """ساخت کاربر جدید در پنل‌های انتخابی"""
        panel_name_target = data['panel_name']
        name = data['name']
        limit = data['limit']
        days = data.get('days', 30)
        user_uuid = data.get('uuid')
        telegram_id = data.get('telegram_id')
        squad_uuid = data.get('squad_uuid')
        ext_squad_uuid = data.get('external_squad_uuid')

        target_panels = []
        if panel_name_target == 'all':
            target_panels = await db.get_active_panels()
        else:
            p = await db.get_panel_by_name(panel_name_target)
            if p: target_panels = [p]

        if not target_panels:
            return {"success": False, "error": "no_panel"}

        results = {"success": [], "fail": [], "uuid": user_uuid}

        for p in target_panels:
            try:
                panel_api = await PanelFactory.get_panel(p['name'])
                res = await panel_api.add_user(
                    name, limit, days, 
                    uuid=user_uuid, 
                    telegram_id=telegram_id, 
                    squad_uuid=squad_uuid,
                    external_squad_uuid=ext_squad_uuid
                )
                
                # اگر UUID نداشتیم و پنل ساخت، آن را نگه می‌داریم
                if res and res.get('uuid') and not results['uuid']:
                    results['uuid'] = res.get('uuid')
                    user_uuid = res.get('uuid') # برای دورهای بعدی حلقه

                if res: results['success'].append(p)
                else: results['fail'].append(p)

            except Exception as e:
                logger.error(f"Error creating user on {p['name']}: {e}")
                results['fail'].append(p)
                
        return results

    # ---------------------------------------------------------
    # 3. مدیریت وضعیت و منابع
    # ---------------------------------------------------------

    async def toggle_user_status(self, target_id: int, action: str, scope: str = 'all'):
        """تغییر وضعیت فعال/غیرفعال (سراسری یا تکی)"""
        uuids = await db.uuids(target_id)
        if not uuids: return {"success": False, "msg": "No UUID"}
        
        uuid_str = str(uuids[0]['uuid'])
        uuid_id = uuids[0]['id']
        new_status_bool = (action == 'enable')
        
        target_panels = []
        success_count = 0

        # آپدیت دیتابیس ربات (فقط اگر سراسری باشد)
        if scope == 'all':
            async with db.get_session() as session:
                await session.execute(update(UserUUID).where(UserUUID.id == uuid_id).values(is_active=new_status_bool))
                await session.commit()
            target_panels = await db.get_active_panels()
        else:
            try:
                p = await db.get_panel_by_id(int(scope))
                if p: target_panels = [p]
            except: pass

        for p in target_panels:
            try:
                handler = await PanelFactory.get_panel(p['name'])
                identifier = uuid_str
                # هندل کردن نام کاربری مرزبان
                if p['panel_type'] == 'marzban':
                    mapping = await db.get_marzban_username_by_uuid(uuid_str)
                    if mapping: identifier = mapping

                # فراخوانی API
                res = await self._call_panel_toggle(handler, p['panel_type'], identifier, action)
                if res: success_count += 1
            except Exception as e:
                logger.error(f"Toggle error {p['name']}: {e}")

        return {"success": True, "count": success_count, "status_bool": new_status_bool}

    async def _call_panel_toggle(self, handler, p_type, identifier, action):
        """متد داخلی برای API Call"""
        if p_type == 'marzban':
            payload = {"status": "active" if action == 'enable' else "disabled"}
            return await handler._request("PUT", f"user/{identifier}", json=payload) is not None
        elif p_type == 'hiddify':
            is_enable = (action == 'enable')
            return await handler._request("PATCH", f"user/{identifier}", json={"enable": is_enable, "is_active": is_enable, "mode": "no_reset"}) is not None
        elif p_type == 'remnawave':
            payload = {"status": "ACTIVE" if action == 'enable' else "DISABLED"}
            return await handler._request("PATCH", f"api/users/{identifier}", json=payload) is not None
        return False

    async def modify_user_resources(self, target_id: int, panel_scope: str, action_type: str, value: float):
        """افزودن/کاستن حجم یا روز"""
        uuids = await db.uuids(target_id)
        if not uuids: return False
        
        main_uuid = str(uuids[0]['uuid'])
        add_gb = value if 'gb' in action_type else 0
        add_days = int(value) if 'days' in action_type else 0
        target_name = panel_scope if panel_scope != 'all' else None
        
        return await combined_handler.modify_user_on_all_panels(
            main_uuid, add_gb=add_gb, add_days=add_days, target_panel_name=target_name
        )

    # ---------------------------------------------------------
    # 4. سایر ابزارها (مالی، نگاشت، ریست)
    # ---------------------------------------------------------

    async def get_wallet_history(self, target_id: int):
        return await db.get_wallet_history(target_id, limit=20)

    async def add_manual_payment(self, target_id: int):
        uuids = await db.uuids(target_id)
        if uuids:
            await db.add_payment_record(uuids[0]['id'])
            return True
        return False

    async def delete_payment_history(self, uuid_id: int):
        return await db.delete_user_payment_history(uuid_id)

    async def update_user_note(self, target_id: int, note: str):
        return await db.update_user_note(target_id, note)

    async def get_marzban_mappings(self):
        return await db.get_all_marzban_mappings()

    async def add_mapping(self, uuid_str, username):
        return await db.add_marzban_mapping(uuid_str, username)

    async def delete_mapping(self, uuid_str):
        return await db.delete_marzban_mapping(uuid_str)

    async def renew_user(self, target_id: int, plan_id: int):
        plan = await db.get_plan_by_id(plan_id)
        if not plan: return False
        
        uuids = await db.uuids(target_id)
        if not uuids: return False
        
        success = await combined_handler.modify_user_on_all_panels(
            str(uuids[0]['uuid']), add_gb=plan['volume_gb'], add_days=plan['days']
        )
        if success:
            await db.add_payment_record(uuids[0]['id'])
        return success

    # --- Node Access ---
    async def get_node_access_matrix(self, user_id: int):
        """دریافت ماتریس دسترسی کاربر به پنل‌ها و نودها"""
        async with db.get_session() as session:
            stmt_user = select(UserUUID).options(selectinload(UserUUID.allowed_panels)).where(UserUUID.user_id == user_id).limit(1)
            res = await session.execute(stmt_user)
            user_uuid = res.scalar_one_or_none()
            if not user_uuid: return None

            allowed_ids = {p.id for p in user_uuid.allowed_panels}
            
            cats = (await session.execute(select(ServerCategory))).scalars().all()
            panels = (await session.execute(select(Panel).where(Panel.is_active == True))).scalars().all()
            nodes = (await session.execute(select(PanelNode).where(PanelNode.is_active == True))).scalars().all()
            
            return {
                "uuid_obj": user_uuid,
                "allowed_ids": allowed_ids,
                "categories": {c.code: c.emoji for c in cats},
                "panels": panels,
                "nodes": nodes
            }

    async def toggle_node_access(self, uuid_db_id: int, panel_id: int, enable: bool):
        return await db.update_user_panel_access_by_id(uuid_db_id, panel_id, enable)

# نمونه‌سازی
admin_user_service = AdminUserService()