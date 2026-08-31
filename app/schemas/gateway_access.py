from dataclasses import dataclass

from app.models.api_key import APIKey
from app.models.api_plan import APIPlan
from app.models.subscription import Subscription


@dataclass
class GatewayAccessContext:
    api_key: APIKey
    subscription: Subscription | None = None
    plan: APIPlan | None = None

    @property
    def subcription(self) -> Subscription | None:
        """Compatibility alias for typo"""
        return self.subscription