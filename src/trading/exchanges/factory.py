"""Adapter factory — the single place that wires config -> concrete adapter.

This is where the "swap the execution target with a config change" promise is
kept, and where the global LIVE safety gate is enforced consistently.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import Settings, get_settings
from .base import Exchange, ExchangeError
from .kraken_futures import KrakenFutures
from .kraken_spot import KrakenSpot
from .kraken_us_perps import KrakenUSPerps

logger = logging.getLogger(__name__)


def create_exchange(
    name: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Exchange:
    """Build the configured exchange adapter.

    ``name`` overrides ``settings.exchange`` (one of ``kraken_spot``,
    ``kraken_futures``, ``kraken_us_perps``). The LIVE gate from settings is
    threaded into every adapter so paper is always the default.
    """
    settings = settings or get_settings()
    name = (name or settings.exchange).lower()
    live = settings.live

    if name == "kraken_spot":
        adapter: Exchange = KrakenSpot(settings.spot, live=live)
    elif name == "kraken_futures":
        adapter = KrakenFutures(
            settings.futures, demo=settings.futures_demo, live=live
        )
    elif name == "kraken_us_perps":
        adapter = KrakenUSPerps(
            settings.us_perps, base_url=settings.us_perps_base_url, live=live
        )
    else:
        raise ExchangeError(
            f"Unknown exchange {name!r}. Valid: kraken_spot, kraken_futures, "
            f"kraken_us_perps."
        )

    mode = "LIVE" if (live and not adapter.is_paper) else "PAPER"
    logger.info("Created %s adapter in %s mode", adapter.name, mode)
    if live and not adapter.is_paper:
        logger.warning(
            "*** LIVE TRADING ENABLED for %s — real orders may be placed ***",
            adapter.name,
        )
    return adapter
