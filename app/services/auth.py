from uuid import UUID

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (create_access_token, create_refresh_token, hash_password, decode_token, verify_password)

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.provisioning import (
    RoleNotFoundError,
    UserProvisioningService,
)

from app.schemas.auth import (RegisterRequest, LoginRequest, TokenResponse, RefreshTokenRequest)

class EmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

        self.user_repository = UserRepository(db)
        self.provisioning_service = UserProvisioningService(db)

    async def register(self, req: RegisterRequest) -> User:
        existing_user = await self.user_repository.get_by_email(req.email)

        if existing_user is not None:
            raise EmailAlreadyExistsError("A user with this email already exists")

        try:
            hashed_password = hash_password(req.password)

            user = await self.provisioning_service.create_user_with_owner_organization(
                email=req.email,
                password_hash=hashed_password,
                organization_name=req.organization_name,
                first_name=req.first_name,
                last_name=req.last_name,
            )

            await self.db.commit()
            await self.db.refresh(user)

            return user

        except EmailAlreadyExistsError:
            await self.db.rollback()
            raise
        except IntegrityError as exc:
            await self.db.rollback()
            raise EmailAlreadyExistsError("A user with this email or organization already exists") from exc
        except Exception:
            await self.db.rollback()
            raise

    async def authenticate(self, data: LoginRequest) -> User:
        user = await self.user_repository.get_by_email(data.email)

        if user is None:
            raise InvalidCredentialsError(
                "Invalid email or password"
            )

        if not user.is_active:
            raise InvalidCredentialsError(
                "User account is inactive"
            )

        if user.password_hash is None or not verify_password(data.password, user.password_hash):
            raise InvalidCredentialsError(
                "Invalid email or password"
            )

        return user

    def create_token(self, user: User) -> TokenResponse:
         access_token = create_access_token(
              subject=str(user.id)
         )

         refresh_token = create_refresh_token(
              subject=str(user.id)
         )

         return TokenResponse(
              access_token=access_token,
              refresh_token=refresh_token
         )

    async def login(self, data: LoginRequest) -> TokenResponse:
         user = await self.authenticate(data)

         return self.create_token(user)

    async def refresh_token(self, data: RefreshTokenRequest) -> TokenResponse:
         try:
              payload = decode_token(data.refresh_token)

         except JWTError as exc:
            raise InvalidTokenError(
                "Invalid or expired refresh token"
            ) from exc

         if payload.get("type") != "refresh":
            raise InvalidTokenError(
                "Invalid token type"
            )

         subject = payload.get("sub")

         if subject is None:
              raise InvalidTokenError(
                   "Invalid token subject"
              )

         try:
              user_id = UUID(subject)

         except (ValueError, TypeError, AttributeError) as exc:
              raise InvalidTokenError(
                "Invalid token subject"
            ) from exc

         user = await self.user_repository.get_by_id(user_id=user_id)

         if user is None or not user.is_active:
            raise InvalidTokenError(
                "User is unavailable"
            )

         return self.create_token(user)


    