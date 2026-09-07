"""Application configuration, loaded from the shared repository-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app/ -> 11-database/ -> fastapi/
MODULE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_ROOT.parent
ENV_FILE = REPO_ROOT / ".env"


def _absolutise_sqlite(url: str) -> str:
    """Turn a relative SQLite path into an absolute one.

    sqlite:///./app.db is resolved against the current working directory, so
    running uvicorn from one place and alembic from another would silently
    create two different database files. Anchoring to the module directory
    means every entry point agrees on which file it means.

    Only SQLite needs this. A PostgreSQL URL is a network address and has no
    relative form.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix) :]
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return url
    return f"{prefix}{(MODULE_ROOT / path.lstrip('./')).as_posix()}"


class Settings(BaseSettings):
    """Configuration for the notes API."""

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

    database_url: str = "sqlite:///./app.db"
    test_database_url: str = "sqlite:///./test.db"

    # --- authentication ---
    # No default. A signing secret with a fallback value is a signing secret
    # that ships to production unchanged, and anyone who has read the source
    # can then mint valid tokens. Startup fails instead - see validate_secret().
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # bcrypt's cost factor. Each increment doubles the work. 12 is a reasonable
    # 2026 default at roughly 200ms per hash; the tests drop it to 4 because
    # 60-odd hashes at 200ms each would add 12 seconds to the suite.
    bcrypt_rounds: int = 12

    # Logs every statement the ORM emits. Invaluable while learning what
    # SQLAlchemy actually does, and far too noisy to leave on.
    database_echo: bool = False

    @property
    def resolved_database_url(self) -> str:
        """The database URL, with any relative SQLite path made absolute."""
        return _absolutise_sqlite(self.database_url)

    @property
    def resolved_test_database_url(self) -> str:
        """The test database URL, with any relative SQLite path made absolute."""
        return _absolutise_sqlite(self.test_database_url)

    @property
    def allowed_origins(self) -> list[str]:
        """The CORS origin list, parsed from the comma separated setting."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """True when running in a production environment."""
        return self.environment.casefold() == "production"

    def validate_secret(self) -> None:
        """Refuse to run without a real signing secret.

        Called at startup so the failure is immediate and obvious. A weak or
        missing secret is not a degraded mode - it means any client can forge a
        token for any user, including an admin.
        """
        if not self.jwt_secret_key:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if len(self.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY is too short; use at least 32 characters")
        if self.is_production and self.jwt_secret_key.startswith("dev-"):
            raise RuntimeError("A development JWT_SECRET_KEY must not be used in production")


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
