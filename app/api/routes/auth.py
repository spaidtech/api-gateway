from fastapi import Depends, APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from authlib.integrations.base_client.errors import OAuthError

from app.core.config import settings
from app.core.oauth import oauth
from app.models.user import User
from app.dependencies.services import get_oauth_account_service
from app.dependencies.services import get_auth_service
from app.dependencies.auth import get_current_user
from app.schemas.auth import (LoginRequest, RegisterRequest, RefreshTokenRequest, TokenResponse)
from app.schemas.user import UserResponse
from app.services.auth import (AuthService, EmailAlreadyExistsError, InvalidCredentialsError, InvalidTokenError)
from app.services.oauth.google import GoogleOAuthProvider
from app.services.oauth.github import GithubOAuthProvider
from app.services.oauth.service import OAuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authenticate"]
)


def _select_verified_github_email(emails: list[dict]) -> str:
    for item in emails:
        if item.get("primary") and item.get("verified") and item.get("email"):
            return item["email"]

    for item in emails:
        if item.get("verified") and item.get("email"):
            return item["email"]

    raise ValueError("GitHub did not provide a verified email")

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def register(
    data: RegisterRequest,
    auth_service: AuthService = Depends(
        get_auth_service
    ),
) -> User:
    try:
        return await auth_service.register(data)

    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    try:
        return await auth_service.login(data)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(data: RefreshTokenRequest, auth_service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    try:
        return await auth_service.refresh_token(data)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

@router.get("/oauth/google/login")
async def google_login(
    request: Request
):
    redirect_uri = request.url_for("google_callback")

    return await oauth.google.authorize_redirect(
        request,
        redirect_uri
    )

@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    oauth_service: OAuthService = Depends(get_oauth_account_service)
):

    try:
        token = await oauth.google.authorize_access_token(request)

        user_info = token.get("userinfo")

        if user_info is None:
            user_info = await oauth.google.userinfo(
                token=token
            )


        user_data = GoogleOAuthProvider.extract_user_data(
            user_info
        )

        tokens = await oauth_service.authenticate(
            **user_data
        )

        return tokens

    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication Failed"
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/oauth/github/login")
async def github_login(
    request: Request
):

    redirect_uri = request.url_for("github_callback")

    return await oauth.github.authorize_redirect(
        request,
        redirect_uri
    )

@router.get("/oauth/github/callback")
async def github_callback(
    request: Request,
    oauth_service: OAuthService = Depends(get_oauth_account_service)
):
    try:
        token = await oauth.github.authorize_access_token(request)

        user_response = await oauth.github.get(
            "user",
            token=token
        )

        user_info = user_response.json()

        emails_response = await oauth.github.get(
            "user/emails",
            token=token
        )

        emails = emails_response.json()

        primary_email = _select_verified_github_email(emails)

        user_data = GithubOAuthProvider.extract_user_data(
            user_info=user_info,
            email=primary_email
        )

        tokens = await oauth_service.authenticate(
            **user_data
        )

        return tokens

    except OAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub authentication failed",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user