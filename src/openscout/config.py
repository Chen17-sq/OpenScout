import shutil
import subprocess
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


def _from_keychain(name: str) -> str:
    """Fetch `name` from macOS Keychain (service=OpenScout, account=name).

    Returns "" if not found, not macOS, or `security` not available.
    """
    if sys.platform != "darwin" or not shutil.which("security"):
        return ""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "OpenScout", "-a", name, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


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
    # LLM provider — "anthropic" / "deepseek" / "" (auto: prefer deepseek if key set)
    llm_provider: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    semantic_scholar_api_key: str = ""
    resend_api_key: str = ""
    notify_email_to: str = ""
    ingest_secret: str = "change-me"
    frontend_origin: str = "http://localhost:5174"


settings = Settings()

# Keychain fallback: if a key wasn't set via env / .env, try macOS Keychain.
# Useful after fresh-cloning the repo when .env is gitignored — the key
# survives across clones because it lives in Keychain.
for _kc_name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "RESEND_API_KEY", "INGEST_SECRET"):
    _kc_attr = _kc_name.lower()
    if not getattr(settings, _kc_attr, None) or getattr(settings, _kc_attr) == "change-me":
        _kc_value = _from_keychain(_kc_name)
        if _kc_value:
            setattr(settings, _kc_attr, _kc_value)
