"""Application configuration, loaded from the shared repository-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration for the dependency injection toolkit."""

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

    # Guards the /admin router. Real per-user authentication is module 12.
    admin_api_key: str = ""

    default_page_size: int = 20
    max_page_size: int = 100

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
    """Return the settings singleton.

    This is both a plain function and a FastAPI dependency. Anything that can be
    called and whose parameters FastAPI can resolve is usable with Depends, so
    no adapter or registration step is needed.

    lru_cache means the .env is parsed once per process. Tests that need
    different settings call get_settings.cache_clear() or, better, override the
    dependency - which is what module 09 is about.
    """
    return Settings()
