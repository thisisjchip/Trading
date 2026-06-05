from trading.symbols import (
    Symbol,
    parse_symbol,
    to_futures_product,
    to_spot_rest,
    to_spot_ws,
)


def test_parse_canonical_and_aliases():
    assert parse_symbol("XBT/USD").canonical == "XBT/USD"
    assert parse_symbol("BTC/USD").canonical == "XBT/USD"  # BTC -> XBT
    assert parse_symbol("eth/usd").canonical == "ETH/USD"


def test_parse_concatenated():
    assert parse_symbol("XBTUSD").canonical == "XBT/USD"
    assert parse_symbol("ETHUSDT").canonical == "ETH/USDT"
    assert parse_symbol("SOLUSDC").canonical == "SOL/USDC"


def test_parse_futures_product():
    assert parse_symbol("PI_XBTUSD").canonical == "XBT/USD"
    assert parse_symbol("PF_ETHUSD").canonical == "ETH/USD"


def test_wire_encoders():
    s = Symbol("XBT", "USD")
    assert to_spot_rest(s) == "XBTUSD"
    assert to_spot_ws(s) == "XBT/USD"
    assert to_futures_product(s) == "PI_XBTUSD"
    assert to_futures_product(s, kind="PF") == "PF_XBTUSD"
