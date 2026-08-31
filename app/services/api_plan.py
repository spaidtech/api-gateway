from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.api_plan import APIPlan
from app.repositories.api_plan import APIPlanRepository


class APIPlanService:
    def __init__(
        self,
        repository: APIPlanRepository,
    ):
        self.repository = repository

    async def get_by_id(self, plan_id: UUID) -> APIPlan | None:
        return await self.repository.get_by_id(plan_id)

    async def get_by_api(self, api_id: UUID) -> list[APIPlan]:
        return await self.repository.get_by_api_id(api_id)

    async def create(
            self,
            **data
    ) -> APIPlan:
        plan = await self.repository.create(**data)
        await self.repository.db.commit()
        await self.repository.db.refresh(plan)
        return plan

    async def update(
            self,
            plan: APIPlan,
            **data
    ) -> APIPlan:
        plan = await self.repository.update(plan, **data)
        await self.repository.db.commit()
        await self.repository.db.refresh(plan)
        return plan

    async def delete(self, plan: APIPlan) -> None:
        try:
            await self.repository.delete(plan)
            await self.repository.db.commit()
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "Cannot delete API plan because it is referenced by existing subscriptions."
            ) from exc
