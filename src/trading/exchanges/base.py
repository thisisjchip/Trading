"""Abstract exchange interface and shared domain models.

This is the contract every adapter implements and the ONLY surface that
strategy / backtest / execution code is allowed to import. Keeping the models
exchange-agnostic is what lets us swap KrakenSpot -> KrakenFutures ->
KrakenUSPerps with a config change.

Design notes
------------
* All instruments are addressed by the canonical :class:`~trading.symbols.Symbol`
  (``BASE/QUOTE``). Adapters translate to their wire format internally.
* OHLCV is returned as a tidy :class:`pandas.DataFrame` for the data/backtest
  layers, plus a typed-row helper for streaming use.
* Order placement takes an :class:`Order` request and returns an
  :class:`OrderResult`. ``client_order_id`` is first-class to support the
  idempotent placement required in Phase 6.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pandas as pd

from ..symbols import Symbol


# --- Enums -----------------------------------------------------------------

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    TAKE_PROFIT = "take_profit"


class TimeInForce(str, Enum):
    GTC = "gtc"  # good-till-cancelled
    IOC = "ioc"  # immediate-or-cancel
    GTD = "gtd"  # good-till-date


# Canonical OHLCV DataFrame schema. Adapters MUST return exactly these columns,
# indexed by a tz-aware UTC DatetimeIndex named "timestamp".
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


# --- Domain models ---------------------------------------------------------

@dataclass(frozen=True)
class OHLCVBar:
    """A single OHLCV candle (typed row for streaming / non-DataFrame use)."""

    timestamp: datetime  # tz-aware UTC, bar OPEN time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBook:
    symbol: Symbol
    bids: list[OrderBookLevel]  # descending price
    asks: list[OrderBookLevel]  # ascending price
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0


@dataclass(frozen=True)
class Order:
    """An order *request* handed to :meth:`Exchange.place_order`."""

    symbol: Symbol
    side: OrderSide
    type: OrderType
    size: float                          # in base units / contracts
    price: Optional[float] = None        # required for LIMIT
    stop_price: Optional[float] = None   # required for STOP / TAKE_PROFIT
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    # Idempotency key. Adapters pass this through to the exchange so retries /
    # restarts cannot create duplicate orders (Phase 6 requirement).
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class OrderResult:
    """The outcome of an order request."""

    order_id: str
    client_order_id: Optional[str]
    symbol: Symbol
    side: OrderSide
    type: OrderType
    size: float
    status: str                       # exchange-reported status string
    filled_size: float = 0.0
    avg_fill_price: Optional[float] = None
    raw: Optional[dict] = None        # original exchange payload for auditing


@dataclass(frozen=True)
class Position:
    symbol: Symbol
    size: float            # signed: positive long, negative short
    entry_price: float
    mark_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    leverage: Optional[float] = None
    raw: Optional[dict] = None


@dataclass(frozen=True)
class Balance:
    asset: str
    total: float
    available: float
    raw: Optional[dict] = None


# --- The interface ---------------------------------------------------------

class ExchangeError(Exception):
    """Base class for adapter-raised errors."""


class Exchange(abc.ABC):
    """Abstract execution + market-data target.

    Concrete adapters: :class:`KrakenSpot`, :class:`KrakenFutures`,
    :class:`KrakenUSPerps` (stub).
    """

    #: Stable identifier, e.g. "kraken_spot". Used by the factory + logging.
    name: str = "abstract"

    #: Whether this adapter trades a perpetual product (=> funding applies).
    supports_funding: bool = False

    #: True when this adapter is pointed at a paper/demo/sim endpoint.
    is_paper: bool = True

    # -- Market data --------------------------------------------------------

    @abc.abstractmethod
    def get_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        *,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return OHLCV as a DataFrame with :data:`OHLCV_COLUMNS`.

        Indexed by tz-aware UTC ``timestamp`` (bar open). ``timeframe`` is a
        human string like ``"1m"``, ``"1h"``, ``"1d"``; adapters map it to the
        exchange's native granularity.
        """

    @abc.abstractmethod
    def get_orderbook(self, symbol: Symbol, depth: int = 10) -> OrderBook:
        """Return the current order book up to ``depth`` levels per side."""

    @abc.abstractmethod
    def get_funding_rate(self, symbol: Symbol) -> Optional[float]:
        """Current funding rate for a perp (per 8h), or ``None`` for spot."""

    # -- Account ------------------------------------------------------------

    @abc.abstractmethod
    def get_balance(self) -> list[Balance]:
        """Return per-asset balances. Requires credentials."""

    @abc.abstractmethod
    def get_positions(self) -> list[Position]:
        """Return open positions. Spot adapters may derive from balances."""

    # -- Execution ----------------------------------------------------------

    @abc.abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """Place an order. Honour ``client_order_id`` for idempotency.

        Adapters MUST refuse real orders unless the global LIVE gate is set;
        see :func:`trading.exchanges.factory.create_exchange`.
        """

    @abc.abstractmethod
    def cancel_order(self, order_id: str, *, symbol: Optional[Symbol] = None) -> bool:
        """Cancel an order by id. Returns True on success."""

    # -- Capabilities -------------------------------------------------------

    @abc.abstractmethod
    def supported_timeframes(self) -> list[str]:
        """Human timeframe strings this adapter can serve."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        mode = "paper" if self.is_paper else "LIVE"
        return f"<{self.__class__.__name__} name={self.name!r} mode={mode}>"
