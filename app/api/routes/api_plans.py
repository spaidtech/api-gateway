from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import get_api_plan_service, get_api_service
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.api_plan import APIPlanCreate, APIPlanResponse, APIPlanUpdate
from app.services.api import APIService
from app.services.api_plan import APIPlanService


router = APIRouter(
    prefix="/organizations/{organization_id}/apis/{api_id}/plans",
    tags=["API Plans"],
)


async def get_api_for_organization(
    organization_id: UUID,
    api_id: UUID,
    api_service: APIService,
):
    api = await api_service.get_by_id(api_id)
    if not api or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found",
        )
    return api


@router.post(
    "",
    response_model=APIPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    organization_id: UUID,
    api_id: UUID,
    data: APIPlanCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)
    return await plan_service.create(api_id=api_id, **data.model_dump())


@router.get(
    "",
    response_model=list[APIPlanResponse],
)
async def list_plans(
    organization_id: UUID,
    api_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)
    return await plan_service.get_by_api(api_id)


@router.get(
    "/{plan_id}",
    response_model=APIPlanResponse,
)
async def get_plan(
    organization_id: UUID,
    api_id: UUID,
    plan_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    plan = await plan_service.get_by_id(plan_id)
    if not plan or plan.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API plan not found",
        )

    return plan


@router.patch(
    "/{plan_id}",
    response_model=APIPlanResponse,
)
async def update_plan(
    organization_id: UUID,
    api_id: UUID,
    plan_id: UUID,
    data: APIPlanUpdate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    plan = await plan_service.get_by_id(plan_id)
    if not plan or plan.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API plan not found",
        )

    return await plan_service.update(plan, **data.model_dump(exclude_unset=True))


@router.delete(
    "/{plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plan(
    organization_id: UUID,
    api_id: UUID,
    plan_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    plan = await plan_service.get_by_id(plan_id)
    if not plan or plan.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API plan not found",
        )

    try:
        await plan_service.delete(plan)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
