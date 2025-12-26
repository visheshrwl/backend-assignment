from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="Database connection string, e.g. sqlite+aiosqlite:////data/app.db")
    WEBHOOK_SECRET: str = Field(..., description="Secret for HMAC signature verification")
    LOG_LEVEL: str = Field("INFO", description="Logging level")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

def get_settings() -> Settings:
    return Settings()
