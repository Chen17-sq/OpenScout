"""Provider-agnostic LLM client.

OpenScout supports two LLM providers:
  - Anthropic Claude (claude-haiku-4-5)
  - DeepSeek (deepseek-chat) — OpenAI-compatible API, cheaper

Picks based on `settings.llm_provider`. Both providers expose a similar JSON
chat API; we hide the differences behind one `complete()` function.

Returns (text, error) — `text=None` signals an API failure that the caller
must treat as "skip / leave as-is" (NOT as a negative answer).
"""

import httpx

from ..config import settings


def _provider() -> str:
    """Pick provider based on config + which key is present."""
    explicit = (settings.llm_provider or "").lower().strip()
    if explicit in ("anthropic", "deepseek"):
        return explicit
    # Auto: prefer deepseek (cheaper) if its key is set, else anthropic.
    if settings.deepseek_api_key:
        return "deepseek"
    if settings.anthropic_api_key:
        return "anthropic"
    return "none"


def is_available() -> bool:
    return _provider() != "none"


def provider_name() -> str:
    return _provider()


def complete(prompt: str, max_tokens: int = 200) -> tuple[str | None, str | None]:
    """Single user-turn completion. Returns (text, error_message).

    On API failure: text=None, error_message=<reason>. Caller must NOT treat
    None as a negative answer.
    """
    prov = _provider()
    if prov == "none":
        return None, "no provider configured (set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY)"

    try:
        if prov == "deepseek":
            return _deepseek_complete(prompt, max_tokens)
        return _anthropic_complete(prompt, max_tokens)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:160]}"


def _anthropic_complete(prompt: str, max_tokens: int) -> tuple[str | None, str | None]:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if not resp.content:
        return None, "empty response"
    return resp.content[0].text.strip(), None


def _deepseek_complete(prompt: str, max_tokens: int) -> tuple[str | None, str | None]:
    """DeepSeek uses an OpenAI-compatible chat completions endpoint."""
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=body,
        )
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:160]}"
    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        return None, "no choices in response"
    text = (choices[0].get("message") or {}).get("content") or ""
    return text.strip(), None
