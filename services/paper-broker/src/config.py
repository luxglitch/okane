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

    # Paper portfolio
    starting_balance: float = 10000.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8001

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
