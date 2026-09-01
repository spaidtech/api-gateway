from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.analytics import router as analytics_routes
from app.api.routes.api_key_domains import router as api_key_domains_routes
from app.api.routes.api_keys import router as api_keys_routes
from app.api.routes.api_plans import router as api_plans_routes
from app.api.routes.api_routes import router as api_routes
from app.api.routes.apis import router as apis_routes
from app.api.routes.auth import router as auth_routes
from app.api.routes.gateway import router as gateway_routes
from app.api.routes.health import router as health_routes
from app.api.routes.organization_members import (
    router as organization_members_routes,
)
from app.api.routes.organizations import router as organizations_routes
from app.api.routes.payments import router as payments_routes
from app.api.routes.subscriptions import router as subscriptions_routes
from app.api.routes.upstreams import router as upstreams_routes
from app.core.config import settings
from app.core.redis import close_redis
from app.services.gateway_proxy import close_shared_proxy_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()
    await close_shared_proxy_client()


app = FastAPI(
    title="Multi-Tenant API Platform",
    description="Production-grade Multi-Tenant API Gateway and Developer Management Platform.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)

# Register routes
app.include_router(health_routes)
app.include_router(auth_routes)
app.include_router(organizations_routes)
app.include_router(organization_members_routes)
app.include_router(upstreams_routes)
app.include_router(apis_routes)
app.include_router(api_routes)
app.include_router(api_plans_routes)
app.include_router(subscriptions_routes)
app.include_router(payments_routes)
app.include_router(api_keys_routes)
app.include_router(api_key_domains_routes)
app.include_router(analytics_routes)
app.include_router(gateway_routes)


@app.get("/")
async def root():
    return {
        "message": "Multi-Tenant API Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }