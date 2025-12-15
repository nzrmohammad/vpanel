# bot/db/product.py

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, update, delete, asc
from sqlalchemy.exc import IntegrityError

# وارد کردن مدل‌ها از فایل base
from .base import Plan, Addon, ServerCategory

logger = logging.getLogger(__name__)

class ProductDB:
    """
    مدیریت محصولات قابل فروش (پلن‌ها، افزودنی‌ها) و دسته‌بندی‌های سرور.
    این کلاس به عنوان Mixin روی DatabaseManager سوار می‌شود.
    """

    # --- مدیریت پلن‌ها (Plans) ---

    async def get_all_plans(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        لیست تمام پلن‌ها را برمی‌گرداند.
        """
        async with self.get_session() as session:
            stmt = select(Plan)
            if active_only:
                stmt = stmt.where(Plan.is_active == True)
            # مرتب‌سازی: اول بر اساس ترتیب نمایش، سپس قیمت
            stmt = stmt.order_by(Plan.display_order.asc(), Plan.price.asc())
            
            result = await session.execute(stmt)
            plans = result.scalars().all()
            
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "price": p.price,
                    "volume_gb": p.volume_gb,
                    "days": p.days,
                    "allowed_categories": p.allowed_categories, # لیست ['de', 'fr']
                    "is_active": p.is_active,
                    "display_order": p.display_order
                }
                for p in plans
            ]

    async def add_plan(self, name: str, price: float, volume_gb: float, days: int, 
                       allowed_categories: List[str] = None, description: str = None, 
                       display_order: int = 0) -> bool:
        """
        یک پلن جدید به دیتابیس اضافه می‌کند.
        """
        async with self.get_session() as session:
            new_plan = Plan(
                name=name,
                price=price,
                volume_gb=volume_gb,
                days=days,
                allowed_categories=allowed_categories or [], # ذخیره به صورت JSON
                description=description,
                display_order=display_order,
                is_active=True
            )
            session.add(new_plan)
            await session.commit()
            return True

    async def update_plan(self, plan_id: int, **kwargs) -> bool:
        """
        مشخصات یک پلن را ویرایش می‌کند.
        kwargs می‌تواند شامل name, price, is_active و ... باشد.
        """
        async with self.get_session() as session:
            stmt = update(Plan).where(Plan.id == plan_id).values(**kwargs)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def delete_plan(self, plan_id: int) -> bool:
        """یک پلن را حذف می‌کند."""
        async with self.get_session() as session:
            stmt = delete(Plan).where(Plan.id == plan_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_plan_by_id(self, plan_id: int) -> Optional[Dict[str, Any]]:
        """جزئیات یک پلن خاص را برمی‌گرداند."""
        async with self.get_session() as session:
            plan = await session.get(Plan, plan_id)
            if plan:
                return {
                    "id": plan.id, "name": plan.name, "price": plan.price,
                    "volume_gb": plan.volume_gb, "days": plan.days,
                    "allowed_categories": plan.allowed_categories,
                    "description": plan.description, "is_active": plan.is_active
                }
            return None

    # --- مدیریت افزودنی‌ها (Addons) ---

    async def get_all_addons(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """لیست بسته‌های افزودنی (حجم/زمان) را برمی‌گرداند."""
        async with self.get_session() as session:
            stmt = select(Addon)
            if active_only:
                stmt = stmt.where(Addon.is_active == True)
            stmt = stmt.order_by(Addon.display_order.asc(), Addon.price.asc())
            
            result = await session.execute(stmt)
            addons = result.scalars().all()
            
            return [
                {
                    "id": a.id, "name": a.name, "price": a.price,
                    "extra_gb": a.extra_gb, "extra_days": a.extra_days,
                    "is_active": a.is_active
                }
                for a in addons
            ]

    async def add_addon(self, name: str, price: float, extra_gb: float = 0, extra_days: int = 0) -> bool:
        """یک بسته افزودنی جدید ایجاد می‌کند."""
        async with self.get_session() as session:
            new_addon = Addon(
                name=name, price=price, 
                extra_gb=extra_gb, extra_days=extra_days,
                is_active=True
            )
            session.add(new_addon)
            await session.commit()
            return True

    # --- مدیریت دسته‌بندی سرورها (Server Categories) ---

    async def get_server_categories(self) -> List[Dict[str, Any]]:
        """
        لیست تمام دسته‌بندی‌های سرور (برای ساخت منوهای داینامیک).
        """
        async with self.get_session() as session:
            stmt = select(ServerCategory).where(ServerCategory.is_active == True).order_by(ServerCategory.display_order)
            result = await session.execute(stmt)
            return [
                {
                    "code": c.code, 
                    "name": c.name, 
                    "emoji": c.emoji, 
                    "description": c.description
                }
                for c in result.scalars().all()
            ]

    async def add_server_category(self, code: str, name: str, emoji: str, description: str = None, display_order: int = 0) -> bool:
        """
        یک دسته‌بندی جدید (مثلاً هلند nl) اضافه می‌کند.
        """
        async with self.get_session() as session:
            try:
                new_cat = ServerCategory(
                    code=code, name=name, emoji=emoji, 
                    description=description,
                    display_order=display_order, is_active=True
                )
                session.add(new_cat)
                await session.commit()
                return True
            except IntegrityError:
                return False

    async def update_server_category_name(self, code: str, new_name: str) -> bool:
        """ویرایش نام یک دسته‌بندی سرور"""
        async with self.get_session() as session:
            stmt = update(ServerCategory).where(ServerCategory.code == code).values(name=new_name)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def delete_server_category(self, code: str) -> bool:
        """حذف یک دسته‌بندی سرور"""
        async with self.get_session() as session:
            stmt = delete(ServerCategory).where(ServerCategory.code == code)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0