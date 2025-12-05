# bot/db/admin_log.py

import logging
from typing import Dict, Any, List
from sqlalchemy import select, desc
from .base import AdminLog, DatabaseManager

logger = logging.getLogger(__name__)

class AdminLogDB:
    """مدیریت لاگ‌های ادمین"""

    async def log_admin_action(self, admin_id: int, action: str, target_id: str = None, details: dict = None):
        """ثبت یک لاگ جدید"""
        async with self.get_session() as session:
            log = AdminLog(
                admin_id=admin_id,
                action=action,
                target_id=str(target_id) if target_id else None,
                details=details or {}
            )
            session.add(log)

    async def get_admin_logs(self, limit: int = 50, admin_id: int = None) -> List[Dict[str, Any]]:
        """دریافت آخرین لاگ‌ها"""
        async with self.get_session() as session:
            stmt = select(AdminLog).order_by(desc(AdminLog.created_at)).limit(limit)
            
            if admin_id:
                stmt = stmt.where(AdminLog.admin_id == admin_id)
                
            result = await session.execute(stmt)
            return [
                {
                    "admin_id": r.admin_id,
                    "action": r.action,
                    "target": r.target_id,
                    "details": r.details,
                    "time": r.created_at
                }
                for r in result.scalars()
            ]