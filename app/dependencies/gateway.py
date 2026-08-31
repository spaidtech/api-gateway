from fastapi import Depends, Request

from app.dependencies.services import get_gateway_routing_service
from app.schemas.gateway_routing import GatewayRouteContext
from app.services.gateway_routing import GatewayRoutingService

async def get_gateway_route(
        request: Request,
        organization_slug: str,
        api_slug: str,
        proxy_path: str = "",
        service: GatewayRoutingService = Depends(get_gateway_routing_service)
) -> GatewayRouteContext:
    path = "/" + proxy_path.lstrip("/")

    return await service.resolve_request(
        organization_slug=organization_slug,
        api_slug=api_slug,
        path=proxy_path,
        method=request.method
    )