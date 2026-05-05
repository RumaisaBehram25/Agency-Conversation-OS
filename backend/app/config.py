"""
Attora — Environment Configuration

Uses Pydantic BaseSettings to load and validate all configuration
from environment variables with sensible defaults for local development.
"""

from typing import Literal

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
    # When False and debug is False, /api/docs and /api/openapi.json are not mounted.
    # Set EXPOSE_API_DOCS=true on staging or internal servers to enable Swagger without DEBUG.
    expose_api_docs: bool = False
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"
    database_url_sync: str = "postgresql://attora:Attora-123@attora-db.cp8ooqrtonyo.us-east-1.rds.amazonaws.com:5432/attora"

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

    # ── AI / Anthropic ────────────────────────────────────────
    anthropic_api_key: str = ""
    hyros_api_key: str = ""

    # ── Cron Jobs ─────────────────────────────────────────────
    cron_secret: str = "change-me-to-a-random-cron-secret"

    # Follow-up dispatcher: optional in-process cron (alternative: POST /api/cron/follow-ups
    # from an external scheduler every 15 minutes).
    follow_up_scheduler_enabled: bool = False
    follow_up_scheduler_cron: str = "*/15 * * * *"

    # ── OLAP / Data Lake ─────────────────────────────────────
    olap_storage_provider: Literal["none", "s3"] = "none"
    olap_query_provider: Literal["none", "trino", "athena"] = "none"
    olap_bucket: str = "attora-analytics"
    olap_prefix: str = "lake"
    olap_region: str = "us-east-1"
    olap_endpoint: str = ""
    olap_access_key_id: str = ""
    olap_secret_access_key: str = ""
    olap_s3_force_path_style: bool = True
    olap_secure: bool = False
    olap_export_batch_size: int = 5000
    olap_message_hot_retention_days: int = 90
    olap_delta_window_days: int = 7
    olap_checkpoint_prefix: str = "_control/checkpoints"
    olap_partition_refresh_interval_seconds: int = 300

    # ── Trino ─────────────────────────────────────────────────
    trino_host: str = ""
    trino_port: int = 8080
    trino_user: str = "attora"
    trino_catalog: str = "lakehouse"
    trino_schema: str = "default"
    trino_http_scheme: Literal["http", "https"] = "http"
    trino_connection_pool_size: int = 4

    # ── Athena ────────────────────────────────────────────────
    athena_workgroup: str = "primary"
    athena_database: str = "attora_analytics"
    athena_output_location: str = ""

    # ── OLAP Scheduler ───────────────────────────────────────
    olap_scheduler_enabled: bool = False
    olap_scheduler_timezone: str = "UTC"
    olap_scheduler_export_daily_analytics_cron: str = "5 1 * * *"
    olap_scheduler_export_ai_usage_cron: str = "20 1 * * *"
    olap_scheduler_archive_messages_cron: str = "35 1 * * *"
    olap_scheduler_parity_cron: str = "50 1 * * *"
    olap_scheduler_parity_org_ids: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def olap_storage_enabled(self) -> bool:
        """Return whether object storage is configured for OLAP datasets."""
        return self.olap_storage_provider != "none"

    @property
    def olap_query_enabled(self) -> bool:
        """Return whether an OLAP query engine is configured."""
        return self.olap_query_provider != "none"

    @property
    def olap_root_prefix(self) -> str:
        """Normalize the data-lake prefix used for dataset paths."""
        return self.olap_prefix.strip("/")

    @property
    def olap_checkpoint_root_prefix(self) -> str:
        """Normalize the checkpoint prefix used for orchestration metadata."""
        checkpoint_prefix = self.olap_checkpoint_prefix.strip("/")
        root_prefix = self.olap_root_prefix
        if root_prefix and checkpoint_prefix:
            return f"{root_prefix}/{checkpoint_prefix}"
        if checkpoint_prefix:
            return checkpoint_prefix
        return root_prefix

    @property
    def olap_scheduler_parity_org_ids_list(self) -> list[str]:
        """Parse the configured org filter list for scheduled parity checks."""
        return [value.strip() for value in self.olap_scheduler_parity_org_ids.split(",") if value.strip()]

    @property
    def olap_s3_uri(self) -> str:
        """Build the root S3-style URI for the configured object store."""
        prefix = self.olap_root_prefix
        if prefix:
            return f"s3://{self.olap_bucket}/{prefix}"
        return f"s3://{self.olap_bucket}"


# Singleton instance
settings = Settings()
