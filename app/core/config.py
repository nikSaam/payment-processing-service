from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "payment-service"
    environment: str = "local"
    api_key: str = "change-me-in-production"
    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    payments_exchange: str = "payments"
    payments_queue: str = "payments.new"
    outbox_poll_interval: float = 1.0
    outbox_batch_size: int = 50
    payment_min_processing_seconds: int = 2
    payment_max_processing_seconds: int = 5
    webhook_timeout_seconds: float = 5.0
    webhook_max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
