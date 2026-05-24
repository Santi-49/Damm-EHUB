from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://hackathon:changeme@localhost:5432/hackathon"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OPA
    opa_url: str = "http://localhost:8181"

    # JWT
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # App
    first_admin_email: str = "admin@example.com"
    first_admin_password: str = "changeme"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # LineWise chat (LangChain + OpenAI). Leave empty to fall back to a
    # canned reply so the demo still works without a key.
    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    chat_max_tokens: int = 1600

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
