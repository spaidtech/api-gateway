from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import get_organization_service
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organization import OrganizationService


router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    organization_service: OrganizationService = Depends(
        get_organization_service
    ),
):
    try:
        return await organization_service.create(
            owner=current_user,
            name=data.name,
            slug=data.slug,
            description=data.description,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    current_user: User=Depends(get_current_user),
    organization_service: OrganizationService=Depends(get_organization_service)
):
    return await organization_service.get_for_user(current_user.id)

@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def get_organization(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_service: OrganizationService = Depends(
        get_organization_service
    ),
    _membership=Depends(
        require_organization_roles(
            "owner",
            "admin",
            "member",
        )
    ),
):
    organization = await organization_service.get_by_id(
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return organization


@router.patch(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def update_organization(
    organization_id: UUID,
    data: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    organization_service: OrganizationService = Depends(
        get_organization_service
    ),
    _membership=Depends(
        require_organization_roles("owner")
    ),
):
    organization = await organization_service.get_by_id(
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    try:
        return await organization_service.update(
            organization,
            name=data.name,
            description=data.description,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.delete(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def deactivate_organization(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    organization_service: OrganizationService = Depends(
        get_organization_service
    ),
    _membership=Depends(
        require_organization_roles("owner")
    ),
):
    organization = await organization_service.get_by_id(
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return await organization_service.deactivate(organization)