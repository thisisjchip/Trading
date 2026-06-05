"""Kraken US Perpetual Futures adapter — STUB (not live yet).

Background
----------
Kraken announced (May 29 2026, ~30-day rollout) CFTC-regulated crypto PERPETUAL
FUTURES for eligible US clients, cleared via Bitnomial / Kraken Derivatives US.
As of this build they are NOT available to us.

WHAT IS UNKNOWN / TBD AT LAUNCH
-------------------------------
* Endpoint/routing. Two plausible shapes:
    1. The SAME futures REST/WS API (futures.kraken.com / derivatives v3) with
       US-eligible products simply enabled on the account. If so, this adapter
       collapses to a thin subclass of :class:`KrakenFutures` pointed at a
       different base URL.
    2. A Bitnomial-specific / Kraken Derivatives US route with its own auth,
       product ids, and clearing semantics. If so, we implement the same
       :class:`Exchange` interface here against that API.
  Set ``KRAKEN_US_PERPS_BASE_URL`` (+ keys) once Kraken publishes details.
* Product id scheme (may differ from PI_/PF_), contract specs, tick sizes.
* Funding mechanics and leverage caps under CFTC rules (expect conservative
  caps — the backtester already supports a configurable max-leverage cap).

Until then every method raises :class:`NotImplementedError` so nothing can
accidentally route live US-perp orders through an unverified path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from ..config import Credentials
from ..symbols import Symbol
from .base import (
    Balance,
    Exchange,
    Order,
    OrderBook,
    OrderResult,
    Position,
)

_NOT_LIVE = (
    "KrakenUSPerps is a stub: CFTC-regulated US perps are not live for this "
    "account yet. Fill in endpoint/auth from Kraken's launch docs "
    "(set KRAKEN_US_PERPS_BASE_URL + keys), then implement against the "
    "Exchange interface. See module docstring for the two likely API shapes."
)


class KrakenUSPerps(Exchange):
    name = "kraken_us_perps"
    supports_funding = True  # perps => funding applies once live

    def __init__(
        self,
        creds: Optional[Credentials] = None,
        *,
        base_url: str = "",
        live: bool = False,
    ):
        self._creds = creds or Credentials()
        self._base_url = base_url
        self._live = live
        # Stub is never a usable paper target; mark paper to be safe.
        self.is_paper = True

    # Every method intentionally unimplemented until launch details land.

    def get_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        *,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(_NOT_LIVE)

    def get_orderbook(self, symbol: Symbol, depth: int = 10) -> OrderBook:
        raise NotImplementedError(_NOT_LIVE)

    def get_funding_rate(self, symbol: Symbol) -> Optional[float]:
        raise NotImplementedError(_NOT_LIVE)

    def get_balance(self) -> list[Balance]:
        raise NotImplementedError(_NOT_LIVE)

    def get_positions(self) -> list[Position]:
        raise NotImplementedError(_NOT_LIVE)

    def place_order(self, order: Order) -> OrderResult:
        raise NotImplementedError(_NOT_LIVE)

    def cancel_order(self, order_id: str, *, symbol: Optional[Symbol] = None) -> bool:
        raise NotImplementedError(_NOT_LIVE)

    def supported_timeframes(self) -> list[str]:
        raise NotImplementedError(_NOT_LIVE)
