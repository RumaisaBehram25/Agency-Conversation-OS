"""
Attora — Environment Configuration

Uses Pydantic BaseSettings to load and validate all configuration
from environment variables with sensible defaults for local development.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "Attora"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://attora:attora_dev@postgres:5432/attora"
    database_url_sync: str = "postgresql://attora:attora_dev@postgres:5432/attora"

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── JWT Authentication ───────────────────────────────────
    jwt_secret_key: str = "change-me-to-a-random-secret-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Encryption ───────────────────────────────────────────
    encryption_key: str = "change-me-generate-a-real-fernet-key"

    # ── CORS ─────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # ── Rate Limiting ────────────────────────────────────────
    rate_limit_per_minute: int = 100

    # ── Cron Jobs ─────────────────────────────────────────────
    cron_secret: str = "change-me-to-a-random-cron-secret"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Singleton instance
settings = Settings()
