"""Fox — Residual/Sector-Neutral Avatar.

Trades properties of ε_t (residuals after removing market/sector exposure)
rather than raw price.

This separates:
> "semiconductor stocks went up"
from:
> "COHR did something unusual"

Candidate models:
- Market-neutral residual momentum
- Sector-neutral momentum
- Residual reversal
- Pairs/cointegration
- PCA residuals
- Factor residuals
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fish.services.baselines import StrategyResult, _closes, _build_result


def _market_neutral_residual(prices: list[dict], benchmark: list[dict] = None, lookback: int = 60, **kw) -> StrategyResult:
    """Trade residual after removing market exposure.
    
    r_COHR = alpha + beta * r_SPY + epsilon
    Trade epsilon, not r_COHR.
    """
    closes = _closes(prices)
    
    # If no benchmark provided, use equal-weight market proxy
    if benchmark is None:
        # Use 20-day MA as market proxy
        benchmark_closes = closes
    else:
        benchmark_closes = _closes(benchmark)
    
    # Align lengths
    min_len = min(len(closes), len(benchmark_closes))
    closes = closes[-min_len:]
    benchmark_closes = benchmark_closes[-min_len:]
    
    # Calculate returns
    stock_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, min_len)]
    bench_returns = [(benchmark_closes[i] - benchmark_closes[i-1]) / benchmark_closes[i-1] for i in range(1, min_len)]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(stock_returns)):
        # Calculate beta over lookback
        sw = stock_returns[i-lookback:i]
        bw = bench_returns[i-lookback:i]
        
        mean_s = sum(sw) / len(sw)
        mean_b = sum(bw) / len(bw)
        
        cov = sum((sw[j] - mean_s) * (bw[j] - mean_b) for j in range(len(sw))) / len(sw)
        var_b = sum((b - mean_b)**2 for b in bw) / len(bw)
        
        beta = cov / var_b if var_b > 0 else 0
        
        # Residual = stock_return - beta * benchmark_return
        residual = stock_returns[i] - beta * bench_returns[i]
        
        # Accumulate residual over lookback
        residual_window = []
        for j in range(i - lookback, i):
            r = stock_returns[j] - beta * bench_returns[j]
            residual_window.append(r)
        
        avg_residual = sum(residual_window) / len(residual_window) if residual_window else 0
        
        # Trade based on residual momentum
        if avg_residual > 0.001 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif avg_residual < -0.001 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Fox-ResidualMomentum", trades, closes)


def _pairs_strategy(prices: list[dict], pair_prices: list[dict], lookback: int = 60, **kw) -> StrategyResult:
    """Trade the spread between two cointegrated stocks."""
    closes1 = _closes(prices)
    closes2 = _closes(pair_prices)
    
    min_len = min(len(closes1), len(closes2))
    closes1 = closes1[-min_len:]
    closes2 = closes2[-min_len:]
    
    # Calculate hedge ratio (beta)
    returns1 = [(closes1[i] - closes1[i-1]) / closes1[i-1] for i in range(1, min_len)]
    returns2 = [(closes2[i] - closes2[i-1]) / closes2[i-1] for i in range(1, min_len)]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, min_len - 1):
        # Rolling hedge ratio
        r1 = returns1[i-lookback:i]
        r2 = returns2[i-lookback:i]
        
        mean1 = sum(r1) / len(r1)
        mean2 = sum(r2) / len(r2)
        
        cov = sum((r1[j] - mean1) * (r2[j] - mean2) for j in range(len(r1))) / len(r1)
        var2 = sum((r - mean2)**2 for r in r2) / len(r2)
        
        hedge_ratio = cov / var2 if var2 > 0 else 1
        
        # Spread = r1 - hedge_ratio * r2
        spread = returns1[i] - hedge_ratio * returns2[i]
        
        # Mean reversion on spread
        spread_window = [returns1[j] - hedge_ratio * returns2[j] for j in range(i-lookback, i)]
        mean_spread = sum(spread_window) / len(spread_window)
        std_spread = math.sqrt(sum((s - mean_spread)**2 for s in spread_window) / len(spread_window))
        
        z_score = (spread - mean_spread) / std_spread if std_spread > 0 else 0
        
        # Trade mean reversion
        if z_score < -2 and position == 0:
            position, entry = 1000, closes1[i]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes1[i], "qty": 1000, "day": i})
        elif z_score > 0 and position > 0:
            pnl = (closes1[i] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes1[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Fox-Pairs", trades, closes1)


def _sector_neutral_momentum(prices: list[dict], sector_prices: list[dict] = None, lookback: int = 20, **kw) -> StrategyResult:
    """Buy stocks outperforming their sector, sell underperformers."""
    closes = _closes(prices)
    
    if sector_prices is None:
        # Use stock's own MA as sector proxy
        sector_closes = closes
    else:
        sector_closes = _closes(sector_prices)
    
    min_len = min(len(closes), len(sector_closes))
    closes = closes[-min_len:]
    sector_closes = sector_closes[-min_len:]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, min_len):
        # Stock momentum
        stock_ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        # Sector momentum
        sector_ret = (sector_closes[i] - sector_closes[i-lookback]) / sector_closes[i-lookback]
        
        # Relative strength
        relative = stock_ret - sector_ret
        
        if relative > 0.02 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif relative < -0.02 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Fox-SectorNeutral", trades, closes)


def _residual_reversal(prices: list[dict], benchmark: list[dict] = None, lookback: int = 20, **kw) -> StrategyResult:
    """Buy when residual is oversold, sell on mean reversion."""
    closes = _closes(prices)
    
    if benchmark is None:
        benchmark_closes = closes
    else:
        benchmark_closes = _closes(benchmark)
    
    min_len = min(len(closes), len(benchmark_closes))
    closes = closes[-min_len:]
    benchmark_closes = benchmark_closes[-min_len:]
    
    stock_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, min_len)]
    bench_returns = [(benchmark_closes[i] - benchmark_closes[i-1]) / benchmark_closes[i-1] for i in range(1, min_len)]
    
    trades, position, entry = [], 0, 0
    
    for i in range(lookback, len(stock_returns)):
        # Calculate residuals
        residuals = []
        for j in range(i-lookback, i):
            # Simple beta estimation
            cov = sum((stock_returns[j-k] - sum(stock_returns[j-lookback:j])/lookback) * 
                     (bench_returns[j-k] - sum(bench_returns[j-lookback:j])/lookback) 
                     for k in range(lookback)) / lookback
            var_b = sum((bench_returns[j-k] - sum(bench_returns[j-lookback:j])/lookback)**2 
                       for k in range(lookback)) / lookback
            beta = cov / var_b if var_b > 0 else 0
            residuals.append(stock_returns[j] - beta * bench_returns[j])
        
        mean_res = sum(residuals) / len(residuals)
        std_res = math.sqrt(sum((r - mean_res)**2 for r in residuals) / len(residuals))
        
        current_residual = stock_returns[i] - 0.5 * bench_returns[i]  # Simplified beta
        z_score = (current_residual - mean_res) / std_res if std_res > 0 else 0
        
        if z_score < -2 and position == 0:
            position, entry = 1000, closes[i+1]
            trades.append({"date": prices[i+1]["date"], "action": "BUY", "price": closes[i+1], "qty": 1000, "day": i})
        elif z_score > 0 and position > 0:
            pnl = (closes[i+1] - entry) * position
            trades.append({"date": prices[i+1]["date"], "action": "SELL", "price": closes[i+1], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    
    return _build_result("Fox-ResidualReversal", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

FOX_STRATEGIES = {
    "fox_residual_momentum": _market_neutral_residual,
    "fox_sector_neutral": _sector_neutral_momentum,
    "fox_residual_reversal": _residual_reversal,
    # "fox_pairs": _pairs_strategy,  # Needs pair_prices argument
}

FOX_META = {
    "fox_residual_momentum": {"animal": "Fox", "class": "residual", "description": "Trade residual after removing market exposure"},
    "fox_sector_neutral": {"animal": "Fox", "class": "residual", "description": "Buy outperformers vs sector"},
    "fox_residual_reversal": {"animal": "Fox", "class": "residual", "description": "Mean reversion on residuals"},
}
