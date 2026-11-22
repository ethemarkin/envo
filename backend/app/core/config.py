from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENVO_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+asyncpg://envo:envo@localhost:5432/envo"

    # JWT access tokens and signed OAuth state cookies.
    secret_key: str = Field(min_length=32)
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60

    # Cookies: Secure must be true anywhere outside local http development.
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # Where the browser is sent after Google login.
    frontend_url: str = "http://localhost:5173"
    # Public base URL of the API, used to build the OAuth redirect URI.
    api_url: str = "http://localhost:5173"

    google_client_id: str | None = None
    google_client_secret: str | None = None

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
