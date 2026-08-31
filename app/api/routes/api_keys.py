from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import get_api_key_service
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.api_key import APIKeyCreatedResponse, APIKeyCreate, APIKeyResponse
from app.services.api_key import APIKeyService

router = APIRouter(
    prefix="/organizations/{organization_id}/api-keys",
    tags=["API Keys"],
)


@router.post(
    "",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    organization_id: UUID,
    data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIKeyService = Depends(get_api_key_service),
):
    try:
        api_key, raw_key = await service.create(
            organization_id=organization_id,
            **data.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return APIKeyCreatedResponse(
        id=api_key.id,
        organization_id=api_key.organization_id,
        subscription_id=api_key.subscription_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        status=api_key.status,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        api_key=raw_key,
    )


@router.get(
    "",
    response_model=list[APIKeyResponse],
)
async def list_api_keys(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: APIKeyService = Depends(get_api_key_service),
):
    return await service.get_by_organization(organization_id)


@router.get(
    "/{api_key_id}",
    response_model=APIKeyResponse,
)
async def get_api_key(
    organization_id: UUID,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: APIKeyService = Depends(get_api_key_service),
):
    api_key = await service.get_by_id(api_key_id)
    if not api_key or api_key.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return api_key


@router.post(
    "/{api_key_id}/regenerate",
    response_model=APIKeyCreatedResponse,
)
async def regenerate_api_key(
    organization_id: UUID,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIKeyService = Depends(get_api_key_service),
):
    api_key = await service.get_by_id(api_key_id)
    if not api_key or api_key.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    try:
        api_key, raw_key = await service.regenerate(api_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return APIKeyCreatedResponse(
        id=api_key.id,
        organization_id=api_key.organization_id,
        subscription_id=api_key.subscription_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        status=api_key.status,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        api_key=raw_key,
    )


@router.post(
    "/{api_key_id}/revoke",
    response_model=APIKeyResponse,
)
async def revoke_api_key(
    organization_id: UUID,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIKeyService = Depends(get_api_key_service),
):
    api_key = await service.get_by_id(api_key_id)
    if not api_key or api_key.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return await service.revoke(api_key)
