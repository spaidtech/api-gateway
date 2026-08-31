from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Setting(BaseSettings):
    APP_NAME: str = "Multi-Tenant API Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str
    REDIS_URL: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""

    PAYMENT_SUCCESS_URL: str = "http://localhost:3000/payments/success"
    PAYMENT_CANCEL_URL: str = "http://localhost:3000/payments/cancel"

    FRONTEND_URL: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
       env_file=".env",
       extra="ignore"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
       if isinstance(value, str) and value.lower() in {
          "release",
          "prod",
          "production",
       }:
          return False

       return value

@lru_cache
def get_settings():
   return Setting()

settings = get_settings()


def validate_security_settings(config: Setting) -> None:
    if config.APP_ENV.lower() not in {"development", "local", "test"}:
        if config.JWT_SECRET_KEY == "change-me" or len(config.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY must be a strong production secret")


validate_security_settings(settings)
