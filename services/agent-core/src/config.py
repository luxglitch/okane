from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "okane"
    postgres_user: str = "okane"
    postgres_password: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8000

    # Paper broker
    paper_broker_url: str = "http://paper-broker:8001"

    # Kalshi API (for settlement lookups)
    kalshi_api_key_id: str = ""
    kalshi_private_key_b64: str = ""
    kalshi_base_url: str = "https://trading-api.kalshi.com/trade-api/v2"

    # LLM provider selection: anthropic | deepseek | llamacpp
    llm_provider: str = "anthropic"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # llama.cpp server
    llamacpp_base_url: str = "http://llamacpp:8080/v1"
    llamacpp_model: str = "local"

    # Agent behavior
    agent_cycle_seconds: int = 60
    min_signal_confidence: float = 0.50
    max_position_fraction: float = 0.05
    starting_balance: float = 10000.0
    llm_max_calls_per_minute: int = 10
    llm_max_calls_per_day: int = 200

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
