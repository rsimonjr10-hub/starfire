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

    fmp_api_key: str = ""

    # Inter-service communication (Railway private network)
    lumiscapital_service_url: str = ""
    osiris_service_url: str = ""
    inter_service_secret: str = "change-me-inter-service-secret"

    # OSIRIS Telegram bridge (@osiris_prime_bot)
    osiris_bot_token: str = ""
    osiris_telegram_chat_id: str = ""

    # LUMISNOVA Telegram bridge (@Lumiscapital_bot)
    lumisnova_bot_token: str = ""         # @Lumiscapital_bot token — sends data as LUMISNOVA
    lumisnova_telegram_chat_id: str = ""  # group chat_id where both bots are present

    google_client_id: str = ""
    google_client_secret: str = ""
    google_drive_credentials_json: Optional[str] = None
    google_drive_token_json: Optional[str] = None

    # SnapTrade brokerage aggregation
    snaptrade_client_id: str = ""
    snaptrade_consumer_key: str = ""

    # Voice transcription (Whisper) — set one or both; Groq tried first
    groq_api_key: str = ""
    openai_api_key: str = ""

    # Monitoring & self-healing
    sentry_dsn: str = ""
    admin_telegram_id: str = ""  # Telegram user ID to receive sentinel alerts

    # Railway self-redeploy (used by sentinel to restart the service on persistent failure)
    railway_token: str = ""
    railway_service_id: str = ""
    railway_environment_id: str = ""

    # Knowledge OS — embeddings model
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
