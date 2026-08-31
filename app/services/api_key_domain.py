from uuid import UUID

from urllib.parse import urlparse

from fastapi import HTTPException, status

from sqlalchemy.exc import IntegrityError

from app.models.api_key_domain import APIKeyDomain
from app.repositories.api_key_domain import APIKeyDomainRepository


class APIKeyDomainService:
    def __init__(
        self,
        repository: APIKeyDomainRepository,
    ):
        self.repository = repository

    async def get_by_id(
        self,
        domain_id: UUID,
    ) -> APIKeyDomain | None:
        return await self.repository.get_by_id(domain_id)

    async def get_by_api_key(
        self,
        api_key_id: UUID,
    ) -> list[APIKeyDomain]:
        return await self.repository.get_by_api_key_id(api_key_id)

    async def add_domain(
        self,
        *,
        api_key_id: UUID,
        domain: str,
    ) -> APIKeyDomain:
        domain = domain.lower().strip()

        existing_domains = await self.repository.get_by_api_key_id(
            api_key_id
        )

        if any(item.domain == domain for item in existing_domains):
            raise ValueError(
                "This domain is already assigned to this API key."
            )

        try:
            domain_record = await self.repository.create(
                api_key_id=api_key_id,
                domain=domain,
            )
            await self.repository.db.commit()
            await self.repository.db.refresh(domain_record)
            return domain_record
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "This domain is already assigned to this API key."
            ) from exc

    async def remove_domain(
        self,
        domain: APIKeyDomain,
    ) -> None:
        await self.repository.delete(domain)
        await self.repository.db.commit()

    async def validate_request_domain(
        self,
        *,
        api_key_id: UUID,
        origin: str | None,
    ) -> None:
        allowed_domains = await self.repository.get_by_api_key_id(api_key_id)

        active_domains = [
            item
            for item in allowed_domains
            if item.is_active
        ]

        # No restrictions configured.
        if not active_domains:
            return

        if not origin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request origin is not allowed",
            )

        origin_str = origin.strip()
        if "://" not in origin_str and not origin_str.startswith("//"):
            origin_to_parse = f"//{origin_str}"
        else:
            origin_to_parse = origin_str

        parsed_origin = urlparse(origin_to_parse)
        request_domain = parsed_origin.hostname

        if request_domain is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid request origin",
            )

        request_domain = request_domain.lower().rstrip(".")

        def is_match(pattern: str, hostname: str) -> bool:
            p = pattern.lower().strip().rstrip(".")
            h = hostname.lower().strip().rstrip(".")
            if p == h:
                return True
            if p.startswith("*."):
                base = p[2:]
                return h == base or h.endswith("." + base)
            return False

        allowed = any(
            is_match(item.domain, request_domain)
            for item in active_domains
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Domain is not allowed for this API key",
            )
