from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_plan import APIPlan


class APIPlanRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        plan_id: UUID,
    ) -> APIPlan | None:
        result = await self.db.execute(
            select(APIPlan).where(APIPlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_id(
        self,
        api_id: UUID,
    ) -> list[APIPlan]:
        result = await self.db.execute(
            select(APIPlan).where(APIPlan.api_id == api_id)
        )
        return list(result.scalars().all())

    async def create(
        self,
        **data,
    ) -> APIPlan:
        plan = APIPlan(**data)

        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)

        return plan

    async def update(
        self,
        plan: APIPlan,
        **fields,
    ) -> APIPlan:
        for field, value in fields.items():
            if value is not None:
                setattr(plan, field, value)

        await self.db.flush()
        await self.db.refresh(plan)

        return plan

    async def delete(self, plan: APIPlan) -> None:
        await self.db.delete(plan)
        await self.db.flush()