from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.services import (
    get_api_route_service,
    get_api_service,
    get_upstream_service,
)
from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.api_route import (
    APIRouteCreate,
    APIRouteResponse,
    APIRouteUpdate,
)
from app.services.api import APIService
from app.services.api_route import APIRouteService
from app.services.upstream import UpstreamService


router = APIRouter(
    prefix="/organizations/{organization_id}/apis/{api_id}/routes",
    tags=["API Routes"],
)


async def get_api_for_organization(
    organization_id: UUID,
    api_id: UUID,
    api_service: APIService = Depends(get_api_service),
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
    response_model=APIRouteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_route(
    organization_id: UUID,
    api_id: UUID,
    data: APIRouteCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(
        get_api_route_service
    ),
    upstream_service: UpstreamService = Depends(
        get_upstream_service
    ),
):
    await get_api_for_organization(
        organization_id,
        api_id,
        api_service,
    )

    upstream = await upstream_service.get_by_id(
        data.upstream_id
    )

    if not upstream or upstream.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream not found",
        )

    try:
        return await route_service.create(
            api_id=api_id,
            **data.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[APIRouteResponse],
)
async def list_routes(
    organization_id: UUID,
    api_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(get_api_route_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)
    return await route_service.get_by_api(api_id)


@router.get(
    "/{route_id}",
    response_model=APIRouteResponse,
)
async def get_route(
    organization_id: UUID,
    api_id: UUID,
    route_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(get_api_route_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    route = await route_service.get_by_id(route_id)
    if not route or route.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API route not found",
        )

    return route


@router.patch(
    "/{route_id}",
    response_model=APIRouteResponse,
)
async def update_route(
    organization_id: UUID,
    api_id: UUID,
    route_id: UUID,
    data: APIRouteUpdate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(get_api_route_service),
    upstream_service: UpstreamService = Depends(get_upstream_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    route = await route_service.get_by_id(route_id)
    if not route or route.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API route not found",
        )

    fields = data.model_dump(exclude_unset=True)
    upstream_id = fields.get("upstream_id")
    if upstream_id is not None:
        upstream = await upstream_service.get_by_id(upstream_id)
        if not upstream or upstream.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upstream not found",
            )

    try:
        return await route_service.update(route, **fields)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_route(
    organization_id: UUID,
    api_id: UUID,
    route_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(get_api_route_service),
):
    await get_api_for_organization(organization_id, api_id, api_service)

    route = await route_service.get_by_id(route_id)
    if not route or route.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API route not found",
        )

    await route_service.delete(route)
