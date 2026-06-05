"""Kraken Spot adapter (REST via python-kraken-sdk).

Public market data needs no keys; balance/positions/orders do. In paper mode
order placement uses Kraken's server-side ``validate`` flag, which checks the
order without ever placing it — so we exercise the real code path with zero risk
of a real fill.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from kraken.spot import Market as SpotMarket
from kraken.spot import Trade as SpotTrade
from kraken.spot import User as SpotUser

from ..config import Credentials
from ..symbols import Symbol, to_spot_rest
from ..timeframes import to_spot_interval
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

# Kraken spot order type strings.
_ORDER_TYPE = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP: "stop-loss",
    OrderType.TAKE_PROFIT: "take-profit",
}


class KrakenSpot(Exchange):
    name = "kraken_spot"
    supports_funding = False  # spot has no funding

    def __init__(self, creds: Optional[Credentials] = None, *, live: bool = False):
        creds = creds or Credentials()
        self._live = live
        self.is_paper = not live
        # Public client (no auth) for market data.
        self._market = SpotMarket()
        # Authenticated clients are created lazily / only if keys exist.
        self._user = (
            SpotUser(key=creds.api_key, secret=creds.api_secret)
            if creds.configured
            else None
        )
        self._trade = (
            SpotTrade(key=creds.api_key, secret=creds.api_secret)
            if creds.configured
            else None
        )

    # -- helpers ------------------------------------------------------------

    def _require_auth(self):
        if self._user is None or self._trade is None:
            raise ExchangeError(
                "Kraken Spot private call requires KRAKEN_SPOT_API_KEY/SECRET."
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
        interval = to_spot_interval(timeframe)
        pair = to_spot_rest(symbol)
        since_s = int(since.timestamp()) if since else None
        resp = self._market.get_ohlc(pair=pair, interval=interval, since=since_s)
        # Response: { <kraken-pair-name>: [[time,o,h,l,c,vwap,vol,count], ...],
        #             "last": <ts> }
        rows = None
        for key, val in resp.items():
            if key == "last":
                continue
            rows = val
            break
        if not rows:
            return _empty_ohlcv()
        df = pd.DataFrame(
            rows,
            columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"],
        )
        df = df[["time", "open", "high", "low", "close", "volume"]].astype(float)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.drop(columns=["time"]).set_index("timestamp")[OHLCV_COLUMNS]
        if limit:
            df = df.iloc[-limit:]
        return df

    def get_orderbook(self, symbol: Symbol, depth: int = 10) -> OrderBook:
        pair = to_spot_rest(symbol)
        resp = self._market.get_order_book(pair=pair, count=depth)
        book = next(iter(resp.values())) if resp else {"asks": [], "bids": []}
        asks = [OrderBookLevel(float(p), float(v)) for p, v, *_ in book.get("asks", [])]
        bids = [OrderBookLevel(float(p), float(v)) for p, v, *_ in book.get("bids", [])]
        return OrderBook(symbol=symbol, bids=bids, asks=asks)

    def get_funding_rate(self, symbol: Symbol) -> Optional[float]:
        return None  # spot: no funding

    # -- account ------------------------------------------------------------

    def get_balance(self) -> list[Balance]:
        self._require_auth()
        out: list[Balance] = []
        try:
            # get_balances() separates held (in-order) from free where available.
            data = self._user.get_balances()
            for asset, info in data.items():
                if isinstance(info, dict):
                    total = float(info.get("balance", 0) or 0)
                    hold = float(info.get("hold_trade", 0) or 0)
                    out.append(Balance(asset, total, total - hold, raw=info))
                else:
                    bal = float(info or 0)
                    out.append(Balance(asset, bal, bal))
        except Exception:  # noqa: BLE001 - fall back to simpler endpoint
            data = self._user.get_account_balance()
            for asset, bal in data.items():
                b = float(bal or 0)
                out.append(Balance(asset, b, b))
        return out

    def get_positions(self) -> list[Position]:
        # Spot has no positions unless margin is used. Report open margin
        # positions if any; otherwise empty.
        self._require_auth()
        try:
            data = self._user.get_open_positions()
        except Exception:  # noqa: BLE001
            return []
        out: list[Position] = []
        for _, p in (data or {}).items():
            try:
                vol = float(p.get("vol", 0))
                signed = vol if p.get("type") == "buy" else -vol
                out.append(
                    Position(
                        symbol=Symbol(*_split_pair(p.get("pair", ""))),
                        size=signed,
                        entry_price=float(p.get("cost", 0)) / vol if vol else 0.0,
                        raw=p,
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        return out

    # -- execution ----------------------------------------------------------

    def place_order(self, order: Order) -> OrderResult:
        self._require_auth()
        validate = not self._live  # paper mode => server-side validate, no fill
        kwargs = dict(
            ordertype=_ORDER_TYPE[order.type],
            side=order.side.value,
            pair=to_spot_rest(order.symbol),
            volume=order.size,
            validate=validate,
        )
        if order.price is not None:
            kwargs["price"] = order.price
        if order.stop_price is not None:
            kwargs["price"] = order.stop_price  # trigger price for stop types
        if order.client_order_id is not None:
            # Spot uses an integer userref for client-side correlation.
            kwargs["userref"] = _userref_from(order.client_order_id)
        if order.reduce_only:
            kwargs["reduce_only"] = True

        resp = self._trade.create_order(**kwargs)
        txids = (resp or {}).get("txid", []) or []
        order_id = txids[0] if txids else ("VALIDATED" if validate else "")
        return OrderResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            size=order.size,
            status="validated" if validate else "submitted",
            raw=resp,
        )

    def cancel_order(self, order_id: str, *, symbol: Optional[Symbol] = None) -> bool:
        self._require_auth()
        resp = self._trade.cancel_order(txid=order_id)
        return bool((resp or {}).get("count", 0))

    def supported_timeframes(self) -> list[str]:
        return ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


def _empty_ohlcv() -> pd.DataFrame:
    df = pd.DataFrame(columns=OHLCV_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return df


def _split_pair(pair: str) -> tuple[str, str]:
    # Best-effort split of a Kraken margin pair like "XXBTZUSD".
    from ..symbols import parse_symbol

    s = parse_symbol(pair)
    return s.base, s.quote


def _userref_from(client_order_id: str) -> int:
    # Kraken's userref is a signed 32-bit int. Hash the client id stably.
    import zlib

    return zlib.crc32(client_order_id.encode()) & 0x7FFFFFFF
