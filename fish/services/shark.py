"""Shark Family — Earnings Event Avatars.

Don't encode PEAD = true. Create competing hypotheses:
- Shark-SUE: earnings surprise
- Shark-Gap: announcement return
- Shark-Revision: analyst revisions
- Shark-Volume: earnings × abnormal volume
- Shark-Retail: earnings × retail pressure
- Shark-Liquidity: earnings × liquidity
- Shark-Expectation: surprise relative to expected-return state

Each shark is a falsifiable avatar, not gospel.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fish.services.baselines import StrategyResult, _closes, _build_result


def _shark_sue(prices: list[dict], lookback: int = 60, threshold: float = 0.05, **kw) -> StrategyResult:
    """Buy on positive earnings surprise (SUE proxy).
    
    Since we don't have actual earnings data, proxy SUE with:
    - Price gap > threshold (proxy for surprise)
    - Volume spike (proxy for information content)
    """
    closes = _closes(prices)
    volumes = [p.get("volume", 1000000) for p in prices]
    
    # Calculate average volume
    avg_vol = sum(volumes) / len(volumes) if volumes else 1000000
    
    trades, position, entry = [], 0, 0
    
    for i in range(1, len(closes)):
        # Daily return (proxy for surprise)
        ret = (closes[i] - closes[i-1]) / closes[i-1]
        
        # Volume spike (proxy for information content)
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
        
        # SUE proxy: large positive return + high volume
        if ret > threshold and vol_ratio > 1.5 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif ret < -threshold and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Shark-SUE", trades, closes)


def _shark_gap(prices: list[dict], gap_threshold: float = 0.03, **kw) -> StrategyResult:
    """Trade on earnings gap (announcement return).
    
    Buy if gap up > threshold, sell on gap down or after N days.
    """
    closes = _closes(prices)
    highs = [p.get("high", p.get("price", 0)) for p in prices]
    lows = [p.get("low", p.get("price", 0)) for p in prices]
    
    trades, position, entry = [], 0, 0
    hold_days = 0
    max_hold = 20
    
    for i in range(1, len(closes)):
        # Gap = overnight return
        gap = (closes[i] - closes[i-1]) / closes[i-1]
        
        if gap > gap_threshold and position == 0:
            position, entry = 1000, closes[i]
            hold_days = 0
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0:
            hold_days += 1
            pnl = (closes[i] - entry) * position
            
            # Sell on: gap down, stop loss, or time exit
            if gap < -gap_threshold or pnl / entry < -0.05 or hold_days >= max_hold:
                trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
                position = 0
    
    return _build_result("Shark-Gap", trades, closes)


def _shark_volume(prices: list[dict], vol_multiplier: float = 2.0, **kw) -> StrategyResult:
    """Trade on abnormal volume events.
    
    High volume + positive return = buy
    High volume + negative return = sell
    """
    closes = _closes(prices)
    volumes = [p.get("volume", 1000000) for p in prices]
    
    # Calculate rolling average volume
    lookback = 20
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        avg_vol = sum(volumes[i-lookback:i]) / lookback
        vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
        
        ret = (closes[i] - closes[i-1]) / closes[i-1]
        
        # Abnormal volume + positive return
        if vol_ratio > vol_multiplier and ret > 0.01 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif vol_ratio > vol_multiplier and ret < -0.01 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Shark-Volume", trades, closes)


def _shark_reversal(prices: list[dict], lookback: int = 5, **kw) -> StrategyResult:
    """Post-earnings reversal: buy oversold after earnings, sell on bounce.
    
    If stock drops >10% in N days (proxy for earnings reaction),
    buy for mean reversion.
    """
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        # N-day return (proxy for earnings reaction)
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        
        # Oversold: large drop
        if ret < -0.10 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0:
            pnl = (closes[i] - entry) * position
            # Sell on bounce or stop loss
            if pnl / entry > 0.05 or pnl / entry < -0.08:
                trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
                position = 0
    
    return _build_result("Shark-Reversal", trades, closes)


def _shark_breakout(prices: list[dict], lookback: int = 20, **kw) -> StrategyResult:
    """Buy on breakout above N-day high (post-earnings momentum).
    
    If stock breaks above 20-day high after period of consolidation,
    ride the momentum.
    """
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(closes)):
        high = max(closes[i-lookback:i])
        
        # Breakout
        if closes[i] > high and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif position > 0:
            pnl = (closes[i] - entry) * position
            # Sell on breakdown or trailing stop
            if closes[i] < entry * 0.95 or closes[i] < entry * 1.1 and (closes[i] - entry) / entry < 0.02:
                trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
                position = 0
    
    return _build_result("Shark-Breakout", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

SHARK_STRATEGIES = {
    "shark_sue": _shark_sue,
    "shark_gap": _shark_gap,
    "shark_volume": _shark_volume,
    "shark_reversal": _shark_reversal,
    "shark_breakout": _shark_breakout,
}

SHARK_META = {
    "shark_sue": {"animal": "Shark", "class": "earnings", "description": "Earnings surprise (SUE proxy)"},
    "shark_gap": {"animal": "Shark", "class": "earnings", "description": "Announcement gap trade"},
    "shark_volume": {"animal": "Shark", "class": "earnings", "description": "Abnormal volume events"},
    "shark_reversal": {"animal": "Shark", "class": "earnings", "description": "Post-earnings reversal"},
    "shark_breakout": {"animal": "Shark", "class": "earnings", "description": "Post-earnings momentum breakout"},
}
