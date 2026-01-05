# bot/services/context_service.py
import time
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from bot.database import db
from bot.db.base import ServerCategory, Panel, PanelNode, UserUUID, User

# کش ساده برای کاهش بار دیتابیس
_CACHE = {
    "cat_map": {"data": {}, "time": 0},
    "panel_map": {"data": {}, "time": 0}
}
CACHE_TTL = 300  # 5 دقیقه

class ContextService:
    @staticmethod
    async def get_category_map():
        """نقشه کد دسته‌بندی به ایموجی"""
        now = time.time()
        if now - _CACHE["cat_map"]["time"] < CACHE_TTL:
            return _CACHE["cat_map"]["data"]

        async with db.get_session() as session:
            stmt = select(ServerCategory)
            result = await session.execute(stmt)
            cats = result.scalars().all()
            data = {c.code: c.emoji for c in cats}
            
            _CACHE["cat_map"] = {"data": data, "time": now}
            return data

    @staticmethod
    async def get_panel_map_data():
        """دریافت اطلاعات پنل‌ها و نودها"""
        now = time.time()
        if now - _CACHE["panel_map"]["time"] < CACHE_TTL:
            return _CACHE["panel_map"]["data"]
            
        async with db.get_session() as session:
            panels_res = await session.execute(select(Panel))
            all_panels = panels_res.scalars().all()
            
            nodes_res = await session.execute(select(PanelNode).where(PanelNode.is_active == True))
            all_nodes = nodes_res.scalars().all()
            
            cat_emoji_map = await ContextService.get_category_map()
            
            panel_map = {}
            for p in all_panels:
                p_nodes = [n for n in all_nodes if n.panel_id == p.id]
                main_flag = cat_emoji_map.get(p.category, "")
                
                info = {
                    "id": str(p.id),
                    "nodes": p_nodes,
                    "main_flag": main_flag,
                    "category": p.category
                }
                panel_map[p.name] = info
                panel_map[p.name.strip()] = info

            _CACHE["panel_map"] = {"data": panel_map, "time": now}
            return panel_map

    @staticmethod
    async def get_user_context_full(uuid_str: str):
        """دریافت تمام اطلاعات مورد نیاز برای نمایش پروفایل کاربر"""
        async with db.get_session() as session:
            # دریافت UUID و پنل‌های مجاز
            stmt = select(UserUUID).where(UserUUID.uuid == uuid_str).options(selectinload(UserUUID.allowed_panels))
            result = await session.execute(stmt)
            user_uuid_obj = result.scalar_one_or_none()

            panel_cat_map = {} 
            user_categories = set()
            user_id = None
            user_settings = {}

            if user_uuid_obj:
                user_id = user_uuid_obj.user_id
                if user_uuid_obj.allowed_panels:
                    for panel in user_uuid_obj.allowed_panels:
                        if panel.category:
                            panel_cat_map[panel.name] = panel.category
                            user_categories.add(panel.category)
                
                # دریافت تنظیمات کاربر اصلی
                if user_id:
                    user_obj = await session.get(User, user_id)
                    if user_obj and user_obj.settings:
                        user_settings = user_obj.settings

        return {
            "user_id": user_id,
            "panel_cat_map": panel_cat_map,
            "user_categories": user_categories,
            "settings": user_settings,
            "uuid_obj": user_uuid_obj
        }