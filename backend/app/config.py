"""TaskForge application configuration via pydantic-settings."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
_ROOT_ENV = _ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT_ENV, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            insecure_defaults = [
                "change_me_generate_a_real_secret_here",
                "secret",
                "changeme",
            ]
            if not self.jwt_secret_key or self.jwt_secret_key in insecure_defaults or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "Production app_env requires a secure JWT_SECRET_KEY of at least 32 characters."
                )
        return self

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://taskforge:taskforge@localhost:5432/taskforge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://taskforge:taskforge@localhost:5672/taskforge"
    rabbitmq_vhost: str = "taskforge"
    rabbitmq_management_url: str = "http://taskforge:taskforge@rabbitmq:15672"

    # JWT
    jwt_secret_key: str = "change_me_generate_a_real_secret_here"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Worker
    worker_concurrency: int = 4
    worker_hostname: str = "worker-local"
    # A worker/scheduler that misses heartbeats this long is shown offline.
    worker_heartbeat_timeout_seconds: int = 60
    scheduler_scan_interval_seconds: int = 30

    # Task Settings
    task_max_attempts_default: int = 5
    task_email_timeout_seconds: int = 30
    task_image_resize_timeout_seconds: int = 60
    task_webhook_timeout_seconds: int = 30

    # Rate Limiting
    rate_limit_task_submission_per_minute: int = 60
    rate_limit_auth_per_minute: int = 20

    # Image Resize Handler
    image_max_dimension_px: int = 4096
    image_max_response_size_mb: int = 50
    image_output_dir: str = "data/images"

    # Webhook Handler
    webhook_max_response_size_kb: int = 1024

    # Email (SMTP)
    smtp_host: str = "smtp.mailtrap.io"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@taskforge.dev"

    # Backpressure
    backpressure_enabled: bool = False
    backpressure_queue_depth_threshold: int = 500

    # Sandbox
    sandbox_enabled: bool = True
    sandbox_cpu_limit_seconds: float = 30.0
    sandbox_memory_limit_mb: int = 256


@lru_cache
def get_settings() -> Settings:
    return Settings()
