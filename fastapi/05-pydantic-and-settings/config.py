"""Application configuration.

Settings come from the single .env at the repository root, not from a copy in
this folder. The path is resolved from __file__ rather than the working
directory, so it resolves correctly no matter where uvicorn was launched from.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration loaded from the environment.

    Values are resolved in priority order: a real environment variable first,
    then the .env file, then the default declared here. That ordering is what
    lets Docker override everything at runtime in module 16 without the .env
    file being present at all.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The shared .env holds variables for every module - database urls, jwt
        # secrets, llm keys. Without extra="ignore" this class would reject the
        # file for containing keys it does not declare.
        extra="ignore",
    )

    app_name: str = "FastAPI Learning Journey"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Not in .env, so this falls through to the default. Included to show that
    # a settings class does not require every field to be externally supplied.
    max_items_per_order: int = Field(default=20, ge=1, le=100)

    @property
    def is_production(self) -> bool:
        """True when running in a production environment."""
        return self.environment.casefold() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton.

    lru_cache means the .env file is read once per process rather than on every
    request. It also gives module 09 a clean override point: the cache can be
    cleared, or the dependency swapped, to inject test settings.
    """
    return Settings()
