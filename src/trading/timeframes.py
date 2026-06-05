"""Timeframe normalisation across spot and futures wire formats.

Internally we use human strings (``"1m"``, ``"1h"``, ``"1d"`` ...). Spot REST
wants an interval in *minutes*; futures charts want a *resolution string*.
"""

from __future__ import annotations

# Canonical timeframe -> seconds. Order matters for display only.
TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}

# Spot REST OHLC interval is in minutes (Kraken supported set).
_SPOT_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}

# Futures charts resolution strings (Kraken supported set).
_FUTURES_RESOLUTION: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "12h": "12h",
    "1d": "1d",
    "1w": "1w",
}


def timeframe_seconds(tf: str) -> int:
    try:
        return TIMEFRAME_SECONDS[tf]
    except KeyError as exc:
        raise ValueError(
            f"Unknown timeframe {tf!r}; valid: {sorted(TIMEFRAME_SECONDS)}"
        ) from exc


def to_spot_interval(tf: str) -> int:
    try:
        return _SPOT_MINUTES[tf]
    except KeyError as exc:
        raise ValueError(
            f"Spot does not support timeframe {tf!r}; valid: {sorted(_SPOT_MINUTES)}"
        ) from exc


def to_futures_resolution(tf: str) -> str:
    try:
        return _FUTURES_RESOLUTION[tf]
    except KeyError as exc:
        raise ValueError(
            f"Futures does not support timeframe {tf!r}; "
            f"valid: {sorted(_FUTURES_RESOLUTION)}"
        ) from exc
