from fastapi import Depends, HTTPException, Request, status

from app.dependencies.services import get_api_key_service
from app.models.api_key import APIKey
from app.services.api_key import APIKeyService

async def get_current_api_key(
    request: Request,
    api_key_service: APIKeyService = Depends(get_api_key_service)
) -> APIKey:
    raw_api_key = request.headers.get("X-API-Key")

    if not raw_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required",
        )

    key_hash = api_key_service.hash_key(raw_api_key)

    api_key = await api_key_service.get_by_key_hash(key_hash)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    validated_api_key = await api_key_service.validate(api_key)
    
    return validated_api_key