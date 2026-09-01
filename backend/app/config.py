"""TaskForge application configuration via pydantic-settings."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    database_url: str = "postgresql+asyncpg://taskforge:taskforge_dev_secret@localhost:5432/taskforge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://taskforge:taskforge_dev_secret@localhost:5672/taskforge"
    rabbitmq_vhost: str = "taskforge"
    rabbitmq_management_url: str = "http://taskforge:taskforge_dev_secret@rabbitmq:15672"

    # JWT
    jwt_secret_key: str = "change_me_generate_a_real_secret_here"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Worker
    worker_concurrency: int = 4
    worker_hostname: str = "worker-local"

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
