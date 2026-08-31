from fastapi import Depends, Request

from app.dependencies.api_key import get_current_api_key
from app.dependencies.services import get_gateway_access_service, get_api_key_domain_service
from app.models.api_key import APIKey
from app.schemas.gateway_access import GatewayAccessContext
from app.services.gateway_access import GatewayAccessService
from app.services.api_key_domain import APIKeyDomainService

async def get_gateway_access(
        request: Request,
        api_key: APIKey = Depends(get_current_api_key),
        gateway_access_service: GatewayAccessService = Depends(get_gateway_access_service),
        domain_service: APIKeyDomainService = Depends(get_api_key_domain_service)
) ->  GatewayAccessContext:
    
    origin = request.headers.get("origin")

    await domain_service.validate_request_domain(
        api_key_id=api_key.id,
        origin=origin
    )

    return await gateway_access_service.get_access_context(api_key=api_key)
