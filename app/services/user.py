from uuid import UUID

from app.models.user import User
from app.repositories.user import UserRepository


class UserService:
    def __init__(
        self,
        repository: UserRepository,
    ):
        self.repository = repository

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        return await self.repository.get_by_id(user_id)

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        return await self.repository.get_by_email(
            email.lower().strip()
        )

    async def create(
        self,
        *,
        email: str,
        password_hash: str | None = None,
        **data,
    ) -> User:
        email = email.lower().strip()

        existing_user = await self.repository.get_by_email(
            email
        )

        if existing_user is not None:
            raise ValueError(
                "A user with this email already exists."
            )

        return await self.repository.create(
            email=email,
            password_hash=password_hash,
            **data,
        )

    async def update(
        self,
        user: User,
        **data,
    ) -> User:
        return await self.repository.update(
            user,
            **data,
        )

    async def delete(
        self,
        user: User,
    ) -> None:
        await self.repository.delete(user)