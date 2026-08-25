"""Application configuration, loaded from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environment
    montra_env: str = "development"
    montra_debug: bool = True

    # Persistence
    database_url: str = "postgresql+psycopg://montra:montra@localhost:5432/montra"
    test_database_url: str = "postgresql+psycopg://montra:montra@localhost:5432/montra_test"
    redis_url: str = "redis://localhost:6379/0"

    # Sessions. Session records live in Postgres so that revocation survives
    # a restart; Redis stays a pure queue/cache (ADR-007).
    secret_key: str = "dev-only-insecure-secret-change-me"
    session_cookie_name: str = "montra_session"
    session_ttl_hours: int = 720
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Object storage for attachments. S3-compatible, so the same code runs
    # against MinIO locally and a real bucket in production; only the endpoint
    # and credentials change.
    s3_endpoint_url: str = "http://minio:9000"
    s3_public_endpoint_url: str = "http://localhost:8080"
    s3_region: str = "us-east-1"
    s3_bucket: str = "montra-attachments"
    s3_access_key: str = "montra"
    s3_secret_key: str = "montra-dev-secret"
    # Long enough to upload a photo on a slow connection, short enough that a
    # leaked link is worthless by the time it is shared.
    s3_signed_url_ttl_seconds: int = 900

    # Attachments
    attachment_max_bytes: int = 10 * 1024 * 1024
    attachment_allowed_mime_types: str = (
        "image/jpeg,image/png,image/webp,image/heic,application/pdf"
    )

    @property
    def attachment_mime_list(self) -> list[str]:
        return [m.strip() for m in self.attachment_allowed_mime_types.split(",") if m.strip()]

    # Exchange rates. Frankfurter and open.er-api need no key; CurrencyFreaks
    # does, and takes precedence when one is configured because it publishes
    # far more currencies than the ECB set.
    currencyfreaks_api_key: str = ""

    # HTTP
    cors_origins: str = "http://localhost:3000"
    api_v1_prefix: str = "/api/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.montra_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
