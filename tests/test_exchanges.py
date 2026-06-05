import pandas as pd
import pytest

from trading.config import Credentials, Settings
from trading.exchanges import Exchange, create_exchange
from trading.exchanges.base import OHLCV_COLUMNS
from trading.exchanges.kraken_futures import KrakenFutures
from trading.exchanges.kraken_spot import KrakenSpot
from trading.exchanges.kraken_us_perps import KrakenUSPerps
from trading.symbols import parse_symbol


def test_factory_selects_adapters():
    base = dict(spot=Credentials(), futures=Credentials(), us_perps=Credentials())
    assert isinstance(
        create_exchange("kraken_spot", Settings(exchange="kraken_spot", **base)),
        KrakenSpot,
    )
    assert isinstance(
        create_exchange("kraken_futures", Settings(exchange="kraken_futures", **base)),
        KrakenFutures,
    )
    assert isinstance(
        create_exchange("kraken_us_perps", Settings(exchange="kraken_us_perps", **base)),
        KrakenUSPerps,
    )


def test_factory_rejects_unknown():
    with pytest.raises(Exception):
        create_exchange("bitmex", Settings())


def test_futures_defaults_to_demo_paper():
    fut = create_exchange("kraken_futures", Settings(exchange="kraken_futures"))
    assert fut.is_paper is True  # demo by default


def test_us_perps_stub_raises():
    perp = KrakenUSPerps()
    with pytest.raises(NotImplementedError):
        perp.get_ohlcv(parse_symbol("XBT/USD"), "1h")
    with pytest.raises(NotImplementedError):
        perp.place_order(None)  # type: ignore[arg-type]


def test_spot_place_order_requires_auth():
    spot = KrakenSpot(Credentials())  # no keys
    with pytest.raises(Exception):
        spot.get_balance()


def test_all_adapters_implement_interface():
    for cls in (KrakenSpot, KrakenFutures, KrakenUSPerps):
        assert issubclass(cls, Exchange)
        # No abstract methods left unimplemented.
        assert not getattr(cls, "__abstractmethods__", set())
