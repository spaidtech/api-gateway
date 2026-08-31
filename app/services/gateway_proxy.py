import httpx
from fastapi import HTTPException, status

# Shared client pool for high-performance proxy forwarding
_shared_client: httpx.AsyncClient | None = None


def get_shared_proxy_client(timeout: float = 30.0) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
        )
    return _shared_client


async def close_shared_proxy_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        try:
            await _shared_client.aclose()
        except Exception:
            pass
        _shared_client = None


class GatewayProxyService:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.timeout = timeout
        self._client = client

    def build_target_url(
        self,
        *,
        base_url: str,
        target_path: str | None,
        request_path: str,
    ) -> str:
        path = target_path or request_path
        return base_url.rstrip("/") + "/" + path.lstrip("/")

    async def forward_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        query_params=None,
        body: bytes = b"",
    ) -> httpx.Response:
        # Exclude hop-by-hop and internal headers from forwarding upstream
        excluded_headers = {
            "host",
            "connection",
            "content-length",
            "transfer-encoding",
            "x-api-key",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "upgrade",
        }

        forwarded_headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in excluded_headers
        }

        try:
            client = self._client or get_shared_proxy_client()
            return await client.request(
                method=method,
                url=url,
                headers=forwarded_headers,
                params=query_params,
                content=body,
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Upstream request timed out",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to connect to upstream service",
            )
