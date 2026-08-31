from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_route import APIRoute


class APIRouteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        route_id: UUID,
    ) -> APIRoute | None:
        result = await self.db.execute(
            select(APIRoute).where(APIRoute.id == route_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_id(
        self,
        api_id: UUID,
    ) -> list[APIRoute]:
        result = await self.db.execute(
            select(APIRoute).where(
                APIRoute.api_id == api_id
            )
        )
        return list(result.scalars().all())

    async def get_by_path_and_method(
        self,
        api_id: UUID,
        path: str,
        method: str,
    ) -> APIRoute | None:
        result = await self.db.execute(
            select(APIRoute).where(
                APIRoute.api_id == api_id,
                APIRoute.path == path,
                APIRoute.method == method,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        **data,
    ) -> APIRoute:
        route = APIRoute(**data)

        self.db.add(route)
        await self.db.flush()
        await self.db.refresh(route)

        return route

    async def update(
        self,
        route: APIRoute,
        **fields,
    ) -> APIRoute:
        for field, value in fields.items():
            if value is not None:
                setattr(route, field, value)

        await self.db.flush()
        await self.db.refresh(route)

        return route

    async def delete(self, route: APIRoute) -> None:
        await self.db.delete(route)
        await self.db.flush()