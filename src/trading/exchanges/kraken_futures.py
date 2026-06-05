"""Kraken Futures adapter (REST via python-kraken-sdk).

Defaults to the demo (paper) cluster ``demo-futures.kraken.com``; the SDK's
``sandbox=True`` flag selects it. Production (``futures.kraken.com``) is only
used when ``demo=False`` AND the global LIVE gate is set.

Perpetual products (``PI_XBTUSD`` etc.) carry an 8-hour funding rate, surfaced
via :meth:`get_funding_rate` for the backtester to model.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from kraken.futures import Market as FutMarket
from kraken.futures import Trade as FutTrade
from kraken.futures import User as FutUser

from ..config import Credentials
from ..symbols import Symbol, parse_symbol, to_futures_product
from ..timeframes import to_futures_resolution
from .base import (
    OHLCV_COLUMNS,
    Balance,
    Exchange,
    ExchangeError,
    Order,
    OrderBook,
    OrderBookLevel,
    OrderResult,
    OrderSide,
    OrderType,
    Position,
)

logger = logging.getLogger(__name__)

_ORDER_TYPE = {
    OrderType.MARKET: "mkt",
    OrderType.LIMIT: "lmt",
    OrderType.STOP: "stp",
    OrderType.TAKE_PROFIT: "take_profit",
}


class KrakenFutures(Exchange):
    name = "kraken_futures"
    supports_funding = True

    def __init__(
        self,
        creds: Optional[Credentials] = None,
        *,
        demo: bool = True,
        live: bool = False,
        product_kind: str = "PI",
    ):
        creds = creds or Credentials()
        self._demo = demo
        self._live = live
        self._product_kind = product_kind
        # Paper whenever we're on demo OR not live-gated.
        self.is_paper = demo or not live

        sandbox = demo
        self._market = FutMarket(sandbox=sandbox)
        if creds.configured:
            self._user = FutUser(
                key=creds.api_key, secret=creds.api_secret, sandbox=sandbox
            )
            self._trade = FutTrade(
                key=creds.api_key, secret=creds.api_secret, sandbox=sandbox
            )
        else:
            self._user = None
            self._trade = None

    # -- helpers ------------------------------------------------------------

    def _product(self, symbol: Symbol) -> str:
        return to_futures_product(symbol, kind=self._product_kind)

    def _require_auth(self):
        if self._user is None or self._trade is None:
            raise ExchangeError(
                "Kraken Futures private call requires "
                "KRAKEN_FUTURES_API_KEY/SECRET."
            )

    # -- market data --------------------------------------------------------

    def get_ohlcv(
        self,
        symbol: Symbol,
        timeframe: str,
        *,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        resolution = to_futures_resolution(timeframe)
        product = self._product(symbol)
        from_ = int(since.timestamp()) if since else None
        resp = self._market.get_ohlc(
            tick_type="trade", symbol=product, resolution=resolution, from_=from_
        )
        candles = (resp or {}).get("candles", [])
        if not candles:
            return _empty_ohlcv()
        df = pd.DataFrame(candles)
        # candle 'time' is epoch milliseconds.
        df["timestamp"] = pd.to_datetime(df["time"].astype("int64"), unit="ms", utc=True)
        for col in OHLCV_COLUMNS:
            df[col] = df[col].astype(float)
        df = df.set_index("timestamp")[OHLCV_COLUMNS]
        if limit:
            df = df.iloc[-limit:]
        return df

    def get_orderbook(self, symbol: Symbol, depth: int = 10) -> OrderBook:
        product = self._product(symbol)
        resp = self._market.get_orderbook(symbol=product)
        book = (resp or {}).get("orderBook", resp or {})
        asks = [OrderBookLevel(float(p), float(v)) for p, v in book.get("asks", [])][:depth]
        bids = [OrderBookLevel(float(p), float(v)) for p, v in book.get("bids", [])][:depth]
        return OrderBook(symbol=symbol, bids=bids, asks=asks)

    def get_funding_rate(self, symbol: Symbol) -> Optional[float]:
        """Current funding rate (per 8h) for the perp, from the tickers feed."""
        product = self._product(symbol)
        resp = self._market.get_tickers()
        for t in (resp or {}).get("tickers", []):
            if t.get("symbol", "").upper() == product:
                # Kraken exposes fundingRate / fundingRatePrediction.
                fr = t.get("fundingRate")
                return float(fr) if fr is not None else None
        return None

    # -- account ------------------------------------------------------------

    def get_balance(self) -> list[Balance]:
        self._require_auth()
        resp = self._user.get_wallets()
        out: list[Balance] = []
        accounts = (resp or {}).get("accounts", {})
        for acct_name, acct in accounts.items():
            balances = acct.get("balances", {})
            for asset, amt in balances.items():
                b = float(amt or 0)
                if b:
                    out.append(Balance(f"{acct_name}:{asset}", b, b, raw=acct))
        return out

    def get_positions(self) -> list[Position]:
        self._require_auth()
        resp = self._user.get_open_positions()
        out: list[Position] = []
        for p in (resp or {}).get("openPositions", []):
            try:
                size = float(p.get("size", 0))
                signed = size if p.get("side") == "long" else -size
                out.append(
                    Position(
                        symbol=parse_symbol(p.get("symbol", "")),
                        size=signed,
                        entry_price=float(p.get("price", 0)),
                        unrealized_pnl=(
                            float(p["unrealizedFunding"])
                            if p.get("unrealizedFunding") is not None
                            else None
                        ),
                        raw=p,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return out

    # -- execution ----------------------------------------------------------

    def place_order(self, order: Order) -> OrderResult:
        self._require_auth()
        # Safety: a production-pointed futures adapter must not place real
        # orders unless explicitly LIVE. Demo endpoint is always safe.
        if not self._demo and not self._live:
            raise ExchangeError(
                "Refusing to place a PRODUCTION futures order while LIVE is not "
                "set. Use demo-futures or set LIVE=true."
            )
        kwargs = dict(
            orderType=_ORDER_TYPE[order.type],
            size=order.size,
            symbol=self._product(order.symbol),
            side=order.side.value,
        )
        if order.price is not None:
            kwargs["limitPrice"] = order.price
        if order.stop_price is not None:
            kwargs["stopPrice"] = order.stop_price
        if order.reduce_only:
            kwargs["reduceOnly"] = True
        if order.client_order_id is not None:
            kwargs["cliOrdId"] = order.client_order_id  # idempotency key

        resp = self._trade.create_order(**kwargs)
        send = (resp or {}).get("sendStatus", {})
        order_id = send.get("order_id", "")
        status = send.get("status", (resp or {}).get("result", "unknown"))
        return OrderResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            size=order.size,
            status=status,
            raw=resp,
        )

    def cancel_order(self, order_id: str, *, symbol: Optional[Symbol] = None) -> bool:
        self._require_auth()
        resp = self._trade.cancel_order(order_id=order_id)
        return (resp or {}).get("result") == "success"

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d", "1w"]


def _empty_ohlcv() -> pd.DataFrame:
    df = pd.DataFrame(columns=OHLCV_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return df
