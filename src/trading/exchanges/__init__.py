"""Exchange adapters.

Strategy and backtest code depend ONLY on :class:`trading.exchanges.base.Exchange`.
Concrete adapters (spot, futures-demo, future US perps) live behind it so the
execution target is a config switch, not a code change.
"""

from .base import (
    Balance,
    Exchange,
    ExchangeError,
    Order,
    OrderBook,
    OrderResult,
    OrderSide,
    OrderType,
    OHLCVBar,
    Position,
    TimeInForce,
)
from .factory import create_exchange

__all__ = [
    "Exchange",
    "ExchangeError",
    "OHLCVBar",
    "OrderBook",
    "Order",
    "OrderResult",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "Position",
    "Balance",
    "create_exchange",
]
