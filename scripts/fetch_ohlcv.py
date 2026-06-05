#!/usr/bin/env python3
"""Fetch & cache historical OHLCV for a symbol/timeframe.

Examples
--------
    # Spot BTC/USD daily into the local parquet cache (public data, no keys):
    python scripts/fetch_ohlcv.py --exchange kraken_spot --symbol BTC/USD --timeframe 1d

    # Futures (demo) perp hourly:
    python scripts/fetch_ohlcv.py --exchange kraken_futures --symbol XBT/USD --timeframe 1h
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml  # noqa: E402

from trading.config import get_settings  # noqa: E402
from trading.data import OHLCVCache  # noqa: E402
from trading.exchanges import create_exchange  # noqa: E402
from trading.symbols import parse_symbol  # noqa: E402


def _fetch_one(cache, exchange, symbol, timeframe, full):
    df = cache.update(exchange, symbol, timeframe, force_full=full)
    if df.empty:
        print(f"  {symbol.canonical} {timeframe}: no data returned.")
        return False
    print(
        f"  {symbol.canonical} {timeframe}: {len(df)} bars  "
        f"{df.index.min()} -> {df.index.max()}"
    )
    return True


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exchange", default=None, help="kraken_spot | kraken_futures | kraken_us_perps")
    p.add_argument("--symbol", help="e.g. BTC/USD, XBT/USD, ETH/USD")
    p.add_argument("--timeframe", default="1d", help="1m,5m,15m,30m,1h,4h,12h,1d,1w")
    p.add_argument("--config", help="YAML file listing a series universe to refresh")
    p.add_argument("--full", action="store_true", help="force a full re-fetch")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.config and not args.symbol:
        p.error("provide --symbol or --config")

    settings = get_settings()
    cache = OHLCVCache(settings.data_cache_dir)

    if args.config:
        cfg = yaml.safe_load(Path(args.config).read_text())
        exchange = create_exchange(args.exchange or cfg.get("exchange"), settings)
        print(f"{exchange.name}: refreshing {len(cfg.get('series', []))} series")
        ok = True
        for s in cfg.get("series", []):
            ok &= _fetch_one(
                cache, exchange, parse_symbol(s["symbol"]),
                s.get("timeframe", "1d"), args.full,
            )
        return 0 if ok else 1

    exchange = create_exchange(args.exchange, settings)
    symbol = parse_symbol(args.symbol)
    ok = _fetch_one(cache, exchange, symbol, args.timeframe, args.full)
    if ok:
        print(f"Cached at: {cache.path_for(exchange.name, symbol, args.timeframe)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
