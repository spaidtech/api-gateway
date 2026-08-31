from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.api import APIRepository
from app.repositories.api_key import APIKeyRepository
from app.repositories.api_key_domain import APIKeyDomainRepository
from app.repositories.api_plan import APIPlanRepository
from app.repositories.api_route import APIRouteRepository
from app.repositories.health_check import HealthCheckRepository
from app.repositories.oauth_account import OAuthAccountRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_member import (
    OrganizationMemberRepository,
)
from app.repositories.payment import PaymentRepository
from app.repositories.role import RoleRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.upstream import UpstreamRepository
from app.repositories.usage_record import UsageRecordRepository
from app.repositories.user import UserRepository
from app.services.analytics import AnalyticsService
from app.services.api import APIService
from app.services.api_key import APIKeyService
from app.services.api_key_domain import APIKeyDomainService
from app.services.api_plan import APIPlanService
from app.services.api_route import APIRouteService
from app.services.auth import AuthService
from app.services.gateway_access import GatewayAccessService
from app.services.gateway_routing import GatewayRoutingService
from app.services.health_check import HealthCheckService
from app.services.oauth.service import OAuthService
from app.services.organization import OrganizationService
from app.services.organization_member import OrganizationMemberService
from app.services.payment.service import PaymentService
from app.services.role import RoleService
from app.services.subscription import SubscriptionService
from app.services.upstream import UpstreamService
from app.services.usage_record import UsageRecordService
from app.services.user import UserService


# User
def get_user_service(
    db: AsyncSession = Depends(get_db),
) -> UserService:
    return UserService(UserRepository(db))


def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    return AuthService(db)


# OAuth
def get_oauth_account_service(
    db: AsyncSession = Depends(get_db),
) -> OAuthService:
    return OAuthService(db)


# Roles
def get_role_service(
    db: AsyncSession = Depends(get_db),
) -> RoleService:
    return RoleService(RoleRepository(db))


# Organizations
def get_organization_service(
    db: AsyncSession = Depends(get_db),
) -> OrganizationService:
    return OrganizationService(
        db=db,
        organization_repository=OrganizationRepository(db),
        membership_repository=OrganizationMemberRepository(db),
        role_repository=RoleRepository(db),
    )


# Organization members
def get_organization_member_service(
    db: AsyncSession = Depends(get_db),
) -> OrganizationMemberService:
    return OrganizationMemberService(
        db=db,
        repository=OrganizationMemberRepository(db),
        role_repository=RoleRepository(db),
        user_repository=UserRepository(db),
    )


# Upstreams
def get_upstream_service(
    db: AsyncSession = Depends(get_db),
) -> UpstreamService:
    return UpstreamService(UpstreamRepository(db))


# APIs
def get_api_service(
    db: AsyncSession = Depends(get_db),
) -> APIService:
    return APIService(APIRepository(db))


# API routes
def get_api_route_service(
    db: AsyncSession = Depends(get_db),
) -> APIRouteService:
    return APIRouteService(APIRouteRepository(db))


# API plans
def get_api_plan_service(
    db: AsyncSession = Depends(get_db),
) -> APIPlanService:
    return APIPlanService(APIPlanRepository(db))


# Subscriptions
def get_subscription_service(
    db: AsyncSession = Depends(get_db),
) -> SubscriptionService:
    return SubscriptionService(SubscriptionRepository(db))


# API keys
def get_api_key_service(
    db: AsyncSession = Depends(get_db),
) -> APIKeyService:
    return APIKeyService(
        repository=APIKeyRepository(db),
        subscription_repository=SubscriptionRepository(db),
        api_plan_repository=APIPlanRepository(db),
    )


# Payments
def get_payment_service(
    db: AsyncSession = Depends(get_db),
) -> PaymentService:
    return PaymentService(PaymentRepository(db))


# API key domains
def get_api_key_domain_service(
    db: AsyncSession = Depends(get_db),
) -> APIKeyDomainService:
    return APIKeyDomainService(APIKeyDomainRepository(db))


# Usage records
def get_usage_record_service(
    db: AsyncSession = Depends(get_db),
) -> UsageRecordService:
    return UsageRecordService(UsageRecordRepository(db))


# Analytics
def get_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsService:
    return AnalyticsService(UsageRecordRepository(db))


# Health checks
def get_health_check_service(
    db: AsyncSession = Depends(get_db),
) -> HealthCheckService:
    return HealthCheckService(HealthCheckRepository(db))


def get_gateway_access_service(
    db: AsyncSession = Depends(get_db),
) -> GatewayAccessService:
    return GatewayAccessService(
        subscription_service=get_subscription_service(db),
        api_plan_service=get_api_plan_service(db),
    )


def get_gateway_routing_service(
    db: AsyncSession = Depends(get_db),
) -> GatewayRoutingService:
    return GatewayRoutingService(
        organization_repository=OrganizationRepository(db),
        api_repository=APIRepository(db),
        route_repository=APIRouteRepository(db),
        upstream_repository=UpstreamRepository(db),
    )