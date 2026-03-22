import base64
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Kalshi
    kalshi_api_key_id: str = ""
    kalshi_private_key_b64: str = ""
    kalshi_base_url: str = "https://trading-api.kalshi.com/trade-api/v2"
    use_demo_api: bool = False

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "okane"
    postgres_user: str = "okane"
    postgres_password: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Fetcher
    fetch_interval_seconds: int = 10
    kalshi_series: str = ""  # Comma-separated series tickers, e.g. "KXBTCD,KXETH"

    @property
    def series_list(self) -> list[str]:
        return [s.strip() for s in self.kalshi_series.split(",") if s.strip()]

    @property
    def base_url(self) -> str:
        if self.use_demo_api:
            return "https://demo-api.kalshi.co/trade-api/v2"
        return self.kalshi_base_url

    @property
    def private_key_pem(self) -> bytes:
        if not self.kalshi_private_key_b64:
            return b""
        return base64.b64decode(self.kalshi_private_key_b64)

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
