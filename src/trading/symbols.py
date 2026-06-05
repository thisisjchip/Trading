"""Explicit symbol translation.

Kraken uses several incompatible symbol spellings and we must never let one
leak into another layer:

* Spot REST pair       e.g. ``XBTUSD`` / ``XXBTZUSD`` (the canonical altname)
* Spot WebSocket pair  e.g. ``XBT/USD``
* Futures/perp product e.g. ``PI_XBTUSD`` (perpetual inverse) or ``PF_XBTUSD``

Internally the whole system speaks ONE canonical symbol: ``BASE/QUOTE`` with
Kraken's asset spellings, e.g. ``XBT/USD``, ``ETH/USD``, ``SOL/USD``. Each
adapter converts to/from its own wire format at its boundary, here, so strategy
and backtest code only ever see the canonical form.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    """A canonical instrument: base + quote in Kraken asset spelling."""

    base: str
    quote: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", self.base.upper())
        object.__setattr__(self, "quote", self.quote.upper())

    @property
    def canonical(self) -> str:
        return f"{self.base}/{self.quote}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.canonical


# Common aliases people type, mapped to Kraken's spelling. Kraken calls
# Bitcoin "XBT". We accept BTC for ergonomics and normalise to XBT.
_ASSET_ALIASES = {
    "BTC": "XBT",
    "XXBT": "XBT",
    "XBT": "XBT",
    "XETH": "ETH",
    "XDG": "XDG",  # Dogecoin (Kraken)
    "DOGE": "XDG",
    "ZUSD": "USD",
    "ZEUR": "EUR",
}


def _normalise_asset(asset: str) -> str:
    a = asset.upper()
    return _ASSET_ALIASES.get(a, a)


def parse_symbol(text: str) -> Symbol:
    """Parse a user/canonical string into a :class:`Symbol`.

    Accepts ``XBT/USD``, ``BTC/USD``, ``XBTUSD`` (assumes 3-char quote),
    ``PI_XBTUSD`` and ``PF_XBTUSD`` perp product ids.
    """
    t = text.strip().upper()

    # Futures product id: PI_XBTUSD / PF_XBTUSD / FI_XBTUSD_<date> ...
    if "_" in t:
        parts = t.split("_")
        # parts[0] is the product-type prefix (PI/PF/FI/...); parts[1] is pair
        pair = parts[1] if len(parts) > 1 else parts[0]
        return _split_concatenated(pair)

    if "/" in t:
        base, quote = t.split("/", 1)
        return Symbol(_normalise_asset(base), _normalise_asset(quote))

    return _split_concatenated(t)


def _split_concatenated(pair: str) -> Symbol:
    """Split a glued pair like ``XBTUSD`` assuming a 3-char fiat-ish quote.

    Handles the common quotes (USD/EUR/GBP/USDT/USDC). Falls back to a 3-char
    quote split.
    """
    p = pair.upper()
    for q in ("USDT", "USDC"):  # 4-char quotes first
        if p.endswith(q):
            return Symbol(_normalise_asset(p[: -len(q)]), q)
    for q in ("USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"):
        if p.endswith(q):
            return Symbol(_normalise_asset(p[: -len(q)]), q)
    # Last resort: assume 3-char quote.
    return Symbol(_normalise_asset(p[:-3]), p[-3:])


# --- Wire-format encoders --------------------------------------------------

def to_spot_rest(sym: Symbol) -> str:
    """Spot REST pair, e.g. ``XBTUSD``. Kraken's REST accepts this altname."""
    return f"{sym.base}{sym.quote}"


def to_spot_ws(sym: Symbol) -> str:
    """Spot WebSocket pair, e.g. ``XBT/USD``."""
    return f"{sym.base}/{sym.quote}"


def to_futures_product(sym: Symbol, kind: str = "PI") -> str:
    """Futures/perp product id.

    ``kind`` is the product-type prefix: ``PI`` = perpetual inverse (the classic
    PI_XBTUSD multi-collateral perp), ``PF`` = perpetual linear (USD-margined).
    Defaults to ``PI`` to match the ``PI_XBTUSD`` examples in Kraken's docs.
    """
    return f"{kind}_{sym.base}{sym.quote}"
