"""Hedgehog — Volatility Avatar.

Markets contain another prediction problem: E[σ_{t+h}|X_t]

Even if direction is unpredictable, volatility can still be forecastable
and useful for: sizing, stops, options, leverage, strategy gating.

Candidate models:
- Historical vol
- EWMA
- GARCH-like
- Range estimators
- Realized vol
- Vol regime detection
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fish.services.baselines import StrategyResult, _closes, _build_result


def _historical_vol(prices: list[dict], lookback: int = 20, vol_target: float = 0.15, **kw) -> StrategyResult:
    """Position size by inverse volatility."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(returns)):
        # Historical volatility
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
        
        # Simple momentum signal
        mom = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        
        # Scale by inverse vol
        if vol > 0:
            scale = vol_target / vol
        else:
            scale = 1.0
        
        signal = mom * scale
        
        if signal > 0.02 and position == 0:
            position, entry = 1000, closes[i+1]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i+1], "qty": 1000, "day": i})
        elif signal < -0.02 and position > 0:
            pnl = (closes[i+1] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i+1], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Hedgehog-HistVol", trades, closes)


def _ewma_vol(prices: list[dict], span: int = 20, vol_target: float = 0.15, **kw) -> StrategyResult:
    """EWMA volatility for position sizing."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    ewma_var = 0
    alpha = 2 / (span + 1)
    
    for i in range(1, len(returns)):
        # EWMA variance
        ewma_var = alpha * returns[i]**2 + (1 - alpha) * ewma_var
        vol = math.sqrt(ewma_var) * math.sqrt(252)
        
        if i < 20:
            continue
        
        mom = (closes[i] - closes[i-20]) / closes[i-20]
        
        if vol > 0:
            scale = vol_target / vol
        else:
            scale = 1.0
        
        signal = mom * scale
        
        if signal > 0.02 and position == 0:
            position, entry = 1000, closes[i+1]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i+1], "qty": 1000, "day": i})
        elif signal < -0.02 and position > 0:
            pnl = (closes[i+1] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i+1], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Hedgehog-EWMA", trades, closes)


def _vol_breakout(prices: list[dict], lookback: int = 20, vol_threshold: float = 0.02, **kw) -> StrategyResult:
    """Buy on low volatility breakout (squeeze)."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        # Historical volatility
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window))
        
        # Bollinger bandwidth (proxy for squeeze)
        prices_window = closes[i-lookback:i]
        p_mean = sum(prices_window) / len(prices_window)
        p_std = math.sqrt(sum((p - p_mean)**2 for p in prices_window) / len(prices_window))
        bandwidth = 2 * p_std / p_mean if p_mean > 0 else 0
        
        # Low vol + breakout
        if vol < vol_threshold and closes[i] > max(closes[i-lookback:i]) and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0:
            pnl = (closes[i] - entry) * position
            # Exit on: high vol, stop loss, or time
            if vol > vol_threshold * 2 or pnl / entry < -0.05:
                trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
                position = 0
    
    return _build_result("Hedgehog-VolBreakout", trades, closes)


def _low_vol_anomaly(prices: list[dict], lookback: int = 60, **kw) -> StrategyResult:
    """Buy stocks with lowest recent volatility (low-vol anomaly)."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
        
        # Low vol regime
        if vol < 0.15 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif vol > 0.30 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Hedgehog-LowVol", trades, closes)


def _vol_targeting(prices: list[dict], target_vol: float = 0.15, lookback: int = 20, **kw) -> StrategyResult:
    """Scale positions to target volatility."""
    closes = _closes(prices)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(returns)):
        window = returns[i-lookback:i]
        mean = sum(window) / len(window)
        vol = math.sqrt(sum((r - mean)**2 for r in window) / len(window)) * math.sqrt(252)
        
        mom = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        
        if vol > 0:
            leverage = target_vol / vol
        else:
            leverage = 1.0
        
        # Cap leverage
        leverage = min(leverage, 2.0)
        
        signal = mom * leverage
        
        if signal > 0.02 and position == 0:
            position, entry = int(1000 * leverage), closes[i+1]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i+1], "qty": position, "day": i})
        elif signal < -0.02 and position > 0:
            pnl = (closes[i+1] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i+1], "qty": position, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Hedgehog-VolTarget", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

HEDGEHOG_STRATEGIES = {
    "hedgehog_histvol": _historical_vol,
    "hedgehog_ewma": _ewma_vol,
    "hedgehog_volbreakout": _vol_breakout,
    "hedgehog_lowvol": _low_vol_anomaly,
    "hedgehog_voltarget": _vol_targeting,
}

HEDGEHOG_META = {
    "hedgehog_histvol": {"animal": "Hedgehog", "class": "volatility", "description": "Historical vol position sizing"},
    "hedgehog_ewma": {"animal": "Hedgehog", "class": "volatility", "description": "EWMA vol position sizing"},
    "hedgehog_volbreakout": {"animal": "Hedgehog", "class": "volatility", "description": "Low vol squeeze breakout"},
    "hedgehog_lowvol": {"animal": "Hedgehog", "class": "volatility", "description": "Low vol anomaly"},
    "hedgehog_voltarget": {"animal": "Hedgehog", "class": "volatility", "description": "Volatility targeting"},
}
