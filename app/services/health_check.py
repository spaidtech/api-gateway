import time
from uuid import UUID

import httpx

from app.models.health_check import HealthCheck
from app.models.upstream import Upstream
from app.repositories.health_check import (
    HealthCheckRepository,
)


class HealthCheckService:

    def __init__(
        self,
        repository: HealthCheckRepository,
    ):
        self.repository = repository

    async def check_upstream(
        self,
        *,
        upstream: Upstream,
        api_id: UUID,
    ) -> HealthCheck:
        started_at = time.perf_counter()

        status = "unhealthy"
        status_code = None
        response_time_ms = None

        try:
            async with httpx.AsyncClient(
                timeout=5.0
            ) as client:
                response = await client.get(
                    upstream.base_url
                )

            response_time_ms = int(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            )

            status_code = response.status_code

            if response.status_code < 500:
                status = "healthy"

        except Exception:
            response_time_ms = int(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            )

        return await self.repository.create(
            api_id=api_id,
            upstream_id=upstream.id,
            status=status,
            status_code=status_code,
            response_time_ms=response_time_ms,
        )