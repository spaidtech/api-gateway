from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import get_api_service
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.api import (
    APICreate,
    APIResponse,
    APIUpdate,
)
from app.services.api import APIService


router = APIRouter(
    prefix="/organizations/{organization_id}/apis",
    tags=["APIs"],
)


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api(
    organization_id: UUID,
    data: APICreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIService = Depends(get_api_service),
):
    try:
        return await service.create(
            organization_id=organization_id,
            **data.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[APIResponse],
)
async def list_apis(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: APIService = Depends(get_api_service),
):
    return await service.get_by_organization(organization_id)


@router.get(
    "/{api_id}",
    response_model=APIResponse,
)
async def get_api(
    organization_id: UUID,
    api_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: APIService = Depends(get_api_service),
):
    api = await service.get_by_id(api_id)

    if not api or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found",
        )

    return api


@router.patch(
    "/{api_id}",
    response_model=APIResponse,
)
async def update_api(
    organization_id: UUID,
    api_id: UUID,
    data: APIUpdate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIService = Depends(get_api_service),
):
    api = await service.get_by_id(api_id)

    if not api or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found",
        )

    try:
        return await service.update(
            api,
            **data.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api(
    organization_id: UUID,
    api_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: APIService = Depends(get_api_service),
):
    api = await service.get_by_id(api_id)

    if not api or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found",
        )

    await service.delete(api)
