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
