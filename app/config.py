from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret_key: str = "dev-secret-key"
    log_level: str = "INFO"
    port: int = 8000

    database_url: str = "postgresql+asyncpg://starfire:password@localhost:5432/starfire_db"
    sync_database_url: str = "postgresql://starfire:password@localhost:5432/starfire_db"

    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str = ""

    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""

    broker_api_key: str = "mock"
    broker_api_secret: str = "mock"
    broker_base_url: str = "https://paper-api.alpaca.markets"
    use_mock_broker: bool = True

    risk_max_daily_loss_pct: float = 5.0
    risk_max_position_size_pct: float = 25.0
    risk_max_trades_per_day: int = 10

    google_drive_credentials_json: Optional[str] = None
    google_drive_token_json: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
