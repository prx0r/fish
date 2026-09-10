"""Canonical strategy return computation.

Every strategy MUST produce:
1. position[t] — current position (-1, 0, +1)
2. strategy_return[t] = position[t-1] * asset_return[t] - costs[t]
3. strategy_equity[t] — cumulative equity curve

All metrics (Sharpe, Sortino, drawdown, Calmar, etc.) are computed
from strategy_equity, NOT from closes.

This fixes the fundamental bug where Judge was scoring stock returns,
not strategy returns.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class StrategyEquity:
    """Canonical strategy equity curve with positions and returns."""
    name: str
    dates: list[str] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)  # -1, 0, +1
    asset_returns: list[float] = field(default_factory=list)
    strategy_returns: list[float] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    costs: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    
    # Metrics computed from equity curve
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0
    total_return: float = 0.0
    win_rate: float = 0.0
    trades_count: int = 0
    turnover: float = 0.0
    avg_holding_period: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0


def compute_strategy_equity(
    name: str,
    prices: list[dict],
    signal_fn,
    cost_bps: float = 10,
    initial_capital: float = 100000,
) -> StrategyEquity:
    """Compute canonical strategy equity curve.
    
    Args:
        name: Strategy name
        prices: List of price dicts with date, close, volume
        signal_fn: Function(prices, i, position) -> new_position
                   Returns -1 (short), 0 (flat), or +1 (long)
        cost_bps: Transaction cost in basis points
        initial_capital: Starting capital
    
    Returns:
        StrategyEquity with all metrics computed from strategy returns
    """
    equity = StrategyEquity(name=name)
    
    if len(prices) < 2:
        return equity
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    dates = [p.get("date", "") for p in prices]
    
    # Compute asset returns
    asset_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    # Generate signals and compute strategy returns
    position = 0  # Current position
    entry_price = 0
    total_turnover = 0
    n_trades = 0
    holding_days = 0
    holding_periods = []
    
    equity.equity = [initial_capital]
    equity.dates = [dates[0]]
    equity.positions = [0]
    equity.asset_returns = [0]
    equity.strategy_returns = [0]
    equity.costs = [0]
    
    for i in range(1, len(prices)):
        # Get new position from signal function
        new_position = signal_fn(prices, i, position)
        
        # Compute transaction cost
        turnover = abs(new_position - position)
        cost = turnover * (cost_bps / 10000) * initial_capital
        total_turnover += turnover
        
        if turnover > 0:
            n_trades += 1
            if holding_days > 0:
                holding_periods.append(holding_days)
            holding_days = 0
            
            equity.trades.append({
                "date": dates[i],
                "action": "BUY" if new_position > position else "SELL",
                "price": closes[i],
                "position": new_position,
                "turnover": turnover,
                "cost": cost,
            })
        else:
            holding_days += 1
        
        # Strategy return = previous position * asset return - costs
        strategy_return = position * asset_returns[i-1] - (cost / initial_capital)
        
        # Update equity
        new_equity = equity.equity[-1] * (1 + strategy_return)
        
        equity.positions.append(new_position)
        equity.asset_returns.append(asset_returns[i-1])
        equity.strategy_returns.append(strategy_return)
        equity.equity.append(new_equity)
        equity.dates.append(dates[i])
        equity.costs.append(cost)
        
        position = new_position
    
    # Final metrics
    if holding_days > 0:
        holding_periods.append(holding_days)
    
    equity.trades_count = n_trades
    equity.turnover = total_turnover
    equity.avg_holding_period = sum(holding_periods) / len(holding_periods) if holding_periods else 0
    
    # Compute metrics from equity curve
    equity.sharpe = _sharpe(equity.strategy_returns)
    equity.sortino = _sortino(equity.strategy_returns)
    equity.max_drawdown = _max_drawdown(equity.equity)
    equity.total_return = (equity.equity[-1] - equity.equity[0]) / equity.equity[0] if equity.equity else 0
    equity.calmar = equity.total_return / abs(equity.max_drawdown) if equity.max_drawdown != 0 else 0
    
    # Win rate
    wins = sum(1 for t in equity.trades if t.get("action") == "SELL" and t.get("pnl", 0) > 0)
    equity.win_rate = wins / n_trades * 100 if n_trades > 0 else 0
    
    # Skewness and kurtosis (standardized)
    equity.skewness = _skewness(equity.strategy_returns)
    equity.kurtosis = _kurtosis(equity.strategy_returns)
    
    return equity


def _sharpe(returns: list[float], periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio from strategy returns."""
    if not returns or len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean)**2 for r in returns) / len(returns))
    return (mean / std) * math.sqrt(periods_per_year) if std > 0 else 0.0


def _sortino(returns: list[float], periods_per_year: int = 252) -> float:
    """Annualized Sortino ratio from strategy returns."""
    if not returns or len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [min(r, 0)**2 for r in returns]
    dd = math.sqrt(sum(downside) / len(downside))
    return (mean / dd) * math.sqrt(periods_per_year) if dd > 0 else 0.0


def _max_drawdown(equity: list[float]) -> float:
    """Maximum drawdown from equity curve."""
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        dd = (e - peak) / peak
        max_dd = min(max_dd, dd)
    return max_dd


def _skewness(returns: list[float]) -> float:
    """Standardized skewness of returns."""
    if len(returns) < 3:
        return 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean)**2 for r in returns) / len(returns))
    if std == 0:
        return 0.0
    m3 = sum((r - mean)**3 for r in returns) / len(returns)
    return m3 / (std**3)


def _kurtosis(returns: list[float]) -> float:
    """Standardized excess kurtosis of returns."""
    if len(returns) < 4:
        return 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean)**2 for r in returns) / len(returns))
    if std == 0:
        return 0.0
    m4 = sum((r - mean)**4 for r in returns) / len(returns)
    return (m4 / (std**4)) - 3  # Excess kurtosis


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL FUNCTIONS FOR BASELINE STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════════

def _closes(prices: list[dict]) -> list[float]:
    return [p.get("close", p.get("price", 0)) for p in prices]


def buyhold_signal(prices: list[dict], i: int, current_position: float) -> float:
    """Always long after first day."""
    return 1.0


def momentum_signal(lookback: int = 20):
    """Momentum signal factory."""
    def signal(prices: list[dict], i: int, current_position: float) -> float:
        closes = _closes(prices)
        if i < lookback:
            return 0.0
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        if ret > 0:
            return 1.0
        elif ret < 0:
            return -1.0 if current_position > 0 else 0.0
        return current_position
    return signal


def rsi_signal(period: int = 14, buy_th: float = 30, sell_th: float = 70):
    """RSI signal factory."""
    def signal(prices: list[dict], i: int, current_position: float) -> float:
        closes = _closes(prices)
        if i < period + 1:
            return 0.0
        
        gains = [max(closes[j+1]-closes[j], 0) for j in range(i-period, i)]
        losses = [max(closes[j]-closes[j+1], 0) for j in range(i-period, i)]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        if rsi < buy_th:
            return 1.0
        elif rsi > sell_th:
            return 0.0
        return current_position
    return signal


def ma_crossover_signal(fast: int = 20, slow: int = 100):
    """MA crossover signal factory."""
    def signal(prices: list[dict], i: int, current_position: float) -> float:
        closes = _closes(prices)
        if i < slow:
            return 0.0
        
        ma_fast = sum(closes[i-fast:i]) / fast
        ma_slow = sum(closes[i-slow:i]) / slow
        
        if ma_fast > ma_slow:
            return 1.0
        else:
            return 0.0
    return signal


def reversal_signal(lookback: int = 20, threshold: float = 0.05):
    """Reversal signal factory."""
    def signal(prices: list[dict], i: int, current_position: float) -> float:
        closes = _closes(prices)
        if i < lookback:
            return 0.0
        
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        
        if ret < -threshold:
            return 1.0  # Buy oversold
        elif ret > threshold and current_position > 0:
            return 0.0  # Sell on reversion
        return current_position
    return signal
