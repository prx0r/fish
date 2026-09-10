"""30 dumb baseline strategies — the control group.

If an elaborate agent cannot beat these, it dies.

Every strategy follows the same interface:
    strategy(prices: list[dict], params: dict) -> StrategyResult

prices = [{"date": "2024-01-01", "price": 100.0, "open": 99, "high": 101, "low": 98, "volume": 1000000}, ...]
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class StrategyResult:
    """Result of running a strategy."""
    name: str
    trades: list[dict] = field(default_factory=list)
    total_return: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades_count: int = 0
    turnover: float = 0.0
    avg_holding_period: float = 0.0


def _closes(prices: list[dict]) -> list[float]:
    return [p.get("close", p.get("price", 0)) for p in prices]


def _returns(closes: list[float]) -> list[float]:
    return [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]


def _sharpe(returns: list[float], periods_per_year: int = 252) -> float:
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean)**2 for r in returns) / len(returns))
    return (mean / std) * math.sqrt(periods_per_year) if std > 0 else 0.0


def _sortino(returns: list[float], periods_per_year: int = 252) -> float:
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [min(r, 0)**2 for r in returns]
    dd = math.sqrt(sum(downside) / len(downside))
    return (mean / dd) * math.sqrt(periods_per_year) if dd > 0 else 0.0


def _max_drawdown(closes: list[float]) -> float:
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        peak = max(peak, c)
        dd = (c - peak) / peak
        max_dd = min(max_dd, dd)
    return max_dd


def _calmar(total_return: float, max_dd: float) -> float:
    return total_return / abs(max_dd) if max_dd != 0 else 0.0


def _build_result(name: str, trades: list[dict], closes: list[float]) -> StrategyResult:
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    initial = closes[0] * 1000 if closes else 1
    total_return = total_pnl / initial
    returns = _returns(closes)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    max_dd = _max_drawdown(closes)
    
    # Holding periods
    holding_periods = []
    for i in range(0, len(trades) - 1, 2):
        if i + 1 < len(trades):
            hold = trades[i+1].get("day", 0) - trades[i].get("day", 0)
            holding_periods.append(hold)
    avg_hold = sum(holding_periods) / len(holding_periods) if holding_periods else 0
    
    # Turnover
    total_traded = sum(abs(t.get("qty", 1000) * t.get("price", 0)) for t in trades)
    avg_value = sum(closes) / len(closes) * 1000 if closes else 1
    turnover = total_traded / (avg_value * len(trades)) if trades else 0
    
    return StrategyResult(
        name=name, trades=trades,
        total_return=total_return, sharpe=_sharpe(returns),
        sortino=_sortino(returns), calmar=_calmar(total_return, max_dd),
        max_drawdown=max_dd, win_rate=wins / len(trades) * 100 if trades else 0,
        trades_count=len(trades), turnover=turnover,
        avg_holding_period=avg_hold,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BUY & HOLD
# ═══════════════════════════════════════════════════════════════════════════════

def buy_and_hold(prices: list[dict], **kw) -> StrategyResult:
    """Buy at start, hold forever. The benchmark."""
    closes = _closes(prices)
    trades = [{"date": prices[0]["date"], "action": "BUY", "price": closes[0], "qty": 1000, "day": 0}]
    return _build_result("Buy & Hold", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# MOMENTUM (5 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def _momentum(prices: list[dict], lookback: int, **kw) -> StrategyResult:
    """Buy when N-day return > 0, sell when < 0."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        if ret > 0 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif ret < 0 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Momentum-{lookback}d", trades, closes)


def momentum_20d(prices, **kw): return _momentum(prices, 20)
def momentum_60d(prices, **kw): return _momentum(prices, 60)
def momentum_120d(prices, **kw): return _momentum(prices, 120)
def momentum_252d(prices, **kw): return _momentum(prices, 252)

def momentum_12_1(prices: list[dict], **kw) -> StrategyResult:
    """12-month momentum minus 1-month reversal."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(252, len(closes)):
        ret_12m = (closes[i] - closes[i-252]) / closes[i-252]
        ret_1m = (closes[i] - closes[i-20]) / closes[i-20]
        signal = ret_12m - ret_1m
        if signal > 0 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif signal < 0 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result("Momentum-12_1", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# TREND (5 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def _ma_crossover(prices: list[dict], fast: int, slow: int, **kw) -> StrategyResult:
    """Buy when fast MA crosses above slow MA."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(slow, len(closes)):
        ma_fast = sum(closes[i-fast:i]) / fast
        ma_slow = sum(closes[i-slow:i]) / slow
        prev_fast = sum(closes[i-fast-1:i-1]) / fast
        prev_slow = sum(closes[i-slow-1:i-1]) / slow
        if prev_fast <= prev_slow and ma_fast > ma_slow and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif prev_fast >= prev_slow and ma_fast < ma_slow and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Trend-{fast}/{slow}", trades, closes)


def trend_10_50(prices, **kw): return _ma_crossover(prices, 10, 50)
def trend_20_100(prices, **kw): return _ma_crossover(prices, 20, 100)
def trend_50_200(prices, **kw): return _ma_crossover(prices, 50, 200)

def _donchian(prices: list[dict], period: int, **kw) -> StrategyResult:
    """Buy on breakout above N-day high, sell on break below N-day low."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(period, len(closes)):
        high = max(closes[i-period:i])
        low = min(closes[i-period:i])
        if closes[i] > high and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif closes[i] < low and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Donchian-{period}", trades, closes)


def donchian_20(prices, **kw): return _donchian(prices, 20)
def donchian_55(prices, **kw): return _donchian(prices, 55)


# ═══════════════════════════════════════════════════════════════════════════════
# REVERSAL (6 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def _reversal(prices: list[dict], lookback: int, **kw) -> StrategyResult:
    """Buy when N-day return < -threshold, sell on reversion to 0."""
    closes = _closes(prices)
    threshold = 0.05
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        if ret < -threshold and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif ret > 0 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Reversal-{lookback}d", trades, closes)


def reversal_1d(prices, **kw): return _reversal(prices, 1)
def reversal_5d(prices, **kw): return _reversal(prices, 5)
def reversal_20d(prices, **kw): return _reversal(prices, 20)

def rsi_strategy(prices: list[dict], period: int = 14, buy_th: float = 30, sell_th: float = 70, **kw) -> StrategyResult:
    """Buy when RSI < buy_th, sell when RSI > sell_th."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(period, len(closes)):
        gains = [max(closes[j+1]-closes[j], 0) for j in range(i-period, i)]
        losses = [max(closes[j]-closes[j+1], 0) for j in range(i-period, i)]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        if rsi < buy_th and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif rsi > sell_th and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"RSI-{period}", trades, closes)

def rsi_14(prices, **kw): return rsi_strategy(prices, 14)

def bollinger_strategy(prices: list[dict], period: int = 20, num_std: float = 2.0, **kw) -> StrategyResult:
    """Buy below lower band, sell above middle band."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(period, len(closes)):
        window = closes[i-period:i]
        mean = sum(window) / period
        std = math.sqrt(sum((x - mean)**2 for x in window) / period)
        upper = mean + num_std * std
        lower = mean - num_std * std
        if closes[i] < lower and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif closes[i] > mean and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Bollinger-{period}", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# VOLATILITY (3 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def vol_target_momentum(prices: list[dict], target_vol: float = 0.15, **kw) -> StrategyResult:
    """Momentum scaled by inverse volatility."""
    closes = _closes(prices)
    returns = _returns(closes)
    trades, position, entry = [], 0, 0
    lookback = 20
    for i in range(lookback + 1, len(closes)):
        vol = math.sqrt(sum((r - sum(returns[i-lookback:i])/lookback)**2 for r in returns[i-lookback:i]) / lookback) * math.sqrt(252)
        mom = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        if vol > 0:
            scale = target_vol / vol
        else:
            scale = 1.0
        signal = mom * scale
        if signal > 0.02 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif signal < -0.02 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result("VolTargetMomentum", trades, closes)


def low_vol(prices: list[dict], lookback: int = 60, **kw) -> StrategyResult:
    """Buy stocks with lowest recent volatility (proxy for low-vol anomaly)."""
    closes = _closes(prices)
    returns = _returns(closes)
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        vol = math.sqrt(sum((r - sum(returns[i-lookback:i])/lookback)**2 for r in returns[i-lookback:i]) / lookback)
        if vol < 0.01 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif vol > 0.03 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result("LowVol", trades, closes)


def breakout_vol(prices: list[dict], period: int = 20, **kw) -> StrategyResult:
    """Breakout × volatility filter."""
    closes = _closes(prices)
    returns = _returns(closes)
    trades, position, entry = [], 0, 0
    for i in range(period + 1, len(closes)):
        high = max(closes[i-period:i])
        vol = math.sqrt(sum((r - sum(returns[i-period:i])/period)**2 for r in returns[i-period:i]) / period)
        if closes[i] > high and vol < 0.03 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif closes[i] < entry * 0.95 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"BreakoutVol-{period}", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# FUNDAMENTAL PROXIES (2 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def value_proxy(prices: list[dict], lookback: int = 252, **kw) -> StrategyResult:
    """Buy when price is lowest in N-day window (proxy for value)."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        low = min(closes[i-lookback:i])
        if closes[i] < low * 1.05 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif closes[i] > entry * 1.2 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Value-{lookback}", trades, closes)


def quality_proxy(prices: list[dict], lookback: int = 60, **kw) -> StrategyResult:
    """Buy stocks with lowest drawdown (proxy for quality/stability)."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        window = closes[i-lookback:i]
        peak = window[0]
        max_dd = 0
        for c in window:
            peak = max(peak, c)
            dd = (c - peak) / peak
            max_dd = min(max_dd, dd)
        if max_dd > -0.1 and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif max_dd < -0.3 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"Quality-{lookback}", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME (2 variants)
# ═══════════════════════════════════════════════════════════════════════════════

def regime_ma(prices: list[dict], fast: int = 20, slow: int = 100, **kw) -> StrategyResult:
    """Simple regime: above MA = long, below = flat."""
    closes = _closes(prices)
    trades, position, entry = [], 0, 0
    for i in range(slow, len(closes)):
        ma = sum(closes[i-slow:i]) / slow
        if closes[i] > ma and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif closes[i] < ma and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"RegimeMA-{fast}/{slow}", trades, closes)


def regime_vol(prices: list[dict], lookback: int = 60, vol_thresh: float = 0.02, **kw) -> StrategyResult:
    """Long when vol is low, flat when vol is high."""
    closes = _closes(prices)
    returns = _returns(closes)
    trades, position, entry = [], 0, 0
    for i in range(lookback, len(closes)):
        vol = math.sqrt(sum((r - sum(returns[i-lookback:i])/lookback)**2 for r in returns[i-lookback:i]) / lookback)
        if vol < vol_thresh and position == 0:
            position, entry = 1000, closes[i]
            trades.append({"date": prices[i]["date"], "action": "BUY", "price": closes[i], "qty": 1000, "day": i})
        elif vol > vol_thresh * 2 and position > 0:
            pnl = (closes[i] - entry) * position
            trades.append({"date": prices[i]["date"], "action": "SELL", "price": closes[i], "qty": 1000, "pnl": pnl, "day": i})
            position = 0
    return _build_result(f"RegimeVol-{lookback}", trades, closes)


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

BASELINE_STRATEGIES = {
    # Buy & Hold
    "buyhold": buy_and_hold,
    # Momentum (5)
    "momentum_20d": momentum_20d,
    "momentum_60d": momentum_60d,
    "momentum_120d": momentum_120d,
    "momentum_252d": momentum_252d,
    "momentum_12_1": momentum_12_1,
    # Trend (5)
    "trend_10_50": trend_10_50,
    "trend_20_100": trend_20_100,
    "trend_50_200": trend_50_200,
    "donchian_20": donchian_20,
    "donchian_55": donchian_55,
    # Reversal (6)
    "reversal_1d": reversal_1d,
    "reversal_5d": reversal_5d,
    "reversal_20d": reversal_20d,
    "rsi_14": rsi_14,
    "bollinger_20": bollinger_strategy,
    # Volatility (3)
    "vol_target_momentum": vol_target_momentum,
    "low_vol": low_vol,
    "breakout_vol": breakout_vol,
    # Fundamental (2)
    "value_252": value_proxy,
    "quality_60": quality_proxy,
    # Regime (2)
    "regime_ma_20_100": regime_ma,
    "regime_vol_60": regime_vol,
}

STRATEGY_META = {
    "buyhold": {"animal": "Turtle", "class": "benchmark"},
    "momentum_20d": {"animal": "Bull", "class": "momentum"},
    "momentum_60d": {"animal": "Bull", "class": "momentum"},
    "momentum_120d": {"animal": "Bull", "class": "momentum"},
    "momentum_252d": {"animal": "Bull", "class": "momentum"},
    "momentum_12_1": {"animal": "Bull", "class": "momentum"},
    "trend_10_50": {"animal": "Bull", "class": "trend"},
    "trend_20_100": {"animal": "Bull", "class": "trend"},
    "trend_50_200": {"animal": "Bull", "class": "trend"},
    "donchian_20": {"animal": "Bull", "class": "trend"},
    "donchian_55": {"animal": "Bull", "class": "trend"},
    "reversal_1d": {"animal": "Bear", "class": "reversal"},
    "reversal_5d": {"animal": "Bear", "class": "reversal"},
    "reversal_20d": {"animal": "Bear", "class": "reversal"},
    "rsi_14": {"animal": "Bear", "class": "reversal"},
    "bollinger_20": {"animal": "Bear", "class": "reversal"},
    "vol_target_momentum": {"animal": "Hedgehog", "class": "volatility"},
    "low_vol": {"animal": "Hedgehog", "class": "volatility"},
    "breakout_vol": {"animal": "Hedgehog", "class": "volatility"},
    "value_252": {"animal": "Turtle", "class": "fundamental"},
    "quality_60": {"animal": "Turtle", "class": "fundamental"},
    "regime_ma_20_100": {"animal": "Wolf", "class": "regime"},
    "regime_vol_60": {"animal": "Wolf", "class": "regime"},
}
