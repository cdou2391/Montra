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

    # Rate limiting. On everywhere it matters; off in the test suite, which
    # registers dozens of users from one address and would otherwise be
    # throttling itself rather than testing anything. The limiter has its own
    # tests that switch it back on.
    rate_limit_enabled: bool = True

    # HTTP
    cors_origins: str = "http://localhost:3000"
    api_v1_prefix: str = "/api/v1"

    # Origins the browser may reach this API from that are not cross-origin at
    # all — the app served through the proxy on the same host. Kept separate
    # from CORS because they need no CORS headers; they only need to not be
    # mistaken for a forgery.
    same_origins: str = ""

    @property
    def same_origin_list(self) -> list[str]:
        return [o.strip() for o in self.same_origins.split(",") if o.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.montra_env == "production"

    @property
    def session_cookie_secure(self) -> bool:
        """HTTPS-only in production, whatever the file says.

        A flag that has to be remembered gets forgotten, and forgetting this
        one sends a session token over plain HTTP. Development stays on the
        configured value so localhost keeps working.
        """
        return True if self.is_production else self.cookie_secure

    def production_problems(self) -> list[str]:
        """Settings that are fine on a laptop and unacceptable in the open.

        Returned rather than raised so the caller decides — the API refuses to
        start on them; a test or a shell should be able to ask without dying.
        """
        problems = []
        if self.secret_key == "dev-only-insecure-secret-change-me":
            problems.append("SECRET_KEY is still the development default.")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE is off, so session cookies would travel in clear.")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS allows any origin.")
        if any(o.startswith("http://") for o in self.cors_origin_list):
            problems.append("CORS_ORIGINS contains a plain-HTTP origin.")
        if self.s3_secret_key == "montra-dev-secret":
            problems.append("S3_SECRET_KEY is still the development default.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
