# bot/db/panel.py

import logging
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, delete, not_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

# وارد کردن مدل‌ها
from .base import (
    Panel, MarzbanMapping, ConfigTemplate, UserUUID, 
    UserGeneratedConfig, UUIDPanelAccess
)

# ایمپورت ACCESS_TEMPLATES فقط برای استفاده از کلیدهای قدیمی در تبدیل
try:
    from ..config import ACCESS_TEMPLATES
except ImportError:
    ACCESS_TEMPLATES = {}
    logging.warning("Could not import ACCESS_TEMPLATES from config.")

logger = logging.getLogger(__name__)

class PanelDB:
    """
    کلاسی برای مدیریت پنل‌ها و دسترسی‌های داینامیک.
    """

    # --- مدیریت پنل‌ها ---

    async def add_panel(self, name: str, panel_type: str, api_url: str, 
                        token1: str, token2: Optional[str] = None, category: str = 'general') -> bool:
        """
        یک پنل جدید با دسته‌بندی (Category/Location) اضافه می‌کند.
        """
        async with self.get_session() as session:
            try:
                new_panel = Panel(
                    name=name,
                    panel_type=panel_type,
                    category=category,  # ستون جدید
                    api_url=api_url,
                    api_token1=token1,
                    api_token2=token2
                )
                session.add(new_panel)
                await session.commit()
                return True
            except IntegrityError:
                logger.warning(f"Attempted to add a panel with a duplicate name: {name}")
                return False

    async def get_all_panels(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(Panel).order_by(Panel.name.asc())
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.scalars().all()]

    async def get_active_panels(self) -> List[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(Panel).where(Panel.is_active == True).order_by(Panel.name.asc())
            result = await session.execute(stmt)
            return [dict(row._mapping) for row in result.scalars().all()]

    async def delete_panel(self, panel_id: int) -> bool:
        async with self.get_session() as session:
            stmt = delete(Panel).where(Panel.id == panel_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def toggle_panel_status(self, panel_id: int) -> bool:
        async with self.get_session() as session:
            stmt = update(Panel).where(Panel.id == panel_id).values(is_active=not_(Panel.is_active))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_panel_by_id(self, panel_id: int) -> Optional[Dict[str, Any]]:
        async with self.get_session() as session:
            panel = await session.get(Panel, panel_id)
            if panel:
                return {
                    "id": panel.id, "name": panel.name, "panel_type": panel.panel_type,
                    "category": panel.category, # اضافه شده
                    "api_url": panel.api_url, "api_token1": panel.api_token1,
                    "api_token2": panel.api_token2, "is_active": panel.is_active
                }
            return None
            
    async def get_panel_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        async with self.get_session() as session:
            stmt = select(Panel).where(Panel.name == name)
            result = await session.execute(stmt)
            panel = result.scalar_one_or_none()
            if panel:
                return {
                    "id": panel.id, "name": panel.name, "panel_type": panel.panel_type,
                    "category": panel.category,
                    "api_url": panel.api_url, "api_token1": panel.api_token1,
                    "api_token2": panel.api_token2, "is_active": panel.is_active
                }
            return None

    async def update_panel_name(self, panel_id: int, new_name: str) -> bool:
        async with self.get_session() as session:
            try:
                stmt = update(Panel).where(Panel.id == panel_id).values(name=new_name)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except IntegrityError:
                return False

    # --- مدیریت دسترسی‌ها (Access Management) ---

    async def apply_access_template(self, uuid_id: int, plan_category: str) -> bool:
        """
        قالب دسترسی قدیمی را به دسته‌بندی‌های جدید ترجمه کرده و اعمال می‌کند.
        """
        template = ACCESS_TEMPLATES.get(plan_category, ACCESS_TEMPLATES.get('default', {}))
        if not template:
            logging.error(f"Access template '{plan_category}' not found.")
            return False

        # استخراج دسته‌بندی‌های مجاز از کلیدهای قالب قدیمی
        # مثلاً اگر 'has_access_de': True باشد، دسته 'de' را اضافه می‌کنیم.
        allowed_categories = []
        for key, value in template.items():
            if value is True and key.startswith('has_access_'):
                # تبدیل 'has_access_de' به 'de'
                cat = key.replace('has_access_', '')
                allowed_categories.append(cat)

        return await self.grant_access_by_category(uuid_id, allowed_categories)

    async def grant_access_by_category(self, uuid_id: int, categories: List[str]) -> bool:
        """
        به UUID اجازه دسترسی به تمام پنل‌های موجود در دسته‌بندی‌های خاص را می‌دهد.
        """
        async with self.get_session() as session:
            # 1. UUID را به همراه پنل‌های فعلی لود می‌کنیم
            stmt_uuid = select(UserUUID).where(UserUUID.id == uuid_id).options(selectinload(UserUUID.allowed_panels))
            result_uuid = await session.execute(stmt_uuid)
            uuid_obj = result_uuid.scalar_one_or_none()
            
            if not uuid_obj: return False

            # 2. پیدا کردن تمام پنل‌های موجود در این دسته‌بندی‌ها
            stmt_panels = select(Panel).where(Panel.category.in_(categories))
            result_panels = await session.execute(stmt_panels)
            panels_to_add = result_panels.scalars().all()

            # 3. افزودن هوشمند (جلوگیری از تکرار)
            current_panel_ids = {p.id for p in uuid_obj.allowed_panels}
            
            for p in panels_to_add:
                if p.id not in current_panel_ids:
                    uuid_obj.allowed_panels.append(p)
            
            await session.commit()
            
        logging.info(f"Access to categories {categories} granted for uuid {uuid_id}.")
        return True

    async def revoke_access_by_category(self, uuid_id: int, category: str):
        """دسترسی به یک دسته‌بندی خاص را از UUID می‌گیرد."""
        async with self.get_session() as session:
            uuid_obj = await session.get(UserUUID, uuid_id) # بهتر است با option لود شود اما اینجا lazy هم کار می‌کند
            if uuid_obj:
                # باید پنل‌ها را لود کنیم
                await session.refresh(uuid_obj, ['allowed_panels'])
                
                # فیلتر کردن لیست: آن‌هایی که کتگوری‌شان مساوی نیست بمانند
                uuid_obj.allowed_panels = [
                    p for p in uuid_obj.allowed_panels if p.category != category
                ]
                await session.commit()

    async def get_user_allowed_panels(self, uuid_id: int) -> List[Dict[str, Any]]:
        """لیست پنل‌هایی که کاربر به آن‌ها دسترسی دارد."""
        async with self.get_session() as session:
            stmt = select(UserUUID).where(UserUUID.id == uuid_id).options(selectinload(UserUUID.allowed_panels))
            result = await session.execute(stmt)
            uuid_obj = result.scalar_one_or_none()
            
            if uuid_obj:
                return [
                    {
                        "id": p.id, "name": p.name, "type": p.panel_type, 
                        "url": p.api_url, "category": p.category
                    }
                    for p in uuid_obj.allowed_panels
                ]
            return []

    # --- توابع مربوط به مپینگ مرزبان (Marzban Mapping) ---
    async def add_marzban_mapping(self, hiddify_uuid: str | uuid.UUID, marzban_username: str) -> bool:
        async with self.get_session() as session:
            try:
                uuid_obj = hiddify_uuid if isinstance(hiddify_uuid, uuid.UUID) else uuid.UUID(str(hiddify_uuid))
                
                mapping = MarzbanMapping(
                    hiddify_uuid=uuid_obj,
                    marzban_username=marzban_username
                )
                await session.merge(mapping)
                await session.commit()
                return True
            except (IntegrityError, ValueError):
                return False

    async def get_marzban_username_by_uuid(self, hiddify_uuid: str | uuid.UUID) -> Optional[str]:
        async with self.get_session() as session:
            try:
                uuid_obj = hiddify_uuid if isinstance(hiddify_uuid, uuid.UUID) else uuid.UUID(str(hiddify_uuid))
                mapping = await session.get(MarzbanMapping, uuid_obj)
                return mapping.marzban_username if mapping else None
            except ValueError:
                return None

    async def get_all_marzban_mappings(self) -> List[Dict[str, str]]:
        async with self.get_session() as session:
            stmt = select(MarzbanMapping).order_by(MarzbanMapping.marzban_username)
            result = await session.execute(stmt)
            return [{"hiddify_uuid": r.hiddify_uuid, "marzban_username": r.marzban_username} for r in result.scalars().all()]

    async def delete_marzban_mapping(self, hiddify_uuid: str | uuid.UUID) -> bool:
        async with self.get_session() as session:
            try:
                uuid_obj = hiddify_uuid if isinstance(hiddify_uuid, uuid.UUID) else uuid.UUID(str(hiddify_uuid))
                stmt = delete(MarzbanMapping).where(MarzbanMapping.hiddify_uuid == uuid_obj)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except ValueError:
                return False

    # --- توابع مربوط به قالب‌های کانفیگ ---

    async def add_batch_templates(self, templates: list[str]) -> int:
        if not templates: return 0
        
        def detect_server_type(config_str: str) -> str:
            config_lower = config_str.lower()
            if "🇮🇷" in config_str: return 'ir'            
            elif "🇩🇪" in config_str: return 'de'
            elif "🇫🇷" in config_str: return 'fr'
            elif "🇹🇷" in config_str: return 'tr'
            elif "🇺🇸" in config_str: return 'us'
            elif "🇷🇴" in config_str: return 'ro'
            elif "support" in config_lower: return 'supp'
            return 'none'

        async with self.get_session() as session:
            new_templates = [
                ConfigTemplate(template_str=tpl, server_type=detect_server_type(tpl))
                for tpl in templates
            ]
            session.add_all(new_templates)
            await session.commit()
            return len(new_templates)

    async def update_template(self, template_id: int, new_template_str: str) -> bool:
        async with self.get_session() as session:
            stmt = update(ConfigTemplate).where(ConfigTemplate.id == template_id).values(template_str=new_template_str)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_all_config_templates(self) -> list[dict]:
        async with self.get_session() as session:
            stmt = select(ConfigTemplate).order_by(ConfigTemplate.id.asc())
            result = await session.execute(stmt)
            return [dict(r._mapping) for r in result.scalars().all()]

    async def get_active_config_templates(self) -> list[dict]:
        async with self.get_session() as session:
            stmt = select(ConfigTemplate).where(ConfigTemplate.is_active == True).order_by(ConfigTemplate.id.asc())
            result = await session.execute(stmt)
            return [dict(r._mapping) for r in result.scalars().all()]

    async def toggle_template_status(self, template_id: int):
        async with self.get_session() as session:
            stmt = update(ConfigTemplate).where(ConfigTemplate.id == template_id).values(is_active=not_(ConfigTemplate.is_active))
            await session.execute(stmt)
            await session.commit()

    async def delete_template(self, template_id: int):
        async with self.get_session() as session:
            stmt = delete(ConfigTemplate).where(ConfigTemplate.id == template_id)
            await session.execute(stmt)
            await session.commit()

    async def toggle_template_special(self, template_id: int):
        async with self.get_session() as session:
            stmt = update(ConfigTemplate).where(ConfigTemplate.id == template_id).values(is_special=not_(ConfigTemplate.is_special))
            await session.execute(stmt)
            await session.commit()
    
    async def toggle_template_random_pool(self, template_id: int) -> bool:
        async with self.get_session() as session:
            stmt = update(ConfigTemplate).where(ConfigTemplate.id == template_id).values(is_random_pool=not_(ConfigTemplate.is_random_pool))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def set_template_server_type(self, template_id: int, server_type: str):
        async with self.get_session() as session:
            stmt = update(ConfigTemplate).where(ConfigTemplate.id == template_id).values(server_type=server_type)
            await session.execute(stmt)
            await session.commit()

    async def reset_templates_table(self):
        async with self.get_session() as session:
            await session.execute(delete(ConfigTemplate))
            await session.commit()
        logger.info("Config templates table has been reset.")
    
    async def get_user_config(self, user_uuid_id: int, template_id: int) -> dict | None:
        async with self.get_session() as session:
            stmt = select(UserGeneratedConfig).where(
                and_(UserGeneratedConfig.user_uuid_id == user_uuid_id, UserGeneratedConfig.template_id == template_id)
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            if config:
                return {
                    "id": config.id, "user_uuid_id": config.user_uuid_id,
                    "template_id": config.template_id, "generated_uuid": config.generated_uuid
                }
            return None

    async def add_user_config(self, user_uuid_id: int, template_id: int, generated_uuid: str) -> None:
        async with self.get_session() as session:
            new_config = UserGeneratedConfig(
                user_uuid_id=user_uuid_id, template_id=template_id, generated_uuid=generated_uuid
            )
            session.add(new_config)
            await session.commit()

    async def get_templates_by_pool_status(self) -> tuple[list[dict], list[dict]]:
        all_templates = await self.get_active_config_templates()
        random_pool = [tpl for tpl in all_templates if tpl.get('is_random_pool')]
        fixed_pool = [tpl for tpl in all_templates if not tpl.get('is_random_pool')]
        return random_pool, fixed_pool