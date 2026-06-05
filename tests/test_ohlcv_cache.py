from datetime import datetime, timedelta, timezone

import pandas as pd

from trading.data import OHLCVCache
from trading.exchanges.base import OHLCV_COLUMNS, Exchange
from trading.symbols import parse_symbol


class FakeExchange(Exchange):
    """Deterministic in-memory exchange for cache tests."""

    name = "fake"

    def __init__(self, bars: pd.DataFrame):
        self._bars = bars

    def get_ohlcv(self, symbol, timeframe, *, since=None, limit=None):
        df = self._bars
        if since is not None:
            df = df[df.index >= pd.Timestamp(since)]
        return df

    # unused abstract methods
    def get_orderbook(self, symbol, depth=10): ...
    def get_funding_rate(self, symbol): ...
    def get_balance(self): ...
    def get_positions(self): ...
    def place_order(self, order): ...
    def cancel_order(self, order_id, *, symbol=None): ...
    def supported_timeframes(self): return ["1d"]


def _make_bars(start: datetime, n: int) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1D", tz="UTC", name="timestamp")
    df = pd.DataFrame(
        {c: [float(i + 1)] * n if c != "volume" else [10.0] * n for i, c in enumerate(OHLCV_COLUMNS)},
        index=idx,
    )
    return df


def test_cache_write_load_and_incremental(tmp_path):
    cache = OHLCVCache(tmp_path)
    sym = parse_symbol("XBT/USD")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    first = _make_bars(start, 5)
    ex = FakeExchange(first)
    out = cache.update(ex, sym, "1d", force_full=True)
    assert len(out) == 5

    loaded = cache.load("fake", sym, "1d")
    assert len(loaded) == 5
    assert list(loaded.columns) == OHLCV_COLUMNS
    assert str(loaded.index.tz) == "UTC"

    # Extend with 3 more bars; incremental merge should de-dup the overlap.
    extended = _make_bars(start, 8)
    ex2 = FakeExchange(extended)
    out2 = cache.update(ex2, sym, "1d")
    assert len(out2) == 8
    assert out2.index.is_monotonic_increasing
    assert not out2.index.has_duplicates
