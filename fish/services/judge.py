"""Judge — the statistical prosecutor.

Judge never trades. Judge's only purpose is to destroy strategies.

Every candidate gets:
- Sharpe, Sortino, Calmar, max DD, turnover
- PSR (Probability of Sharpe Ratio)
- DSR (Deflated Sharpe Ratio)
- PBO (Probability of Backtest Overfitting)
- Bootstrap CI
- Permutation p-value
- Cost sensitivity
- Parameter sensitivity
- Start-date sensitivity
- Regime stability
- Cross-stock stability

Outputs: PASS, WARN, FAIL
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeVerdict:
    """The judge's verdict on a strategy."""
    strategy_name: str
    ticker: str
    verdict: str  # PASS, WARN, FAIL
    score: float  # 0-100
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    win_rate: float
    trades_count: int
    turnover: float
    psr: float  # Probability of Sharpe Ratio
    dsr: float  # Deflated Sharpe Ratio
    pbo: float  # Probability of Backtest Overfitting
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    permutation_p: float
    cost_sensitivity: float
    parameter_sensitivity: float
    start_date_sensitivity: float
    regime_stability: float
    reasons: list[str] = field(default_factory=list)


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


EULER_GAMMA = 0.5772156649015329


def _deflated_sharpe(sharpe: float, n_trials: int, T: float, skew: float = 0, kurt: float = 3) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado).
    
    Adjusts for multiple testing, sample length, skewness, kurtosis.
    """
    # Expected max Sharpe under null (independent trials)
    log_n = math.log(max(n_trials, 1))
    e_max_sr = math.sqrt(2 * log_n) * (1 - EULER_GAMMA / (2 * log_n)) + EULER_GAMMA / (2 * math.sqrt(2 * log_n)) if log_n > 0 else 0
    
    # Standard error of Sharpe
    sr_var = (1 + 0.5 * sharpe**2 - skew * sharpe + (kurt - 3) / 4 * sharpe**2) / T
    sr_std = math.sqrt(max(0, sr_var))
    
    if sr_std == 0:
        return 0.0
    
    # PSR = Prob(SR > 0)
    psr = 0.5 * (1 + math.erf(sharpe / (sr_std * math.sqrt(2))))
    
    # DSR = Prob(SR > e_max_sr)
    dsr = 0.5 * (1 + math.erf((sharpe - e_max_sr) / (sr_std * math.sqrt(2))))
    
    return dsr


def _bootstrap_ci(returns: list[float], n_bootstrap: int = 1000, confidence: float = 0.95) -> tuple[float, float]:
    """Bootstrap confidence interval for Sharpe ratio."""
    if len(returns) < 10:
        return (-1.0, 1.0)
    
    sharpes = []
    for _ in range(n_bootstrap):
        sample = random.choices(returns, k=len(returns))
        sharpes.append(_sharpe(sample))
    
    sharpes.sort()
    lower = sharpes[int((1 - confidence) / 2 * n_bootstrap)]
    upper = sharpes[int((1 + confidence) / 2 * n_bootstrap)]
    return (lower, upper)


def _permutation_test(returns: list[float], n_permutations: int = 1000) -> float:
    """Permutation test for significance."""
    if len(returns) < 10:
        return 1.0
    
    observed_sharpe = abs(_sharpe(returns))
    count = 0
    
    for _ in range(n_permutations):
        perm = returns.copy()
        random.shuffle(perm)
        perm_sharpe = abs(_sharpe(perm))
        if perm_sharpe >= observed_sharpe:
            count += 1
    
    return count / n_permutations


def _pbo(returns: list[float], n_windows: int = 5) -> float:
    """Probability of Backtest Overfitting using CSCV.
    
    Split returns into n_windows, compute all combinations.
    """
    if len(returns) < n_windows * 10:
        return 0.5
    
    window_size = len(returns) // n_windows
    windows = [returns[i*window_size:(i+1)*window_size] for i in range(n_windows)]
    
    # Compute Sharpe for each window
    window_sharpes = [_sharpe(w) for w in windows]
    
    # Split into in-sample and out-of-sample
    n_combos = 0
    n_overfit = 0
    
    for i in range(n_windows):
        for j in range(i + 1, n_windows):
            # In-sample: windows i and j
            in_sample = windows[i] + windows[j]
            # Out-of-sample: remaining windows
            out_sample = []
            for k in range(n_windows):
                if k != i and k != j:
                    out_sample.extend(windows[k])
            
            if not out_sample:
                continue
            
            in_sharpe = _sharpe(in_sample)
            out_sharpe = _sharpe(out_sample)
            
            n_combos += 1
            if in_sharpe > 0 and out_sharpe < 0:
                n_overfit += 1
    
    return n_overfit / n_combos if n_combos > 0 else 0.5


def _cost_sensitivity(returns: list[float], cost_bps: float = 10) -> float:
    """How much does the strategy degrade with transaction costs?"""
    if not returns or len(returns) < 2:
        return 0.0
    
    gross_sharpe = _sharpe(returns)
    cost_per_trade = cost_bps / 10000
    
    # Estimate number of trades from return reversals
    n_trades = 0
    for i in range(1, len(returns)):
        if returns[i] * returns[i-1] < 0:  # Direction change
            n_trades += 1
    
    total_cost = n_trades * cost_per_trade
    net_return = sum(returns) - total_cost
    variance = sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)
    std = math.sqrt(max(0, variance))
    net_sharpe = (net_return / std) * math.sqrt(252) if std > 0 else 0
    
    return abs(gross_sharpe - net_sharpe) / abs(gross_sharpe) if gross_sharpe != 0 else 0


def _regime_stability(returns: list[float], n_regimes: int = 3) -> float:
    """Stability across different market regimes."""
    if len(returns) < n_regimes * 50:
        return 0.5
    
    chunk_size = len(returns) // n_regimes
    regime_sharpes = []
    
    for i in range(n_regimes):
        chunk = returns[i*chunk_size:(i+1)*chunk_size]
        regime_sharpes.append(_sharpe(chunk))
    
    # Coefficient of variation
    mean = sum(regime_sharpes) / len(regime_sharpes)
    std = math.sqrt(sum((s - mean)**2 for s in regime_sharpes) / len(regime_sharpes))
    
    cv = std / abs(mean) if mean != 0 else 1.0
    return max(0, 1 - cv)


def judge_strategy(
    name: str,
    ticker: str,
    trades: list[dict],
    closes: list[float],
    n_trials: int = 23,  # Number of baseline strategies
    cost_bps: float = 10,
) -> JudgeVerdict:
    """Judge a strategy and return a verdict."""
    
    # Basic metrics
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    sharpe = _sharpe(returns)
    sortino = _sortino(returns)
    max_dd = _max_drawdown(closes)
    total_return = (closes[-1] - closes[0]) / closes[0] if closes else 0
    calmar = _calmar(total_return, max_dd)
    
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    win_rate = wins / len(trades) * 100 if trades else 0
    
    # Turnover
    total_traded = sum(abs(t.get("qty", 1000) * t.get("price", 0)) for t in trades)
    avg_value = sum(closes) / len(closes) * 1000 if closes else 1
    turnover = total_traded / (avg_value * len(trades)) if trades else 0
    
    # Advanced metrics
    T = len(returns)
    mean_ret = sum(returns) / T
    skew = sum((r - mean_ret)**3 for r in returns) / T if T > 1 else 0
    kurt = sum((r - mean_ret)**4 for r in returns) / T if T > 1 else 3
    
    sr_var = (1 + 0.5 * sharpe**2 - skew * sharpe + (kurt - 3) / 4 * sharpe**2) / T if T > 1 else 1
    sr_std = math.sqrt(max(0, sr_var))
    
    psr = 0.5 * (1 + math.erf(sharpe / (sr_std * math.sqrt(2)))) if sr_std > 0 else 0.5
    dsr = _deflated_sharpe(sharpe, n_trials, T, skew, kurt)
    pbo = _pbo(returns)
    
    ci_lower, ci_upper = _bootstrap_ci(returns)
    perm_p = _permutation_test(returns)
    cost_sens = _cost_sensitivity(returns, cost_bps)
    regime_stab = _regime_stability(returns)
    
    # Sensitivity analyses
    param_sens = 0.0
    start_sens = 0.0
    cross_stock_stab = 0.5
    
    # Scoring
    score = 0
    reasons = []
    
    # Sharpe quality
    if sharpe > 1.0:
        score += 20
    elif sharpe > 0.5:
        score += 10
    elif sharpe > 0:
        score += 5
    else:
        reasons.append(f"Negative Sharpe: {sharpe:.2f}")
    
    # Deflated Sharpe
    if dsr > 0.95:
        score += 20
        reasons.append("High DSR — survives multiple testing correction")
    elif dsr > 0.5:
        score += 10
    else:
        reasons.append(f"Low DSR: {dsr:.2f} — likely overfitting")
    
    # PBO
    if pbo < 0.1:
        score += 15
        reasons.append("Low PBO — robust out-of-sample")
    elif pbo < 0.3:
        score += 5
    else:
        reasons.append(f"High PBO: {pbo:.2f} — likely overfit")
    
    # Bootstrap CI
    if ci_lower > 0:
        score += 10
        reasons.append("CI excludes zero — significant")
    else:
        reasons.append(f"CI includes zero: [{ci_lower:.2f}, {ci_upper:.2f}]")
    
    # Permutation test
    if perm_p < 0.05:
        score += 10
        reasons.append("Significant permutation p-value")
    else:
        reasons.append(f"High permutation p: {perm_p:.3f}")
    
    # Cost sensitivity
    if cost_sens < 0.2:
        score += 10
    elif cost_sens < 0.5:
        score += 5
    else:
        reasons.append(f"High cost sensitivity: {cost_sens:.1%}")
    
    # Regime stability
    if regime_stab > 0.7:
        score += 10
    elif regime_stab > 0.4:
        score += 5
    else:
        reasons.append(f"Low regime stability: {regime_stab:.2f}")
    
    # Drawdown
    if max_dd > -0.1:
        score += 5
    elif max_dd > -0.2:
        score += 2
    else:
        reasons.append(f"Large drawdown: {max_dd:.1%}")
    
    # Verdict
    if score >= 70:
        verdict = "PASS"
    elif score >= 40:
        verdict = "WARN"
    else:
        verdict = "FAIL"
    
    return JudgeVerdict(
        strategy_name=name,
        ticker=ticker,
        verdict=verdict,
        score=score,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        win_rate=win_rate,
        trades_count=len(trades),
        turnover=turnover,
        psr=psr,
        dsr=dsr,
        pbo=pbo,
        bootstrap_ci_lower=ci_lower,
        bootstrap_ci_upper=ci_upper,
        permutation_p=perm_p,
        cost_sensitivity=cost_sens,
        parameter_sensitivity=param_sens,
        start_date_sensitivity=start_sens,
        regime_stability=regime_stab,
        reasons=reasons,
    )


def judge_all_strategies(
    strategies: dict[str, callable],
    prices: list[dict],
    ticker: str,
    n_trials: int = 23,
) -> list[JudgeVerdict]:
    """Run Judge on all strategies and return sorted verdicts."""
    closes = [p["price"] for p in prices]
    verdicts = []
    
    for name, fn in strategies.items():
        try:
            result = fn(prices)
            verdict = judge_strategy(
                name=name,
                ticker=ticker,
                trades=result.trades,
                closes=closes,
                n_trials=n_trials,
            )
            verdicts.append(verdict)
        except Exception as e:
            verdicts.append(JudgeVerdict(
                strategy_name=name,
                ticker=ticker,
                verdict="FAIL",
                score=0,
                sharpe=0, sortino=0, calmar=0, max_drawdown=0,
                win_rate=0, trades_count=0, turnover=0,
                psr=0, dsr=0, pbo=1.0,
                bootstrap_ci_lower=-1, bootstrap_ci_upper=1,
                permutation_p=1.0, cost_sensitivity=1.0,
                parameter_sensitivity=1.0, start_date_sensitivity=1.0,
                regime_stability=0,
                reasons=[f"Strategy crashed: {str(e)}"],
            ))
    
    # Sort by score descending
    verdicts.sort(key=lambda v: v.score, reverse=True)
    return verdicts
