from uuid import UUID

from fastapi import HTTPException, status

from app.models.api import API, APIStatus
from app.repositories.api import APIRepository
from app.repositories.api_route import APIRouteRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.upstream import UpstreamRepository
from app.schemas.gateway_routing import GatewayRouteContext


class GatewayRoutingService:
    def __init__(
        self,
        organization_repository: OrganizationRepository,
        api_repository: APIRepository,
        route_repository: APIRouteRepository,
        upstream_repository: UpstreamRepository,
    ):
        self.organization_repository = organization_repository
        self.api_repository = api_repository
        self.route_repository = route_repository
        self.upstream_repository = upstream_repository

    async def resolve_request(
        self,
        *,
        organization_slug: str,
        api_slug: str,
        path: str,
        method: str,
    ) -> GatewayRouteContext:
        organization = await self.organization_repository.get_by_slug(
            organization_slug.lower().strip()
        )

        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        if not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization is inactive",
            )

        api = await self.api_repository.get_by_slug(
            organization_id=organization.id,
            slug=api_slug.lower().strip(),
        )

        if api is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API not found",
            )

        if api.status != APIStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API is not available",
            )

        method = method.upper().strip()
        normalized_path = "/" + path.lstrip("/")

        # Try exact normalized path first, then raw path if different
        route = await self.route_repository.get_by_path_and_method(
            api_id=api.id,
            path=normalized_path,
            method=method,
        )

        if route is None and path != normalized_path:
            route = await self.route_repository.get_by_path_and_method(
                api_id=api.id,
                path=path,
                method=method,
            )

        if route is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API route not found",
            )

        upstream = await self.upstream_repository.get_by_id(route.upstream_id)

        if upstream is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream is not configured",
            )

        # Critical tenant isolation check
        if upstream.organization_id != api.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Upstream does not belong to this organization",
            )

        if not upstream.is_active:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Upstream is inactive",
            )

        return GatewayRouteContext(
            organization=organization,
            api=api,
            route=route,
            upstream=upstream,
        )
