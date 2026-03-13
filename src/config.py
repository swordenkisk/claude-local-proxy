"""
config.py — Application settings loaded from .env
All application code reads settings exclusively from this module.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (two levels up from src/)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=False)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


# ── Provider ─────────────────────────────────────────────────────
API_PROVIDER: str = _env("API_PROVIDER", "anthropic")  # "anthropic" | "remote"
ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
REMOTE_INFERENCE_URL: str = _env("REMOTE_INFERENCE_URL")

# ── Model ─────────────────────────────────────────────────────────
DEFAULT_MODEL: str = _env("MODEL", "claude-3-haiku-20240307")
MAX_TOKENS: int = _int("MAX_TOKENS", 4096)

# ── Server ────────────────────────────────────────────────────────
BIND_ADDR: str = _env("BIND_ADDR", "127.0.0.1")
PORT: int = _int("PORT", 8080)

# ── Security ──────────────────────────────────────────────────────
UI_AUTH_TOKEN: str = _env("UI_AUTH_TOKEN")      # empty = no auth
RATE_LIMIT_PER_MINUTE: int = _int("RATE_LIMIT_PER_MINUTE", 20)

# ── Conversation ──────────────────────────────────────────────────
SYSTEM_PROMPT: str = _env("SYSTEM_PROMPT")
DB_PATH: str = _env("DB_PATH", str(_ROOT / "data" / "conversations.db"))

# ── Templates / Static dirs ───────────────────────────────────────
TEMPLATES_DIR: Path = _ROOT / "templates"
STATIC_DIR: Path = _ROOT / "static"
DATA_DIR: Path = Path(DB_PATH).parent

# ── Supported models ─────────────────────────────────────────────
ANTHROPIC_MODELS = [
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620",
]

# ── Validation ────────────────────────────────────────────────────

def validate() -> list[str]:
    """Return a list of configuration warnings (not fatal errors)."""
    warnings = []
    if API_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        warnings.append(
            "ANTHROPIC_API_KEY is not set. "
            "Set it in .env or export ANTHROPIC_API_KEY=sk-ant-..."
        )
    if API_PROVIDER == "remote" and not REMOTE_INFERENCE_URL:
        warnings.append(
            "API_PROVIDER=remote but REMOTE_INFERENCE_URL is not set."
        )
    if BIND_ADDR != "127.0.0.1" and not UI_AUTH_TOKEN:
        warnings.append(
            f"BIND_ADDR={BIND_ADDR} exposes the server on the network "
            "but UI_AUTH_TOKEN is not set. Anyone on the network can use your API key."
        )
    return warnings
