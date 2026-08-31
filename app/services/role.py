from uuid import UUID

from app.models.role import Role
from app.repositories.role import RoleRepository

class RoleService:
    def __init__(self, repository: RoleRepository):
        self.repository = repository

    async def get_by_id(self, role_id: UUID) -> Role | None:
        return await self.repository.get_by_id(role_id)

    async def get_by_name(self, name: str) -> Role | None:
        return await self.repository.get_by_name(name)

    async def get_all(self) -> list[Role]:
        return await self.repository.get_all()
