from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.api import API
from app.repositories.api import APIRepository

class APIService:
    def __init__(self, repository: APIRepository):
        self.repository = repository

    async def get_by_id(self, api_id: UUID) -> API | None: 
        return await self.repository.get_by_id(api_id)

    async def get_by_organization(self, organization_id: UUID) -> list[API]:
        return await self.repository.get_by_organization_id(organization_id)

    async def get_by_slug(self, slug: str, organization_id: UUID) -> API | None:
        return await self.repository.get_by_slug(organization_id, slug)

    async def create(
            self,
            *,
            organization_id: UUID,
            name: str,
            slug: str,
            version: str,
            description: str | None = None,
            documentation: str | None = None,
            visibility= None,
            status= None,
            base_path: str | None = None
    ) -> API:

        slug = slug.lower().strip()

        existing_api = await self.repository.get_by_slug(organization_id, slug)

        if existing_api:
            raise ValueError(
                "An API with this slug already exists "
                "in this organization."
            )

        try:
            api = await self.repository.create(
                organization_id=organization_id,
                name=name,
                slug=slug,
                version=version,
                description=description,
                documentation=documentation,
                visibility=visibility,
                status=status,
                base_path=base_path,
            )
            await self.repository.db.commit()
            await self.repository.db.refresh(api)
            return api
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "An API with this slug already exists in this organization."
            ) from exc

    async def update(
        self,
        api: API,
        **data
    ) -> API:
        slug = data.get("slug")
        if slug is not None:
            slug = slug.lower().strip()

            existing_api = await self.repository.get_by_slug(api.organization_id, slug)

            if existing_api and existing_api.id != api.id:
                raise ValueError(
                    "An API with this slug already exists "
                    "in this organization."
                )

            data["slug"] = slug

        try:
            updated_api = await self.repository.update(api, **data)
            await self.repository.db.commit()
            await self.repository.db.refresh(updated_api)
            return updated_api
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "An API with this slug already exists in this organization."
            ) from exc

    async def delete(self, api: API):
        await self.repository.delete(api)
        await self.repository.db.commit()

    
