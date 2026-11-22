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

    # Public URL of the dashboard, used in links (invitations, `envo login`).
    frontend_url: str = "http://localhost:5173"
    # Built dashboard to serve from this process (set in the container image).
    # Unset in development, where Vite serves the frontend.
    static_dir: str | None = None

    # Outgoing e-mail (invitations). Without a host, nothing is sent and the
    # inviter is shown the invitation link to share it themselves.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_from: str = "Envo <envo@localhost>"

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host)

    # Envelope encryption master key (KEK): 32 bytes, base64. Read from the
    # variable or, if set, from a mounted file. Never stored in the database.
    master_key: str | None = None
    master_key_file: str | None = None
    master_key_id: str = "k1"
    # Previous KEKs kept for unwrapping during rotation: "id:base64,id:base64".
    retired_master_keys: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
