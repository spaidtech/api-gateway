from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import (
    get_api_service,
    get_health_check_service,
    get_upstream_service,
)
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.health import HealthCheckResponse
from app.schemas.upstream import (
    UpstreamCreate,
    UpstreamResponse,
    UpstreamUpdate,
)
from app.services.api import APIService
from app.services.health_check import HealthCheckService
from app.services.upstream import UpstreamService


router = APIRouter(
    prefix="/organizations/{organization_id}/upstreams",
    tags=["Upstreams"],
)


@router.post(
    "",
    response_model=UpstreamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upstream(
    organization_id: UUID,
    data: UpstreamCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: UpstreamService = Depends(get_upstream_service),
):
    return await service.create(
        organization_id=organization_id,
        **data.model_dump(),
    )


@router.get(
    "",
    response_model=list[UpstreamResponse],
)
async def list_upstreams(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: UpstreamService = Depends(get_upstream_service),
):
    return await service.get_by_organization(organization_id)


@router.get(
    "/{upstream_id}",
    response_model=UpstreamResponse,
)
async def get_upstream(
    organization_id: UUID,
    upstream_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    service: UpstreamService = Depends(get_upstream_service),
):
    upstream = await service.get_by_id(upstream_id)

    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    return upstream


@router.patch(
    "/{upstream_id}",
    response_model=UpstreamResponse,
)
async def update_upstream(
    organization_id: UUID,
    upstream_id: UUID,
    data: UpstreamUpdate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: UpstreamService = Depends(get_upstream_service),
):
    upstream = await service.get_by_id(upstream_id)

    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    return await service.update(
        upstream,
        **data.model_dump(exclude_unset=True),
    )


@router.delete(
    "/{upstream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_upstream(
    organization_id: UUID,
    upstream_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    service: UpstreamService = Depends(get_upstream_service),
):
    upstream = await service.get_by_id(upstream_id)

    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    try:
        await service.delete(upstream)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post(
    "/{upstream_id}/health-check",
    response_model=HealthCheckResponse,
)
async def trigger_health_check(
    organization_id: UUID,
    upstream_id: UUID,
    api_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    upstream_service: UpstreamService = Depends(get_upstream_service),
    api_service: APIService = Depends(get_api_service),
    health_service: HealthCheckService = Depends(get_health_check_service),
):
    upstream = await upstream_service.get_by_id(upstream_id)
    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    target_api_id = api_id
    if target_api_id is not None:
        api = await api_service.get_by_id(target_api_id)
        if not api or api.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target API not found in this organization",
            )
    else:
        apis = await api_service.get_by_organization(organization_id)
        if not apis:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization must have at least one API to record health checks",
            )
        target_api_id = apis[0].id

    health_check = await health_service.check_upstream(
        upstream=upstream,
        api_id=target_api_id,
    )
    await health_service.repository.db.commit()
    await health_service.repository.db.refresh(health_check)
    return health_check


@router.get(
    "/{upstream_id}/health",
    response_model=HealthCheckResponse,
)
async def get_latest_health(
    organization_id: UUID,
    upstream_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    upstream_service: UpstreamService = Depends(get_upstream_service),
    health_service: HealthCheckService = Depends(get_health_check_service),
):
    upstream = await upstream_service.get_by_id(upstream_id)
    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    latest = await health_service.repository.get_latest_by_upstream(upstream_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No health check records found for this upstream",
        )

    return latest


@router.get(
    "/{upstream_id}/health-history",
    response_model=list[HealthCheckResponse],
)
async def get_health_history(
    organization_id: UUID,
    upstream_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    upstream_service: UpstreamService = Depends(get_upstream_service),
    health_service: HealthCheckService = Depends(get_health_check_service),
):
    upstream = await upstream_service.get_by_id(upstream_id)
    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    return await health_service.repository.get_history(upstream_id, limit=limit)
