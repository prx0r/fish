"""Proper trading strategies based on financial ML research.

Sources:
- López de Prado: Advances in Financial Machine Learning
- Ernie Chan: Quantitative Trading, Algorithmic Trading
- BEAR: Confluence scoring, regime detection
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


@dataclass
class StrategyResult:
    """Result of running a strategy."""
    name: str
    trades: list[dict]
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    trades_count: int


def calculate_returns(prices: list[dict]) -> list[float]:
    """Calculate returns from price series."""
    return [(prices[i]["price"] - prices[i-1]["price"]) / prices[i-1]["price"]
            for i in range(1, len(prices))]


def calculate_sharpe(returns: list[float], periods_per_year: int = 12) -> float:
    """Calculate annualized Sharpe ratio."""
    if not returns:
        return 0
    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret)**2 for r in returns) / len(returns))
    return (mean_ret / std_ret) * math.sqrt(periods_per_year) if std_ret > 0 else 0


def calculate_max_drawdown(prices: list[dict]) -> float:
    """Calculate maximum drawdown."""
    peak = prices[0]["price"]
    max_dd = 0
    for p in prices:
        peak = max(peak, p["price"])
        dd = (p["price"] - peak) / peak
        max_dd = min(max_dd, dd)
    return max_dd


# ── Strategy 1: Buy and Hold (Turtle) ───────────────────────────────────────

def strategy_buyhold(prices: list[dict]) -> StrategyResult:
    """Buy at start, hold forever. The benchmark."""
    trades = [{"date": prices[0]["date"], "action": "BUY", "price": prices[0]["price"], "qty": 1000}]
    total_return = (prices[-1]["price"] - prices[0]["price"]) / prices[0]["price"]
    returns = calculate_returns(prices)
    return StrategyResult(
        name="Turtle (Buy & Hold)", trades=trades,
        total_return=total_return, sharpe=calculate_sharpe(returns),
        max_drawdown=calculate_max_drawdown(prices),
        win_rate=100 if total_return > 0 else 0, trades_count=1,
    )


# ── Strategy 2: Mean Reversion (Bear) ──────────────────────────────────────

def strategy_mean_reversion(prices: list[dict]) -> StrategyResult:
    """Buy when price drops 2 std below mean, sell on reversion. (Ernie Chan)"""
    closes = [p["price"] for p in prices]
    trades = []
    position = 0
    entry_price = 0
    
    for i in range(20, len(prices)):
        window = closes[i-20:i]
        mean = sum(window) / len(window)
        std = math.sqrt(sum((x - mean)**2 for x in window) / len(window))
        
        if closes[i] < mean - 2 * std and position == 0:
            position = 1000
            entry_price = closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": position})
        elif closes[i] > mean and position > 0:
            pnl = (closes[i] - entry_price) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": position, "pnl": pnl})
            position = 0
    
    # Calculate actual trading return from trades
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    total_return = total_pnl / (closes[0] * 1000) if closes[0] > 0 else 0  # Normalize by initial investment
    returns = calculate_returns(prices)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    
    return StrategyResult(
        name="Bear (Mean Reversion)", trades=trades,
        total_return=total_return, sharpe=calculate_sharpe(returns),
        max_drawdown=calculate_max_drawdown(prices),
        win_rate=wins / len(trades) * 100 if trades else 0, trades_count=len(trades),
    )


# ── Strategy 3: Momentum (Bull) ────────────────────────────────────────────

def strategy_momentum(prices: list[dict]) -> StrategyResult:
    """Buy when 20-day MA crosses above 50-day MA. (Trend following)"""
    closes = [p["price"] for p in prices]
    trades = []
    position = 0
    entry_price = 0
    
    for i in range(50, len(prices)):
        ma20 = sum(closes[i-20:i]) / 20
        ma50 = sum(closes[i-50:i]) / 50
        prev_ma20 = sum(closes[i-21:i-1]) / 20
        prev_ma50 = sum(closes[i-51:i-1]) / 50
        
        if prev_ma20 <= prev_ma50 and ma20 > ma50 and position == 0:
            position = 1000
            entry_price = closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": position})
        elif prev_ma20 >= prev_ma50 and ma20 < ma50 and position > 0:
            pnl = (closes[i] - entry_price) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": position, "pnl": pnl})
            position = 0
    
    # Calculate actual trading return from trades
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    total_return = total_pnl / (closes[0] * 1000) if closes[0] > 0 else 0
    returns = calculate_returns(prices)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    
    return StrategyResult(
        name="Bull (Momentum)", trades=trades,
        total_return=total_return, sharpe=calculate_sharpe(returns),
        max_drawdown=calculate_max_drawdown(prices),
        win_rate=wins / len(trades) * 100 if trades else 0, trades_count=len(trades),
    )


# ── Strategy 4: RSI Overbought/Oversold ─────────────────────────────────────

def strategy_rsi(prices: list[dict]) -> StrategyResult:
    """Buy when RSI < 30, sell when RSI > 70."""
    closes = [p["price"] for p in prices]
    trades = []
    position = 0
    entry_price = 0
    
    for i in range(14, len(prices)):
        gains = []
        losses = []
        for j in range(i-13, i):
            change = closes[j+1] - closes[j]
            if change > 0:
                gains.append(change)
            else:
                losses.append(abs(change))
        
        avg_gain = sum(gains) / 14 if gains else 0
        avg_loss = sum(losses) / 14 if losses else 0
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        if rsi < 30 and position == 0:
            position = 1000
            entry_price = closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": position})
        elif rsi > 70 and position > 0:
            pnl = (closes[i] - entry_price) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": position, "pnl": pnl})
            position = 0
    
    final = closes[-1]
    total_return = (final - closes[0]) / closes[0]
    returns = calculate_returns(prices)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    
    return StrategyResult(
        name="RSI Overbought/Oversold", trades=trades,
        total_return=total_return, sharpe=calculate_sharpe(returns),
        max_drawdown=calculate_max_drawdown(prices),
        win_rate=wins / len(trades) * 100 if trades else 0, trades_count=len(trades),
    )


# ── Strategy 5: Confluence (Wolf) ──────────────────────────────────────────

def strategy_confluence(prices: list[dict]) -> StrategyResult:
    """Multiple signals align: RSI oversold + price below MA20 + volume spike."""
    closes = [p["price"] for p in prices]
    trades = []
    position = 0
    entry_price = 0
    
    for i in range(50, len(prices)):
        # RSI
        gains = []
        losses = []
        for j in range(max(0, i-13), i):
            change = closes[j+1] - closes[j]
            if change > 0:
                gains.append(change)
            else:
                losses.append(abs(change))
        avg_gain = sum(gains) / 14 if gains else 0
        avg_loss = sum(losses) / 14 if losses else 0
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # MA
        ma20 = sum(closes[i-20:i]) / 20
        
        # Confluence: RSI < 35 AND price < MA20
        if rsi < 35 and closes[i] < ma20 * 0.98 and position == 0:
            position = 1000
            entry_price = closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": position})
        elif rsi > 65 and closes[i] > ma20 and position > 0:
            pnl = (closes[i] - entry_price) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": position, "pnl": pnl})
            position = 0
    
    final = closes[-1]
    total_return = (final - closes[0]) / closes[0]
    returns = calculate_returns(prices)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    
    return StrategyResult(
        name="Wolf (Confluence)", trades=trades,
        total_return=total_return, sharpe=calculate_sharpe(returns),
        max_drawdown=calculate_max_drawdown(prices),
        win_rate=wins / len(trades) * 100 if trades else 0, trades_count=len(trades),
    )


# ── Strategy Registry ───────────────────────────────────────────────────────

STRATEGIES = {
    "buyhold": strategy_buyhold,
    "mean_reversion": strategy_mean_reversion,
    "momentum": strategy_momentum,
    "rsi": strategy_rsi,
    "confluence": strategy_confluence,
}

STRATEGY_INFO = {
    "buyhold": {"name": "Turtle", "avatar": "🐢", "based_on": "Buffett's favorite holding period", "best_for": "Core compounders"},
    "mean_reversion": {"name": "Bear", "avatar": "🐻", "based_on": "Ernie Chan's pairs trading", "best_for": "Range-bound markets"},
    "momentum": {"name": "Bull", "avatar": "🐂", "based_on": "Classic trend following", "best_for": "Trending markets"},
    "rsi": {"name": "RSI", "avatar": "📊", "based_on": "Technical analysis", "best_for": "Oversold/overbought"},
    "confluence": {"name": "Wolf", "avatar": "🐺", "based_on": "BEAR confluence scoring", "best_for": "High-conviction setups"},
}
