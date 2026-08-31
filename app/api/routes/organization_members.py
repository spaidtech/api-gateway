from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import (
    get_organization_member_service,
)
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.membership import (
    MemberCreate,
    MemberRoleUpdate,
    MembershipResponse,
)
from app.services.organization_member import (
    OrganizationMemberService,
)


router = APIRouter(
    prefix="/organizations/{organization_id}/members",
    tags=["Organization Members"],
)


@router.get(
    "",
    response_model=list[MembershipResponse],
)
async def list_members(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    membership_service: OrganizationMemberService = Depends(
        get_organization_member_service
    ),
    _membership=Depends(
        require_organization_roles(
            "owner",
            "admin",
            "member",
        )
    ),
):
    return await membership_service.get_by_organization(
        organization_id
    )


@router.post(
    "",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    organization_id: UUID,
    data: MemberCreate,
    current_user: User = Depends(get_current_user),
    membership_service: OrganizationMemberService = Depends(
        get_organization_member_service
    ),
    _membership=Depends(
        require_organization_roles("owner")
    ),
):
    try:
        return await membership_service.add_member(
            organization_id=organization_id,
            user_id=data.user_id,
            role_id=data.role_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.patch(
    "/{membership_id}",
    response_model=MembershipResponse,
)
async def update_member_role(
    organization_id: UUID,
    membership_id: UUID,
    data: MemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    membership_service: OrganizationMemberService = Depends(
        get_organization_member_service
    ),
    _membership=Depends(
        require_organization_roles("owner")
    ),
):
    membership = await membership_service.repository.get_by_id(
        membership_id
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    # Critical tenant-isolation check
    if membership.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found in this organization",
        )

    return await membership_service.update_role(
        membership=membership,
        role_id=data.role_id,
    )


@router.delete(
    "/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    organization_id: UUID,
    membership_id: UUID,
    current_user: User = Depends(get_current_user),
    membership_service: OrganizationMemberService = Depends(
        get_organization_member_service
    ),
    _membership=Depends(
        require_organization_roles("owner")
    ),
):
    membership = await membership_service.repository.get_by_id(
        membership_id
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    # Prevent accessing a membership belonging to another organization
    if membership.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found in this organization",
        )

    await membership_service.remove_member(membership)

    return None