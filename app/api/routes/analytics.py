from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import (
    get_analytics_service,
    get_api_key_service,
    get_api_route_service,
    get_api_service,
)
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.analytics import AnalyticsSummaryResponse
from app.services.analytics import AnalyticsService
from app.services.api import APIService
from app.services.api_key import APIKeyService
from app.services.api_route import APIRouteService

router = APIRouter(
    prefix="/organizations/{organization_id}/analytics",
    tags=["Analytics"],
)


@router.get(
    "",
    response_model=AnalyticsSummaryResponse,
)
async def get_organization_analytics(
    organization_id: UUID,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    return await analytics_service.get_organization_summary(
        organization_id=organization_id,
        start=start,
        end=end,
    )


@router.get(
    "/apis/{api_id}",
    response_model=AnalyticsSummaryResponse,
)
async def get_api_analytics(
    organization_id: UUID,
    api_id: UUID,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    api = await api_service.get_by_id(api_id)
    if api is None or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found in this organization",
        )

    return await analytics_service.get_api_summary(
        api_id=api_id,
        start=start,
        end=end,
    )


@router.get(
    "/apis/{api_id}/routes/{route_id}",
    response_model=AnalyticsSummaryResponse,
)
async def get_route_analytics(
    organization_id: UUID,
    api_id: UUID,
    route_id: UUID,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_service: APIService = Depends(get_api_service),
    route_service: APIRouteService = Depends(get_api_route_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    api = await api_service.get_by_id(api_id)
    if api is None or api.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API not found in this organization",
        )

    route = await route_service.get_by_id(route_id)
    if route is None or route.api_id != api_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API route not found",
        )

    return await analytics_service.get_route_summary(
        route_id=route_id,
        start=start,
        end=end,
    )


@router.get(
    "/api-keys/{api_key_id}",
    response_model=AnalyticsSummaryResponse,
)
async def get_api_key_analytics(
    organization_id: UUID,
    api_key_id: UUID,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_key_service: APIKeyService = Depends(get_api_key_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
):
    api_key = await api_key_service.get_by_id(api_key_id)
    if api_key is None or api_key.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found in this organization",
        )

    return await analytics_service.get_api_key_summary(
        api_key_id=api_key_id,
        start=start,
        end=end,
    )