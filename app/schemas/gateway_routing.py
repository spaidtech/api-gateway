from dataclasses import dataclass

from app.models.api import API
from app.models.api_route import APIRoute
from app.models.organization import Organization
from app.models.upstream import Upstream


@dataclass
class GatewayRouteContext:
    organization: Organization
    api: API
    route: APIRoute
    upstream: Upstream