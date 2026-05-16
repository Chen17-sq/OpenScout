from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `env_ignore_empty=True` so an env var set to "" in the shell (which is what
    # Claude Desktop and some other apps do for ANTHROPIC_API_KEY) doesn't block
    # the .env file's value from taking effect.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # SQLite for zero-friction local dev. Production uses Postgres + pgvector —
    # set DATABASE_URL=postgresql+psycopg://... in the deploy env.
    database_url: str = "sqlite:///./openscout.db"
    anthropic_api_key: str = ""
    semantic_scholar_api_key: str = ""
    resend_api_key: str = ""
    notify_email_to: str = ""
    ingest_secret: str = "change-me"
    frontend_origin: str = "http://localhost:5174"


settings = Settings()
