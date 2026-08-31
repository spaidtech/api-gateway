from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.services import (
    get_api_key_domain_service,
    get_api_key_service,
)
from app.dependencies.authorization import require_organization_roles
from app.models.membership import OrganizationMember
from app.models.api_key import APIKey
from app.models.user import User
from app.schemas.api_key_domain import (
    APIKeyDomainCreate,
    APIKeyDomainResponse,
)
from app.services.api_key import APIKeyService
from app.services.api_key_domain import APIKeyDomainService

# Use your existing authentication / authorization dependencies here
from app.dependencies.auth import get_current_user


router = APIRouter(
    prefix="/organizations/{organization_id}/api-keys/{api_key_id}/domains",
    tags=["API Key Domains"],
)


async def get_api_key_for_organization(
    organization_id: UUID,
    api_key_id: UUID,
    api_key_service: APIKeyService = Depends(
        get_api_key_service
    ),
) -> APIKey:
    """
    Ensures the API key exists and belongs to the organization
    in the URL.
    """
    api_key = await api_key_service.get_by_id(api_key_id)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    if api_key.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return api_key


@router.get(
    "",
    response_model=list[APIKeyDomainResponse],
)
async def list_api_key_domains(
    organization_id: UUID,
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    api_key: APIKey = Depends(get_api_key_for_organization),
    domain_service: APIKeyDomainService = Depends(
        get_api_key_domain_service
    ),
):
    """
    List all domains assigned to an API key.
    """

    return await domain_service.get_by_api_key(api_key.id)


@router.post(
    "",
    response_model=APIKeyDomainResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_api_key_domain(
    organization_id: UUID,
    api_key_id: UUID,
    data: APIKeyDomainCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_key: APIKey = Depends(get_api_key_for_organization),
    domain_service: APIKeyDomainService = Depends(
        get_api_key_domain_service
    ),
):
    """
    Add a domain restriction to an API key.
    """

    try:
        return await domain_service.add_domain(
            api_key_id=api_key.id,
            domain=data.domain,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.delete(
    "/{domain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_api_key_domain(
    organization_id: UUID,
    api_key_id: UUID,
    domain_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    api_key: APIKey = Depends(get_api_key_for_organization),
    domain_service: APIKeyDomainService = Depends(
        get_api_key_domain_service
    ),
):
    """
    Remove a domain restriction from an API key.
    """

    domain = await domain_service.get_by_id(domain_id)

    if domain is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key domain not found",
        )

    # Critical tenant/resource isolation check
    if domain.api_key_id != api_key.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key domain not found",
        )

    await domain_service.remove_domain(domain)
