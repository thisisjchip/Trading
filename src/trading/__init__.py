"""Kraken trend-following trading system.

Phase 1 delivers the exchange-adapter abstraction and the local OHLCV data
layer. Strategy, backtest, validation, paper-trading and live-execution layers
are added in later phases and plug in behind the same adapter interface.
"""

__version__ = "0.1.0"
