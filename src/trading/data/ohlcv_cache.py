"""Local OHLCV cache with incremental refresh (parquet-backed).

Each (exchange, symbol, timeframe) maps to one parquet file. ``update`` fetches
only the bars newer than what we already have, merges, de-duplicates, and
persists. Strategy/backtest code reads from here, not from the network.

Why parquet: columnar, compressed, fast to load into pandas, and trivially
inspectable. SQLite would also work; parquet is simpler for append-mostly time
series and keeps each series in its own file.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from ..exchanges.base import OHLCV_COLUMNS, Exchange
from ..symbols import Symbol
from ..timeframes import timeframe_seconds

logger = logging.getLogger(__name__)


def _safe(text: str) -> str:
    """Make a string safe for a filename."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)


class OHLCVCache:
    def __init__(self, cache_dir: Path | str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- paths --------------------------------------------------------------

    def path_for(self, exchange_name: str, symbol: Symbol, timeframe: str) -> Path:
        fname = f"{_safe(exchange_name)}__{_safe(symbol.canonical)}__{_safe(timeframe)}.parquet"
        return self.cache_dir / fname

    # -- read ---------------------------------------------------------------

    def load(
        self, exchange_name: str, symbol: Symbol, timeframe: str
    ) -> pd.DataFrame:
        """Load cached OHLCV (possibly empty) for a series."""
        path = self.path_for(exchange_name, symbol, timeframe)
        if not path.exists():
            return _empty()
        df = pd.read_parquet(path)
        return _normalise(df)

    # -- write / refresh ----------------------------------------------------

    def update(
        self,
        exchange: Exchange,
        symbol: Symbol,
        timeframe: str,
        *,
        since: Optional[datetime] = None,
        force_full: bool = False,
    ) -> pd.DataFrame:
        """Incrementally refresh a series and return the full cached frame.

        Fetches only bars after the last cached bar (unless ``force_full`` or an
        empty cache), merges, drops duplicate timestamps and the final
        (possibly still-forming) bar is kept but will be overwritten on the next
        refresh.
        """
        path = self.path_for(exchange.name, symbol, timeframe)
        existing = _empty() if force_full else self.load(exchange.name, symbol, timeframe)

        fetch_since = since
        if not existing.empty and not force_full:
            # Re-fetch from the last bar so the previously-incomplete bar gets
            # corrected; overlap is de-duplicated on merge.
            last_ts = existing.index.max().to_pydatetime()
            fetch_since = last_ts - timedelta(seconds=timeframe_seconds(timeframe))

        logger.info(
            "Refreshing %s %s %s (since=%s, have=%d bars)",
            exchange.name, symbol.canonical, timeframe, fetch_since, len(existing),
        )
        fresh = exchange.get_ohlcv(symbol, timeframe, since=fetch_since)
        fresh = _normalise(fresh)

        if existing.empty:
            merged = fresh
        elif fresh.empty:
            merged = existing
        else:
            merged = pd.concat([existing, fresh])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()

        if not merged.empty:
            merged.to_parquet(path)
            logger.info(
                "Cached %d bars (+%d new) -> %s",
                len(merged), max(0, len(merged) - len(existing)), path.name,
            )
        return merged

    def get(
        self,
        exchange: Exchange,
        symbol: Symbol,
        timeframe: str,
        *,
        refresh: bool = True,
        since: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Convenience: refresh (optional) then return the series."""
        if refresh:
            return self.update(exchange, symbol, timeframe, since=since)
        return self.load(exchange.name, symbol, timeframe)


def _empty() -> pd.DataFrame:
    df = pd.DataFrame(columns=OHLCV_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return df


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce any OHLCV frame to the canonical schema/index."""
    if df is None or df.empty:
        return _empty()
    df = df.copy()
    if df.index.name != "timestamp":
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx
    df.index.name = "timestamp"
    df = df[[c for c in OHLCV_COLUMNS if c in df.columns]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()
