import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.dependencies.gateway import get_gateway_route
from app.dependencies.gateway_access import get_gateway_access
from app.schemas.gateway_access import GatewayAccessContext
from app.schemas.gateway_routing import GatewayRouteContext
from app.services.gateway_proxy import GatewayProxyService
from app.services.quota import QuotaService
from app.services.rate_limit import RateLimitService
from app.services.usage_record import record_usage_in_background

router = APIRouter(prefix="/gateway", tags=["Gateway"])


@router.get("/verify")
async def verify_access(
    access: GatewayAccessContext = Depends(get_gateway_access),
) -> dict:
    """
    Validates API key status, origin domain rules, and subscription/plan validity.
    """
    return {
        "status": "authenticated",
        "api_key_id": str(access.api_key.id),
        "organization_id": str(access.api_key.organization_id),
        "subscription_id": (
            str(access.subscription.id) if access.subscription else None
        ),
        "plan_id": str(access.plan.id) if access.plan else None,
    }


@router.api_route(
    "/{organization_slug}/{api_slug}/{proxy_path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
    ],
)
async def proxy_request(
    request: Request,
    background_tasks: BackgroundTasks,
    access: GatewayAccessContext = Depends(get_gateway_access),
    route_context: GatewayRouteContext = Depends(get_gateway_route),
    redis: Redis = Depends(get_redis),
):
    # 1. API key authorization check:
    # Must belong directly to the provider organization OR be subscribed to the target API
    is_direct_owner = access.api_key.organization_id == route_context.api.organization_id
    is_valid_subscriber = (
        access.subscription is not None
        and access.plan is not None
        and access.plan.api_id == route_context.api.id
    )

    if not (is_direct_owner or is_valid_subscriber):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not belong to this organization or API",
        )

    rate_limit_headers = {}

    # 2. Rate Limiting & Monthly Quota enforcement (when plan is attached)
    if access.plan is not None:
        # Rate Limiting
        rate_limiter = RateLimitService(redis)
        rl_res = await rate_limiter.check(
            api_key_id=access.api_key.id,
            limit=access.plan.rate_limit,
        )
        rate_limit_headers = {
            "X-RateLimit-Limit": str(rl_res.limit),
            "X-RateLimit-Remaining": str(rl_res.remaining),
            "X-RateLimit-Reset": str(rl_res.reset_at),
        }

        if not rl_res.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=rate_limit_headers,
            )

        # Monthly Quota
        if access.subscription is not None:
            quota_service = QuotaService(redis)
            quota_res = await quota_service.consume(
                subscription_id=access.subscription.id,
                monthly_quota=access.plan.monthly_quota,
            )
            if not quota_res.allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Monthly quota exceeded",
                )

    # 3. Build upstream URL
    proxy_service = GatewayProxyService()
    target_url = proxy_service.build_target_url(
        base_url=route_context.upstream.base_url,
        target_path=route_context.route.target_path,
        request_path="/" + request.path_params.get("proxy_path", "").lstrip("/"),
    )

    body = await request.body()
    start_time = time.perf_counter()

    # 4. Forward upstream
    upstream_response = await proxy_service.forward_request(
        method=request.method,
        url=target_url,
        headers=dict(request.headers),
        query_params=request.query_params,
        body=body,
    )

    latency_ms = int((time.perf_counter() - start_time) * 1000)

    # 5. Background usage recording (using safe background session worker)
    background_tasks.add_task(
        record_usage_in_background,
        organization_id=route_context.api.organization_id,
        api_id=route_context.api.id,
        route_id=route_context.route.id,
        api_key_id=access.api_key.id,
        status_code=upstream_response.status_code,
        latency_ms=latency_ms,
        domain=request.headers.get("origin"),
    )


    # 6. Filter response headers
    excluded_response_headers = {
        "connection",
        "content-length",
        "transfer-encoding",
        "content-encoding",
    }

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in excluded_response_headers
    }
    response_headers.update(rate_limit_headers)

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )