"""Configuration loading.

All secrets come from the environment (loaded from a local ``.env`` via
python-dotenv). Nothing here is ever hardcoded, and ``.env`` is git-ignored.

The :class:`Settings` object is the single source of truth for credentials,
the active exchange target, and the paper/live safety gate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env once at import time. Calling again is cheap and idempotent.
# We do NOT override variables already present in the real environment so that
# CI / container env vars win over a stray local .env.
load_dotenv(override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    """Strict-ish boolean parse. Only the obvious truthy spellings count."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return default if val is None else val.strip()


@dataclass(frozen=True)
class Credentials:
    """A single key/secret pair for one adapter."""

    api_key: str = ""
    api_secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings, built from the environment."""

    # Global safety gate: real orders require this to be exactly truthy.
    live: bool = False
    # Default adapter the app/CLI targets.
    exchange: str = "kraken_futures"

    spot: Credentials = field(default_factory=Credentials)
    futures: Credentials = field(default_factory=Credentials)
    us_perps: Credentials = field(default_factory=Credentials)

    # Futures: point at the demo (paper) cluster unless explicitly disabled.
    futures_demo: bool = True
    # US perps endpoint is TBD until launch; surfaced here for the stub.
    us_perps_base_url: str = ""

    data_cache_dir: Path = Path("data/cache")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            live=_env_bool("LIVE", False),
            exchange=_env_str("EXCHANGE", "kraken_futures").lower(),
            spot=Credentials(
                api_key=_env_str("KRAKEN_SPOT_API_KEY"),
                api_secret=_env_str("KRAKEN_SPOT_API_SECRET"),
            ),
            futures=Credentials(
                api_key=_env_str("KRAKEN_FUTURES_API_KEY"),
                api_secret=_env_str("KRAKEN_FUTURES_API_SECRET"),
            ),
            us_perps=Credentials(
                api_key=_env_str("KRAKEN_US_PERPS_API_KEY"),
                api_secret=_env_str("KRAKEN_US_PERPS_API_SECRET"),
            ),
            futures_demo=_env_bool("KRAKEN_FUTURES_DEMO", True),
            us_perps_base_url=_env_str("KRAKEN_US_PERPS_BASE_URL"),
            data_cache_dir=Path(_env_str("DATA_CACHE_DIR", "data/cache")),
        )


_settings: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Return the process-wide :class:`Settings` singleton."""
    global _settings
    if _settings is None or reload:
        if reload:
            load_dotenv(override=False)
        _settings = Settings.from_env()
    return _settings
