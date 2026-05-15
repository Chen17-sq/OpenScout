from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://openscout:openscout_dev@localhost:5433/openscout"
    anthropic_api_key: str = ""
    semantic_scholar_api_key: str = ""
    resend_api_key: str = ""
    notify_email_to: str = ""
    ingest_secret: str = "change-me"
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
