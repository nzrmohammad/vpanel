# bot/services/user_modifier.py

import logging
import asyncio
from typing import Optional
from bot.database import db
from bot.services.panels.factory import PanelFactory
from bot.utils.parsers import validate_uuid

logger = logging.getLogger(__name__)

async def _get_handler(panel_name: str):
    try:
        return await PanelFactory.get_panel(panel_name)
    except:
        return None

async def modify_user_logic(
    identifier: str,
    add_gb: float = 0,
    add_days: int = 0,
    set_gb: Optional[float] = None,
    set_days: Optional[int] = None,
    target_panel_type: Optional[str] = None,
    target_panel_name: Optional[str] = None
) -> bool:
    """
    اعمال تغییرات روی کاربران (هوشمند نسبت به مپینگ مرزبان)
    """
    logger.info(f"Modifier: Processing {identifier}")

    # --- 1. RESOLVE IDENTITY (Marzban Mapping) ---
    is_uuid = validate_uuid(identifier)
    uuid = identifier if is_uuid else await db.get_uuid_by_marzban_username(identifier)
    marzban_username = await db.get_marzban_username_by_uuid(identifier) if is_uuid else identifier

    # اگر هیچکدام پیدا نشد، یعنی کاربر وجود ندارد
    if not uuid and not marzban_username:
        logger.error(f"❌ Modifier: Identifier '{identifier}' not resolved.")
        return False
        
    all_panels = await db.get_active_panels()

    async def modify_single(panel_config):
        ptype = panel_config['panel_type']
        pname = panel_config['name']

        if target_panel_type and ptype != target_panel_type: return False
        if target_panel_name and pname != target_panel_name: return False

        handler = await _get_handler(pname)
        if not handler: return False

        success = False
        try:
            # اگر پنل هیدیفای/رمنا است -> با UUID کار کن
            if ptype in ['hiddify', 'remnawave'] and uuid:
                if await handler.modify_user(uuid, add_gb=add_gb, add_days=add_days):
                    success = True
            
            # اگر پنل مرزبان است -> با Username کار کن
            elif ptype == 'marzban' and marzban_username:
                if await handler.modify_user(marzban_username, add_gb=add_gb, add_days=add_days):
                    success = True
        except Exception as e:
            logger.error(f"Error modifying {pname}: {e}")
        
        return success

    tasks = [modify_single(p) for p in all_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    any_success = any(res is True for res in results)

    # ریست کردن یادآوری تمدید
    if any_success and (add_days > 0 or set_days is not None) and uuid:
        uuid_id = await db.get_uuid_id_by_uuid(uuid)
        if uuid_id:
            await db.reset_renewal_reminder_sent(uuid_id)
            
    return any_success

async def delete_user_logic(identifier: str, user_breakdown: Optional[dict] = None) -> bool:
    """حذف کاربر از همه جا با در نظر گرفتن مپینگ"""
    is_uuid = validate_uuid(identifier)
    uuid = identifier if is_uuid else await db.get_uuid_by_marzban_username(identifier)
    marzban_username = identifier if not is_uuid else await db.get_marzban_username_by_uuid(identifier)

    all_panels = await db.get_all_panels()

    async def delete_single(panel_config):
        handler = await _get_handler(panel_config['name'])
        if not handler: return True
        
        ptype = panel_config['panel_type']
        try:
            if ptype in ['hiddify', 'remnawave'] and uuid:
                return await handler.delete_user(uuid)
            elif ptype == 'marzban' and marzban_username:
                return await handler.delete_user(marzban_username)
        except:
            return False
        return True

    tasks = [delete_single(p) for p in all_panels]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    if uuid:
        await db.delete_user_by_uuid(uuid)
        
    return all(r is not False for r in results)