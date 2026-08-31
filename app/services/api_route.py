from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.api_route import APIRoute
from app.repositories.api_route import APIRouteRepository


class APIRouteService:
    def __init__(
        self,
        repository: APIRouteRepository,
    ):
        self.repository = repository

    async def get_by_id(self, route_id: UUID) -> APIRoute | None:
        return await self.repository.get_by_id(route_id)

    async def get_by_api(self, api_id: UUID) -> list[APIRoute]:
        return await self.repository.get_by_api_id(api_id)

    async def create(
        self,
        *,
        api_id: UUID,
        path: str,
        method: str,
        **data
    ) -> APIRoute:

        method = method.upper().strip()
        path = path.strip()

        existing_route = await self.repository.get_by_path_and_method(api_id, path, method)

        if existing_route:
            raise ValueError(
                "A route with this path and method "
                "already exists for this API."
            )

        try:
            route = await self.repository.create(
                api_id=api_id,
                path=path,
                method=method,
                **data,
            )
            await self.repository.db.commit()
            await self.repository.db.refresh(route)
            return route
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "A route with this path and method already exists for this API."
            ) from exc

    async def update(
            self,
            route: APIRoute,
            **data
    ) -> APIRoute:
        path = data.get("path", route.path)
        method = data.get("method", route.method)

        if path is not None:
            path = path.strip()
            data["path"] = path

        if method is not None:
            method = method.upper().strip()
            data["method"] = method

        existing_route = await self.repository.get_by_path_and_method(
            route.api_id,
            path,
            method,
        )
        if existing_route and existing_route.id != route.id:
            raise ValueError(
                "A route with this path and method already exists for this API."
            )

        try:
            updated_route = await self.repository.update(route, **data)
            await self.repository.db.commit()
            await self.repository.db.refresh(updated_route)
            return updated_route
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "A route with this path and method already exists for this API."
            ) from exc

    async def delete(
            self,
            route: APIRoute
    ) -> None:
        await self.repository.delete(route)
        await self.repository.db.commit()
