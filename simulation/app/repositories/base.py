"""Base repository class with common CRUD operations.

This module provides a generic base repository class that implements
common database operations using SQLAlchemy async sessions.
"""

from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Base


class BaseRepository[ModelType: Base]:
    """Generic repository with common CRUD operations.

    Attributes:
        model: SQLAlchemy model class.
        session: Async database session.
    """

    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        """Initialize repository with model and session.

        Args:
            model: SQLAlchemy model class.
            session: Async database session.
        """
        self.model = model
        self.session = session

    async def get_by_id(self, id: int) -> ModelType | None:
        """Get a single record by ID.

        Args:
            id: Primary key ID.

        Returns:
            Model instance or None if not found.
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        return cast("ModelType | None", result.scalar_one_or_none())

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """Get all records with pagination.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of model instances.
        """
        result = await self.session.execute(
            select(self.model)
            .order_by(self.model.id)  # type: ignore[attr-defined]
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        """Get total count of records.

        Returns:
            Total number of records.
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return cast("int", result.scalar_one())

    async def create(self, obj_in: dict[str, Any]) -> ModelType:
        """Create a new record.

        Args:
            obj_in: Dictionary of field values.

        Returns:
            Created model instance.
        """
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db_obj: ModelType,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """Update an existing record.

        Args:
            db_obj: Existing model instance.
            obj_in: Dictionary of field values to update.

        Returns:
            Updated model instance.
        """
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, db_obj: ModelType) -> None:
        """Delete a record.

        Args:
            db_obj: Model instance to delete.
        """
        await self.session.delete(db_obj)
        await self.session.flush()
