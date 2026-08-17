"""Application configuration, loaded from the shared repository-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration for the observable API."""

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

    # Deliberately typed as str, not list[str]. pydantic-settings tries to parse
    # a list-typed field from the environment as JSON, so the comma separated
    # value in .env would fail with a confusing JSONDecodeError rather than
    # being split. Parsing it here keeps the .env format human friendly.
    cors_allowed_origins: str = ""

    gzip_minimum_size: int = 500

    @property
    def allowed_origins(self) -> list[str]:
        """The CORS origin list, parsed from the comma separated setting."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """True when running in a production environment."""
        return self.environment.casefold() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
