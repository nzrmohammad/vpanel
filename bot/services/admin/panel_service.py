# bot/services/admin/panel_service.py

import logging
from bot.database import db

logger = logging.getLogger(__name__)

class PanelService:
    """
    سرویس جامع مدیریت پنل‌ها و نودها.
    تمام عملیات دیتابیس مربوط به سرورها از این طریق انجام می‌شود.
    """

    async def get_all_panels(self):
        """دریافت لیست همه پنل‌ها"""
        return await db.get_all_panels()

    async def add_new_panel(self, name: str, p_type: str, url: str, t1: str, t2: str = None, cat: str = 'ir'):
        """افزودن پنل جدید با هندل کردن خطاها"""
        try:
            # اینجا می‌توان تست اتصال هم اضافه کرد
            result = await db.add_panel(
                name=name,
                panel_type=p_type,
                api_url=url,
                token1=t1,
                token2=t2,
                category=cat
            )
            return {"success": result, "error": None if result else "duplicate_name"}
        except Exception as e:
            logger.error(f"Error adding panel: {e}")
            return {"success": False, "error": str(e)}

    async def get_panel_details_full(self, panel_id: int):
        """دریافت همزمان پنل و نودهایش"""
        panel = await db.get_panel_by_id(panel_id)
        if not panel:
            return None
        nodes = await db.get_panel_nodes(panel_id)
        return {"panel": panel, "nodes": nodes}

    async def update_panel_name(self, panel_id: int, new_name: str):
        return await db.update_panel_name(panel_id, new_name)

    async def delete_panel(self, panel_id: int):
        return await db.delete_panel(panel_id)

    async def toggle_panel_status(self, panel_id: int):
        return await db.toggle_panel_status(panel_id)

    # --- متدهای مدیریت نود (Node Management) ---

    async def add_node(self, panel_id: int, name: str, country_code: str, flag: str):
        return await db.add_panel_node(panel_id, name, country_code, flag)

    async def get_node(self, node_id: int):
        return await db.get_panel_node_by_id(node_id)

    async def rename_node(self, node_id: int, new_name: str):
        return await db.update_panel_node_name(node_id, new_name)

    async def delete_node(self, node_id: int):
        return await db.delete_panel_node(node_id)

    async def toggle_node_status(self, node_id: int):
        return await db.toggle_panel_node_status(node_id)

# نمونه‌سازی
panel_service = PanelService()