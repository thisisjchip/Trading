# Kraken Trend-Following Trading System

A trend-following algo-trading system for Kraken, built behind a clean
**exchange adapter** so the execution target (spot → futures-demo → US
perps) is a *config change*, not a code rewrite.

> **Status:** Phase 1 complete (exchange adapter + data layer). Live trading is
> **disabled** and gated behind an explicit `LIVE=true` flag. Nothing places a
> real order yet.

## Why the adapter

I'm a US trader. Kraken announced (May 29 2026) CFTC-regulated crypto
**perpetual futures** for eligible US clients (~30-day rollout, cleared via
Bitnomial / Kraken Derivatives US). Those perps **aren't live for me yet**, so
the whole system is built now against Kraken's existing **Spot** and
**Futures (demo)** APIs behind an `Exchange` interface, with a clearly-marked
`KrakenUSPerps` stub to fill in at launch. No endpoint is hardcoded into
strategy/backtest logic.

## Roadmap

| Phase | Scope | State |
|------:|-------|-------|
| 1 | Exchange adapter interface + cached OHLCV data layer | ✅ done |
| 2 | Vectorized backtester (fees, funding, slippage, no-lookahead) | ⏳ |
| 3 | Strategy framework (MA-cross, Donchian, MACD, ADX-filtered) | ⏳ |
| 4 | Overfitting validation (IS/OOS, walk-forward) | ⏳ |
| 5 | Paper trading vs demo-futures | ⏳ |
| 6 | Live execution (risk controls, idempotency, audit) — `LIVE=true` only | ⏳ |

## Phase 1 — what's built

```
src/trading/
  config.py              # .env-driven Settings + LIVE safety gate (no hardcoded keys)
  symbols.py             # canonical BASE/QUOTE <-> spot REST / spot WS / futures product id
  timeframes.py          # "1h" -> spot minutes / futures resolution string
  utils/ratelimit.py     # token bucket + retry-with-backoff (HTTP 429 / Retry-After)
  exchanges/
    base.py              # abstract Exchange + domain models (Order, Position, OHLCV ...)
    kraken_spot.py       # Spot adapter (paper = server-side `validate`, no fills)
    kraken_futures.py    # Futures adapter (demo-futures by default; funding rate exposed)
    kraken_us_perps.py   # STUB — endpoint/auth TBD at US-perp launch (raises until then)
    factory.py           # config -> adapter; enforces the LIVE gate in one place
  data/ohlcv_cache.py    # parquet cache with incremental refresh
scripts/fetch_ohlcv.py   # CLI: fetch & cache OHLCV (single series or a YAML universe)
config/data.yaml         # example series universe to cache
tests/                   # symbol translation, factory/adapter contract, cache behaviour
```

### The interface (what later phases depend on)

Everything above strategy level imports only `trading.exchanges.Exchange`:

```python
get_ohlcv(symbol, timeframe, since=, limit=) -> pandas.DataFrame  # canonical OHLCV schema
get_orderbook(symbol, depth=) -> OrderBook
get_funding_rate(symbol) -> float | None                          # per-8h; None for spot
get_balance() -> list[Balance]
get_positions() -> list[Position]
place_order(Order) -> OrderResult                                 # honours client_order_id
cancel_order(order_id, symbol=) -> bool
supported_timeframes() -> list[str]
```

### Safety model (already wired, matters from Phase 6)

- **Paper by default.** `LIVE` must be exactly `true` to place real orders.
- **Spot paper mode** uses Kraken's server-side `validate` flag — the order is
  checked by Kraken but never placed.
- **Futures** defaults to `demo-futures.kraken.com`. A *production* futures
  order is refused unless `LIVE=true`.
- **US perps** stub raises `NotImplementedError` everywhere so nothing can route
  through an unverified path.
- `client_order_id` is first-class on every order for idempotent placement.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # or: pip install -r requirements.txt
cp .env.example .env        # then fill in keys as needed (.env is git-ignored)
pytest                      # 11 tests, offline
```

## Usage

```bash
# Public OHLCV (no keys). Spot BTC/USD daily, cached to parquet:
python scripts/fetch_ohlcv.py --exchange kraken_spot --symbol BTC/USD --timeframe 1d -v

# Futures demo perp, hourly:
python scripts/fetch_ohlcv.py --exchange kraken_futures --symbol XBT/USD --timeframe 1h -v

# Refresh a whole universe (incremental):
python scripts/fetch_ohlcv.py --config config/data.yaml -v
```

Symbol spellings are translated for you: `BTC/USD` → `XBT/USD` canonical →
`XBTUSD` (spot REST) / `XBT/USD` (spot WS) / `PI_XBTUSD` (futures product).

## ⚠️ Network note for the cloud sandbox

This repo was developed in Claude Code's remote sandbox, whose **egress
allowlist does not include Kraken hosts** (`api.kraken.com`,
`futures.kraken.com`, `demo-futures.kraken.com` all return
`403 Host not in allowlist`). The code, adapters and cache are exercised by the
offline test suite; **live data fetches must be run locally** (or from an
environment whose network policy permits those hosts). Nothing in the code
hardcodes around this — it's purely the sandbox's network policy.

## Configuration (`.env`)

See `.env.example`. Key vars: `LIVE`, `EXCHANGE`, the three key/secret pairs,
`KRAKEN_FUTURES_DEMO` (default `true`), `KRAKEN_US_PERPS_BASE_URL` (blank until
launch), `DATA_CACHE_DIR`.
