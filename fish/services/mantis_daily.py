"""Mantis Daily — Translate microstructure learnings into daily-price strategies.

Trained on LSE GSK 2007 (274K order lifecycles):
- Cancel rate: 71.3% → most "moves" are fake, require volume confirmation
- Execution rate: 10.6% → most aggressive orders don't fill, fade panic
- Wall persistence: 0.07% → large volume nodes are unreliable support/resistance
- Large order cancel rate: 71.6% → big walls vanish, don't trust them

These patterns transfer to daily data via:
1. Volume-weighted signals (cancel rate → noise filter)
2. Fade-the-panic entries (execution rate → contrarian at extremes)
3. Volume-node avoidance (wall persistence → don't trade at volume clusters)
"""
from __future__ import annotations

from fish.services.baselines import StrategyResult, _closes, _build_result


def _mantis_noise_filter(prices: list[dict], lookback: int = 20, volume_threshold: float = 1.5, **kw) -> StrategyResult:
    """Cancel rate insight: 71% of orders vanish → most price moves are noise.

    Only trade when volume confirms the move (volume > 1.5x average).
    This filters out the 71% of moves that are just cancelled orders.
    """
    closes = _closes(prices)
    volumes = [p.get('volume', 1_000_000) for p in prices]
    avg_vol = sum(volumes[:lookback]) / lookback if lookback <= len(volumes) else sum(volumes) / len(volumes)

    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        # Volume confirmation: only trade if volume > threshold
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
        ret = (closes[i] - closes[i-1]) / closes[i-1]

        if vol_ratio > volume_threshold and ret > 0.01 and position == 0:
            # High volume + positive return → real buying, not cancellation noise
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif (vol_ratio > volume_threshold or ret < -0.02) and position > 0:
            # Volume spike or stop loss → exit
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0

        # Update rolling average
        avg_vol = (avg_vol * (lookback - 1) + volumes[i]) / lookback

    return _build_result("Mantis-NoiseFilter", trades, closes)


def _mantis_fade_panic(prices: list[dict], lookback: int = 20, panic_threshold: float = -0.03, **kw) -> StrategyResult:
    """Execution rate insight: only 10.6% of aggressive orders fill.

    When price drops >3% on a single day, most sellers won't get filled
    at the panic price. The price usually reverts. Buy the panic.
    """
    closes = _closes(prices)
    trades, position, entry = [], 0, 0

    for i in range(1, len(closes)):
        ret = (closes[i] - closes[i-1]) / closes[i-1]

        if ret < panic_threshold and position == 0:
            # Panic drop → most sellers won't fill → price reverts
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0 and (closes[i] > entry * 1.05 or i - trades[-1].get("day", 0) > 10):
            # Take profit at +5% or exit after 10 days
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0

    return _build_result("Mantis-FadePanic", trades, closes)


def _mantis_volume_climax(prices: list[dict], lookback: int = 20, **kw) -> StrategyResult:
    """Wall persistence insight: 0.07% of large orders stay live.

    When volume spikes to 3x average, it's likely a wall being hit and
    cancelled. Trade against the volume climax — the wall won't hold.
    """
    closes = _closes(prices)
    volumes = [p.get('volume', 1_000_000) for p in prices]
    avg_vol = sum(volumes[:lookback]) / lookback if lookback <= len(volumes) else sum(volumes) / len(volumes)

    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
        ret = (closes[i] - closes[i-1]) / closes[i-1]

        if vol_ratio > 3.0 and ret > 0.02 and position == 0:
            # Volume climax up → wall was hit and cancelled → fade it
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif vol_ratio > 3.0 and ret < -0.02 and position == 0:
            # Volume climax down → panic selling into cancelled walls → buy
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0 and (closes[i] > entry * 1.08 or closes[i] < entry * 0.95):
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0

        avg_vol = (avg_vol * (lookback - 1) + volumes[i]) / lookback

    return _build_result("Mantis-VolumeClimax", trades, closes)


# Registry
MANTIS_DAILY_STRATEGIES = {
    "mantis_noise_filter": _mantis_noise_filter,
    "mantis_fade_panic": _mantis_fade_panic,
    "mantis_volume_climax": _mantis_volume_climax,
}

MANTIS_DAILY_META = {
    "mantis_noise_filter": {"animal": "Mantis", "class": "microstructure", "description": "71% cancel rate → volume confirms moves"},
    "mantis_fade_panic": {"animal": "Mantis", "class": "microstructure", "description": "10.6% exec rate → fade panic selling"},
    "mantis_volume_climax": {"animal": "Mantis", "class": "microstructure", "description": "0.07% wall persistence → trade against volume spikes"},
}
