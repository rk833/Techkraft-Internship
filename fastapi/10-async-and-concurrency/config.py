"""Application configuration, loaded from the shared repository-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration for the concurrent aggregator."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FastAPI Learning Journey"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    cors_allowed_origins: str = ""
    gzip_minimum_size: int = 500

    # Empty means the upstream app is called in-process through httpx's
    # ASGITransport. Set it to a URL to call a separately running upstream over
    # real HTTP instead. The application code is identical either way, which is
    # the point - only the transport changes.
    upstream_base_url: str = ""

    upstream_timeout_seconds: float = 2.0

    @property
    def allowed_origins(self) -> list[str]:
        """The CORS origin list, parsed from the comma separated setting."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """True when running in a production environment."""
        return self.environment.casefold() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
