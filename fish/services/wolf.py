"""Wolf — Regime Avatar.

Competing regime models:
- Hidden Markov Model (simplified)
- Change-point detection
- Volatility regimes
- Trend/dispersion regimes
- MA regime

Don't define: market = BULL
Represent: P(regime=k|X_t)
Strategy weights depend on the distribution.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fish.services.baselines import StrategyResult, _closes, _build_result


def _ma_regime(prices: list[dict], fast: int = 20, slow: int = 100, **kw) -> StrategyResult:
    """Simple regime: above MA = long, below = flat."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    
    for i in range(slow, len(closes)):
        ma_fast = sum(closes[i-fast:i]) / fast
        ma_slow = sum(closes[i-slow:i]) / slow
        
        # Regime: bull if fast > slow, bear otherwise
        regime = "bull" if ma_fast > ma_slow else "bear"
        
        if regime == "bull" and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif regime == "bear" and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Wolf-MARegime", trades, closes)


def _vol_regime(prices: list[dict], lookback: int = 60, low_vol: float = 0.15, high_vol: float = 0.30, **kw) -> StrategyResult:
    """Volatility regimes: low vol = long, high vol = flat."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
        
        regime = "low" if vol < low_vol else ("high" if vol > high_vol else "mid")
        
        if regime == "low" and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif regime == "high" and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Wolf-VolRegime", trades, closes)


def _trend_dispersion(prices: list[dict], lookback: int = 20, **kw) -> StrategyResult:
    """Trend + dispersion regime: strong trend + low dispersion = long."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        
        # Trend strength (Sharpe of window)
        std = math.sqrt(sum((r - mean)**2 for r in window) / len(window))
        sharpe = mean / std * math.sqrt(252) if std > 0 else 0
        
        # Dispersion (coefficient of variation)
        vol = std * math.sqrt(252)
        
        # Regime: trending + low vol = good
        if abs(sharpe) > 1 and vol < 0.25:
            regime = "trending_low_vol"
        elif abs(sharpe) > 1 and vol >= 0.25:
            regime = "trending_high_vol"
        elif abs(sharpe) <= 1 and vol < 0.25:
            regime = "choppy_low_vol"
        else:
            regime = "choppy_high_vol"
        
        # Trade in trending regimes
        if regime == "trending_low_vol" and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif regime in ("trending_high_vol", "choppy_high_vol") and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Wolf-TrendDisp", trades, closes)


def _change_point(prices: list[dict], threshold: float = 2.0, **kw) -> StrategyResult:
    """Detect regime changes using rolling z-score of returns."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    lookback = 20
    
    for i in range(lookback, len(returns)):
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        std = math.sqrt(sum((r - mean)**2 for r in window) / len(window))
        
        # Z-score of current return
        z = (returns[i] - mean) / std if std > 0 else 0
        
        # Regime change: large positive z = buy, large negative z = sell
        if z > threshold and position == 0:
            position, entry = 1000, closes[i+1]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i+1], "qty": 1000, "day": i})
        elif z < -threshold and position > 0:
            pnl = (closes[i+1] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i+1], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Wolf-ChangePoint", trades, closes)


def _multi_regime(prices: list[dict], lookback: int = 20, **kw) -> StrategyResult:
    """Combine MA + vol + momentum regime signals."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(max(lookback, 50), len(closes)):
        # MA regime
        ma20 = sum(closes[i-20:i]) / 20
        ma50 = sum(closes[i-50:i]) / 50
        ma_regime = "bull" if ma20 > ma50 else "bear"
        
        # Vol regime
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
        vol_regime = "low" if vol < 0.20 else "high"
        
        # Momentum regime
        mom = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        mom_regime = "up" if mom > 0 else "down"
        
        # Combined regime
        score = 0
        if ma_regime == "bull": score += 1
        if vol_regime == "low": score += 1
        if mom_regime == "up": score += 1
        
        if score >= 2 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif score <= 1 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Wolf-MultiRegime", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

WOLF_STRATEGIES = {
    "wolf_ma_regime": _ma_regime,
    "wolf_vol_regime": _vol_regime,
    "wolf_trend_disp": _trend_dispersion,
    "wolf_change_point": _change_point,
    "wolf_multi_regime": _multi_regime,
}

WOLF_META = {
    "wolf_ma_regime": {"animal": "Wolf", "class": "regime", "description": "MA crossover regime"},
    "wolf_vol_regime": {"animal": "Wolf", "class": "regime", "description": "Volatility regime"},
    "wolf_trend_disp": {"animal": "Wolf", "class": "regime", "description": "Trend + dispersion regime"},
    "wolf_change_point": {"animal": "Wolf", "class": "regime", "description": "Change-point detection"},
    "wolf_multi_regime": {"animal": "Wolf", "class": "regime", "description": "Multi-signal regime"},
}
