"""Application configuration, loaded from the shared repository-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration for the resilient item API."""

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

    @property
    def is_production(self) -> bool:
        """True when running in a production environment."""
        return self.environment.casefold() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
