from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def create(
            self, 
            *,
            email: str,
            password_hash: str,
            first_name: str | None = None,
            last_name: str | None = None
    ) -> User:

        user = User(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name
        )

        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        return user

    async def update(
            self,
            user: User,
            **fields
    ) -> User:
        for field, value in fields.items():
            if value is not None:
                setattr(user, field, value)

        await self.db.flush()
        await self.db.refresh(user)

        return user


    async def delete(self, user: User) -> None:
        await self.db.delete(user)
        await self.db.flush()