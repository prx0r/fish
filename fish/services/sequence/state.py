"""WorldState — Complete world state at time t.

This is the foundation of the MPC architecture.
Everything the system knows about a stock at a point in time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class WorldState:
    """Complete world state at time t."""
    ticker: str
    date: str
    
    # Price state
    price: float
    returns_1d: float = 0.0
    returns_5d: float = 0.0
    returns_20d: float = 0.0
    returns_60d: float = 0.0
    
    # Volatility state
    vol_20d: float = 0.0
    vol_60d: float = 0.0
    vol_regime: str = "mid"  # "low", "mid", "high"
    
    # Momentum state
    momentum_20d: float = 0.0
    momentum_60d: float = 0.0
    momentum_120d: float = 0.0
    
    # Regime state
    ma_regime: str = "neutral"  # "bull", "bear", "neutral"
    trend_strength: float = 0.0
    
    # Liquidity state
    adv: float = 0.0
    spread_bps: float = 0.0
    liquidity_tier: str = "B"
    
    # Avatar signals
    avatar_signals: dict = field(default_factory=dict)
    
    # External state
    spy_return: float = 0.0
    sector_return: float = 0.0
    vix: float = 20.0
    rates: float = 0.05


def compute_world_state(
    prices: list[dict],
    ticker: str,
    index: int,
    spy_prices: list[dict] = None,
    sector_prices: list[dict] = None,
) -> WorldState:
    """Compute world state from price data at given index."""
    if index < 0 or index >= len(prices):
        return WorldState(ticker=ticker, date="", price=0)
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    volumes = [p.get("volume", 1000000) for p in prices]
    dates = [p.get("date", "") for p in prices]
    
    price = closes[index]
    date = dates[index] if index < len(dates) else ""
    
    # Returns
    returns_1d = (closes[index] - closes[index-1]) / closes[index-1] if index > 0 else 0
    returns_5d = (closes[index] - closes[max(0, index-5)]) / closes[max(0, index-5)] if index >= 5 else 0
    returns_20d = (closes[index] - closes[max(0, index-20)]) / closes[max(0, index-20)] if index >= 20 else 0
    returns_60d = (closes[index] - closes[max(0, index-60)]) / closes[max(0, index-60)] if index >= 60 else 0
    
    # Volatility (20-day)
    if index >= 20:
        window = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(index-19, index+1)]
        mean = sum(window) / len(window)
        vol_20d = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
    else:
        vol_20d = 0
    
    # Volatility (60-day)
    if index >= 60:
        window = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(index-59, index+1)]
        mean = sum(window) / len(window)
        vol_60d = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
    else:
        vol_60d = vol_20d
    
    # Vol regime
    if vol_20d < 0.15:
        vol_regime = "low"
    elif vol_20d > 0.30:
        vol_regime = "high"
    else:
        vol_regime = "mid"
    
    # Momentum
    momentum_20d = returns_20d
    momentum_60d = returns_60d
    momentum_120d = (closes[index] - closes[max(0, index-120)]) / closes[max(0, index-120)] if index >= 120 else 0
    
    # MA regime
    if index >= 100:
        ma20 = sum(closes[index-19:index+1]) / 20
        ma100 = sum(closes[index-99:index+1]) / 100
        ma_regime = "bull" if ma20 > ma100 else "bear"
        trend_strength = (ma20 - ma100) / ma100
    else:
        ma_regime = "neutral"
        trend_strength = 0
    
    # Liquidity
    if index >= 20:
        adv = sum(volumes[index-19:index+1]) / 20
    else:
        adv = sum(volumes[:index+1]) / max(1, index+1)
    
    # Spread estimate (simplified)
    spread_bps = 5 + vol_20d * 100  # Base + vol adjustment
    
    # Liquidity tier
    if adv > 10000000:
        liquidity_tier = "A"
    elif adv > 1000000:
        liquidity_tier = "B"
    elif adv > 100000:
        liquidity_tier = "C"
    else:
        liquidity_tier = "D"
    
    # External state
    spy_return = 0
    if spy_prices and index < len(spy_prices):
        spy_closes = [p.get("close", p.get("price", 0)) for p in spy_prices]
        if index > 0 and index < len(spy_closes):
            spy_return = (spy_closes[index] - spy_closes[index-1]) / spy_closes[index-1]
    
    sector_return = 0
    if sector_prices and index < len(sector_prices):
        sector_closes = [p.get("close", p.get("price", 0)) for p in sector_prices]
        if index > 0 and index < len(sector_closes):
            sector_return = (sector_closes[index] - sector_closes[index-1]) / sector_closes[index-1]
    
    return WorldState(
        ticker=ticker,
        date=date,
        price=price,
        returns_1d=returns_1d,
        returns_5d=returns_5d,
        returns_20d=returns_20d,
        returns_60d=returns_60d,
        vol_20d=vol_20d,
        vol_60d=vol_60d,
        vol_regime=vol_regime,
        momentum_20d=momentum_20d,
        momentum_60d=momentum_60d,
        momentum_120d=momentum_120d,
        ma_regime=ma_regime,
        trend_strength=trend_strength,
        adv=adv,
        spread_bps=spread_bps,
        liquidity_tier=liquidity_tier,
        spy_return=spy_return,
        sector_return=sector_return,
    )


def state_to_features(state: WorldState) -> list[float]:
    """Convert world state to feature vector for ML."""
    return [
        state.returns_1d,
        state.returns_5d,
        state.returns_20d,
        state.returns_60d,
        state.vol_20d,
        state.vol_60d,
        state.momentum_20d,
        state.momentum_60d,
        state.momentum_120d,
        state.trend_strength,
        state.adv / 1000000,  # Normalize
        state.spread_bps / 100,  # Normalize
        state.spy_return,
        state.sector_return,
    ]
