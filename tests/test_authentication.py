from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from app.api.routes.auth import _select_verified_github_email
from app.core.config import Setting, settings, validate_security_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.dependencies import auth as auth_dependencies
from app.schemas.auth import LoginRequest, RegisterRequest, RefreshTokenRequest
from app.services.auth import (
    AuthService,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.services.oauth.github import GithubOAuthProvider
from app.services.oauth.google import GoogleOAuthProvider
from app.services.oauth.service import OAuthService
from app.services.provisioning import UserProvisioningService


class FakeDatabase:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, item):
        return item


class FakeUsers:
    def __init__(self, user=None):
        self.user = user
        self.created = []

    async def get_by_email(self, email):
        return self.user

    async def get_by_id(self, user_id):
        if self.user is not None and self.user.id == user_id:
            return self.user
        return None

    async def create(self, **fields):
        user = SimpleNamespace(
            id=uuid4(),
            email=fields["email"],
            password_hash=fields["password_hash"],
            is_active=True,
        )
        self.created.append(user)
        self.user = user
        return user


class FakeOrganizations:
    def __init__(self, existing_slugs=None):
        self.created = []
        self.existing_slugs = set(existing_slugs or [])

    async def get_by_slug(self, slug):
        return SimpleNamespace(slug=slug) if slug in self.existing_slugs else None

    async def create(self, **fields):
        organization = SimpleNamespace(id=uuid4(), **fields)
        self.created.append(organization)
        return organization


class FakeRoles:
    def __init__(self, role=None):
        self.role = role or SimpleNamespace(id=uuid4(), name="owner")

    async def get_by_name(self, name):
        return self.role if name == "owner" else None


class FakeMemberships:
    def __init__(self):
        self.created = []

    async def create(self, **fields):
        membership = SimpleNamespace(id=uuid4(), **fields)
        self.created.append(membership)
        return membership


class FakeAccounts:
    def __init__(self, account=None):
        self.account = account
        self.created = []

    async def get_by_provider_account(self, **fields):
        return self.account

    async def create(self, **fields):
        account = SimpleNamespace(**fields)
        self.created.append(account)
        return account


class FakeProvisioning:
    def __init__(self):
        self.calls = []

    async def create_user_with_owner_organization(self, **fields):
        self.calls.append(fields)
        return SimpleNamespace(
            id=uuid4(),
            email=fields["email"],
            password_hash=fields["password_hash"],
            is_active=True,
        )


def make_auth(users=None, provisioning=None):
    service = AuthService.__new__(AuthService)
    service.db = FakeDatabase()
    service.user_repository = users or FakeUsers()
    service.provisioning_service = provisioning or FakeProvisioning()
    return service


def make_oauth(users, accounts, provisioning=None):
    service = OAuthService.__new__(OAuthService)
    service.db = FakeDatabase()
    service.user_repository = users
    service.oauth_repository = accounts
    service.provisioning_service = provisioning or FakeProvisioning()
    return service


@pytest.mark.asyncio
async def test_registration_hashes_password_and_provisions_owner_membership():
    provisioning = UserProvisioningService.__new__(UserProvisioningService)
    provisioning.user_repository = FakeUsers()
    provisioning.organization_repository = FakeOrganizations()
    provisioning.role_repository = FakeRoles()
    provisioning.organization_member_repository = FakeMemberships()

    password_hash = hash_password("correct-password")
    user = await provisioning.create_user_with_owner_organization(
        email="new@example.com",
        password_hash=password_hash,
        organization_name="New Workspace",
    )

    assert user.password_hash != "correct-password"
    assert len(provisioning.organization_repository.created) == 1
    assert len(provisioning.organization_member_repository.created) == 1
    membership = provisioning.organization_member_repository.created[0]
    assert membership.user_id == user.id
    assert membership.organization_id == provisioning.organization_repository.created[0].id
    assert membership.role_id == provisioning.role_repository.role.id


@pytest.mark.asyncio
async def test_provisioning_avoids_duplicate_organization_slugs():
    provisioning = UserProvisioningService.__new__(UserProvisioningService)
    provisioning.user_repository = FakeUsers()
    provisioning.organization_repository = FakeOrganizations({"new-workspace"})
    provisioning.role_repository = FakeRoles()
    provisioning.organization_member_repository = FakeMemberships()

    user = await provisioning.create_user_with_owner_organization(
        email="another@example.com",
        password_hash=None,
        organization_name="New Workspace",
    )

    assert provisioning.organization_repository.created[0].slug.startswith("new-workspace-")
    assert provisioning.organization_member_repository.created[0].user_id == user.id


@pytest.mark.asyncio
async def test_registration_success_and_duplicate_email():
    provisioning = FakeProvisioning()
    auth = make_auth(users=FakeUsers(), provisioning=provisioning)
    request = RegisterRequest(
        email="new@example.com",
        password="correct-password",
        organization_name="New Workspace",
    )

    user = await auth.register(request)
    assert user.email == "new@example.com"
    assert provisioning.calls[0]["password_hash"] != request.password

    duplicate_auth = make_auth(
        users=FakeUsers(SimpleNamespace(id=uuid4())),
        provisioning=FakeProvisioning(),
    )
    with pytest.raises(EmailAlreadyExistsError):
        await duplicate_auth.register(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user,password,expected",
    [
        (SimpleNamespace(id=uuid4(), is_active=True, password_hash=hash_password("secret")), "secret", True),
        (SimpleNamespace(id=uuid4(), is_active=True, password_hash=hash_password("secret")), "wrong", False),
        (None, "secret", False),
        (SimpleNamespace(id=uuid4(), is_active=False, password_hash=hash_password("secret")), "secret", False),
    ],
)
async def test_login_cases(user, password, expected):
    auth = make_auth(users=FakeUsers(user))
    if expected:
        tokens = await auth.login(LoginRequest(email="user@example.com", password=password))
        assert decode_token(tokens.access_token)["type"] == "access"
    else:
        with pytest.raises(InvalidCredentialsError):
            await auth.login(LoginRequest(email="user@example.com", password=password))


@pytest.mark.asyncio
async def test_refresh_token_type_expiry_and_subject_validation():
    user = SimpleNamespace(id=uuid4(), is_active=True)
    auth = make_auth(users=FakeUsers(user))

    tokens = await auth.refresh_token(
        RefreshTokenRequest(refresh_token=create_refresh_token(str(user.id)))
    )
    assert decode_token(tokens.access_token)["type"] == "access"

    with pytest.raises(InvalidTokenError):
        await auth.refresh_token(RefreshTokenRequest(refresh_token=create_access_token(str(user.id))))

    expired = create_refresh_token(str(user.id), extra_claims={"exp": 1})
    with pytest.raises(InvalidTokenError):
        await auth.refresh_token(RefreshTokenRequest(refresh_token=expired))

    malformed = jwt.encode(
        {"sub": "not-a-uuid", "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        await auth.refresh_token(RefreshTokenRequest(refresh_token=malformed))


@pytest.mark.asyncio
async def test_current_user_valid_invalid_inactive_and_deleted(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_active=True)
    users = FakeUsers(user)
    monkeypatch.setattr(auth_dependencies, "UserRepository", lambda db: users)
    access_token = create_access_token(str(user.id))

    assert await auth_dependencies.get_current_user(access_token, object()) is user

    with pytest.raises(HTTPException) as invalid:
        await auth_dependencies.get_current_user("invalid", object())
    assert invalid.value.status_code == 401

    user.is_active = False
    with pytest.raises(HTTPException) as inactive:
        await auth_dependencies.get_current_user(access_token, object())
    assert inactive.value.status_code == 401

    users.user = None
    with pytest.raises(HTTPException) as deleted:
        await auth_dependencies.get_current_user(access_token, object())
    assert deleted.value.status_code == 401


@pytest.mark.asyncio
async def test_oauth_new_user_gets_provisioning_and_existing_users_do_not():
    users = FakeUsers()
    accounts = FakeAccounts()
    provisioning = FakeProvisioning()
    service = make_oauth(users, accounts, provisioning)

    await service.authenticate(
        provider="google",
        provider_user_id="google-1",
        email="new@example.com",
        first_name="New",
        last_name="User",
    )
    assert len(provisioning.calls) == 1
    assert provisioning.calls[0]["organization_name"] == "New User"
    assert len(accounts.created) == 1

    existing_user = SimpleNamespace(id=uuid4(), is_active=True)
    existing_accounts = FakeAccounts()
    existing_provisioning = FakeProvisioning()
    existing_service = make_oauth(
        FakeUsers(existing_user), existing_accounts, existing_provisioning
    )
    await existing_service.authenticate(
        provider="github",
        provider_user_id="github-1",
        email="existing@example.com",
    )
    assert not existing_provisioning.calls
    assert len(existing_accounts.created) == 1

    linked_account = SimpleNamespace(user_id=existing_user.id)
    linked_accounts = FakeAccounts(linked_account)
    linked_service = make_oauth(
        FakeUsers(existing_user), linked_accounts, FakeProvisioning()
    )
    await linked_service.authenticate(
        provider="github",
        provider_user_id="github-1",
        email="existing@example.com",
    )
    assert not linked_accounts.created



def test_oauth_provider_identity_and_verified_email_rules():
    with pytest.raises(ValueError):
        GoogleOAuthProvider.extract_user_data(
            {"sub": "1", "email": "user@example.com", "email_verified": False}
        )

    google_data = GoogleOAuthProvider.extract_user_data(
        {"sub": "1", "email": "user@example.com", "email_verified": True}
    )
    assert google_data["provider_user_id"] == "1"

    github_data = GithubOAuthProvider.extract_user_data(
        {"id": 12345, "name": "Ada Lovelace"}, "ada@example.com"
    )
    assert github_data["provider_user_id"] == "12345"

    with pytest.raises(ValueError):
        _select_verified_github_email([{"email": "unverified@example.com", "verified": False}])

    assert _select_verified_github_email(
        [
            {"email": "fallback@example.com", "verified": True, "primary": False},
            {"email": "primary@example.com", "verified": True, "primary": True},
        ]
    ) == "primary@example.com"
    assert _select_verified_github_email(
        [{"email": "fallback@example.com", "verified": True, "primary": False}]
    ) == "fallback@example.com"


def test_production_rejects_weak_jwt_secret():
    config = Setting(
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        JWT_SECRET_KEY="change-me",
        GOOGLE_CLIENT_ID="google-id",
        GOOGLE_CLIENT_SECRET="google-secret",
        GITHUB_CLIENT_ID="github-id",
        GITHUB_CLIENT_SECRET="github-secret",
        APP_ENV="production",
    )

    with pytest.raises(ValueError, match="strong production secret"):
        validate_security_settings(config)


def test_settings_accept_release_debug_environment_value():
    config = Setting(
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        JWT_SECRET_KEY="change-me",
        GOOGLE_CLIENT_ID="google-id",
        GOOGLE_CLIENT_SECRET="google-secret",
        GITHUB_CLIENT_ID="github-id",
        GITHUB_CLIENT_SECRET="github-secret",
        DEBUG="release",
    )

    assert config.DEBUG is False
