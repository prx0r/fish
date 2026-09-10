"""Judge — the statistical prosecutor (FIXED v2).

Judge never trades. Judge's only purpose is to destroy strategies.

FIXES from v1:
1. Now computes metrics from strategy equity curve, not stock returns
2. Correct skewness/kurtosis (standardized)
3. Real trade-based costs
4. Cross-strategy PBO (CSCV)
5. Permutation test on signals, not returns
6. Effective number of independent trials
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from fish.services.equity import StrategyEquity, _sharpe, _sortino, _max_drawdown, _skewness, _kurtosis


EULER_GAMMA = 0.5772156649015329


@dataclass
class JudgeVerdict:
    """The judge's verdict on a strategy."""
    strategy_name: str
    ticker: str
    verdict: str  # PASS, WARN, FAIL
    score: float  # 0-100
    
    # Metrics from strategy equity curve
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    total_return: float
    win_rate: float
    trades_count: int
    turnover: float
    skewness: float
    kurtosis: float
    
    # Statistical tests
    psr: float
    dsr: float
    pbo: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    permutation_p: float
    
    # Cost analysis
    cost_sensitivity: float
    
    # Regime analysis
    regime_stability: float
    
    reasons: list[str] = field(default_factory=list)


def _deflated_sharpe(sharpe: float, n_trials: float, T: float, skew: float = 0, kurt: float = 0) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado).
    
    Uses effective number of independent trials, not raw count.
    """
    if T <= 1:
        return 0.0
    
    # Expected max Sharpe under null
    log_n = math.log(max(n_trials, 1))
    e_max_sr = math.sqrt(2 * log_n) * (1 - EULER_GAMMA / (2 * log_n)) + EULER_GAMMA / (2 * math.sqrt(2 * log_n)) if log_n > 0 else 0
    
    # Standard error of Sharpe (with skew/kurtosis correction)
    sr_var = (1 + 0.5 * sharpe**2 - skew * sharpe + (kurt) / 4 * sharpe**2) / T
    sr_std = math.sqrt(max(0, sr_var))
    
    if sr_std == 0:
        return 0.0
    
    # DSR = Prob(SR > e_max_sr)
    dsr = 0.5 * (1 + math.erf((sharpe - e_max_sr) / (sr_std * math.sqrt(2))))
    
    return dsr


def _pbo_cross_strategy(
    strategy_returns: dict[str, list[float]],
    n_windows: int = 5,
) -> float:
    """Probability of Backtest Overfitting using CSCV.
    
    Requires multiple strategy return series.
    Returns probability that IS winner underperforms OOS.
    """
    if len(strategy_returns) < 2:
        return 0.5
    
    strategies = list(strategy_returns.keys())
    n_strategies = len(strategies)
    
    if n_strategies < 2:
        return 0.5
    
    # Get common length
    min_len = min(len(v) for v in strategy_returns.values())
    if min_len < n_windows * 10:
        return 0.5
    
    window_size = min_len // n_windows
    
    # Build strategy × time return matrix
    matrix = {}
    for strat in strategies:
        returns = strategy_returns[strat][:min_len]
        matrix[strat] = [returns[i*window_size:(i+1)*window_size] for i in range(n_windows)]
    
    # CSCV: count how often IS winner is OOS loser
    n_combos = 0
    n_overfit = 0
    
    for i in range(n_windows):
        for j in range(i + 1, n_windows):
            # In-sample: windows i and j
            is_returns = {}
            for strat in strategies:
                is_returns[strat] = matrix[strat][i] + matrix[strat][j]
            
            # Out-of-sample: remaining windows
            oos_returns = {}
            for strat in strategies:
                oos_returns[strat] = []
                for k in range(n_windows):
                    if k != i and k != j:
                        oos_returns[strat].extend(matrix[strat][k])
            
            if not oos_returns[strategies[0]]:
                continue
            
            # Find IS winner
            is_sharpes = {strat: _sharpe(rets) for strat, rets in is_returns.items()}
            is_winner = max(is_sharpes, key=is_sharpes.get)
            
            # Find OOS rank of IS winner
            oos_sharpes = {strat: _sharpe(rets) for strat, rets in oos_returns.items()}
            sorted_oos = sorted(oos_sharpes.values(), reverse=True)
            is_winner_rank = sorted_oos.index(oos_sharpes[is_winner])
            
            # Overfit if IS winner is below median OOS
            n_combos += 1
            if is_winner_rank >= n_strategies / 2:
                n_overfit += 1
    
    return n_overfit / n_combos if n_combos > 0 else 0.5


def _permutation_test_signals(
    prices: list[dict],
    signal_fn,
    n_permutations: int = 100,
    cost_bps: float = 10,
) -> float:
    """Permutation test on strategy signals.
    
    Shuffles signals relative to returns to test if signal
    contains timing information.
    """
    from fish.services.equity import compute_strategy_equity
    
    if len(prices) < 50:
        return 1.0
    
    # Get baseline equity
    baseline = compute_strategy_equity("baseline", prices, signal_fn, cost_bps)
    if not baseline.strategy_returns:
        return 1.0
    
    baseline_sharpe = abs(baseline.sharpe)
    
    # Shuffle signals and recompute
    count = 0
    for _ in range(n_permutations):
        # Create shuffled signal function
        closes = [p.get("close", p.get("price", 0)) for p in prices]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        
        # Generate original signals
        original_signals = []
        position = 0
        for i in range(1, len(prices)):
            new_pos = signal_fn(prices, i, position)
            original_signals.append(new_pos)
            position = new_pos
        
        # Shuffle signals
        shuffled_signals = original_signals.copy()
        random.shuffle(shuffled_signals)
        
        # Compute shuffled equity
        equity = [100000]
        position = 0
        for i in range(len(shuffled_signals)):
            new_position = shuffled_signals[i]
            turnover = abs(new_position - position)
            cost = turnover * (cost_bps / 10000)
            
            strat_return = position * returns[i] - cost
            equity.append(equity[-1] * (1 + strat_return))
            position = new_position
        
        shuffled_returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
        shuffled_sharpe = abs(_sharpe(shuffled_returns))
        
        if shuffled_sharpe >= baseline_sharpe:
            count += 1
    
    return count / n_permutations


def _bootstrap_ci(
    strategy_returns: list[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Bootstrap confidence interval for Sharpe ratio."""
    if len(strategy_returns) < 10:
        return (-1.0, 1.0)
    
    sharpes = []
    for _ in range(n_bootstrap):
        sample = random.choices(strategy_returns, k=len(strategy_returns))
        sharpes.append(_sharpe(sample))
    
    sharpes.sort()
    lower = sharpes[int((1 - confidence) / 2 * n_bootstrap)]
    upper = sharpes[int((1 + confidence) / 2 * n_bootstrap)]
    return (lower, upper)


def _regime_stability(strategy_returns: list[float], n_regimes: int = 3) -> float:
    """Stability across different market regimes."""
    if len(strategy_returns) < n_regimes * 50:
        return 0.5
    
    chunk_size = len(strategy_returns) // n_regimes
    regime_sharpes = []
    
    for i in range(n_regimes):
        chunk = strategy_returns[i*chunk_size:(i+1)*chunk_size]
        regime_sharpes.append(_sharpe(chunk))
    
    # Coefficient of variation
    mean = sum(regime_sharpes) / len(regime_sharpes)
    std = math.sqrt(sum((s - mean)**2 for s in regime_sharpes) / len(regime_sharpes))
    
    cv = std / abs(mean) if mean != 0 else 1.0
    return max(0, 1 - cv)


def _effective_trials(strategy_returns: dict[str, list[float]]) -> float:
    """Compute effective number of independent trials from correlation.
    
    Highly correlated strategies count as less than 1 independent trial.
    """
    strategies = list(strategy_returns.keys())
    n = len(strategies)
    
    if n < 2:
        return float(n)
    
    # Build correlation matrix
    min_len = min(len(v) for v in strategy_returns.values())
    if min_len < 20:
        return float(n)
    
    returns_matrix = []
    for strat in strategies:
        returns_matrix.append(strategy_returns[strat][:min_len])
    
    # Compute pairwise correlations
    correlations = []
    for i in range(n):
        for j in range(i+1, n):
            r_i = returns_matrix[i]
            r_j = returns_matrix[j]
            mean_i = sum(r_i) / len(r_i)
            mean_j = sum(r_j) / len(r_j)
            
            cov = sum((r_i[k] - mean_i) * (r_j[k] - mean_j) for k in range(min_len)) / min_len
            std_i = math.sqrt(sum((r - mean_i)**2 for r in r_i) / min_len)
            std_j = math.sqrt(sum((r - mean_j)**2 for r in r_j) / min_len)
            
            corr = cov / (std_i * std_j) if std_i * std_j > 0 else 0
            correlations.append(abs(corr))
    
    # Average correlation
    avg_corr = sum(correlations) / len(correlations) if correlations else 0
    
    # Effective trials (simplified)
    # If all perfectly correlated, effective = 1
    # If all independent, effective = n
    effective = n * (1 - avg_corr) + avg_corr
    
    return max(1, min(effective, n))


def judge_strategy(
    name: str,
    ticker: str,
    equity: StrategyEquity,
    all_strategy_returns: dict[str, list[float]] = None,
    n_trials: int = 23,
    cost_bps: float = 10,
) -> JudgeVerdict:
    """Judge a strategy using its equity curve.
    
    All metrics come from equity.strategy_returns, not stock returns.
    """
    
    # Get strategy returns
    strategy_returns = equity.strategy_returns if equity.strategy_returns else [0]
    
    # Basic metrics (already computed in equity)
    sharpe = equity.sharpe
    sortino = equity.sortino
    max_dd = equity.max_drawdown
    total_return = equity.total_return
    calmar = equity.calmar
    win_rate = equity.win_rate
    trades_count = equity.trades_count
    turnover = equity.turnover
    skewness = equity.skewness
    kurtosis = equity.kurtosis
    
    # Effective number of independent trials
    if all_strategy_returns and len(all_strategy_returns) > 1:
        effective_n = _effective_trials(all_strategy_returns)
    else:
        effective_n = float(n_trials)
    
    # Advanced metrics
    T = len(strategy_returns)
    
    # PSR
    sr_var = (1 + 0.5 * sharpe**2 - skewness * sharpe + kurtosis / 4 * sharpe**2) / T if T > 1 else 1
    sr_std = math.sqrt(max(0, sr_var))
    psr = 0.5 * (1 + math.erf(sharpe / (sr_std * math.sqrt(2)))) if sr_std > 0 else 0.5
    
    # DSR
    dsr = _deflated_sharpe(sharpe, effective_n, T, skewness, kurtosis)
    
    # PBO (cross-strategy)
    if all_strategy_returns and len(all_strategy_returns) > 2:
        pbo = _pbo_cross_strategy(all_strategy_returns)
    else:
        pbo = 0.5
    
    # Bootstrap CI
    ci_lower, ci_upper = _bootstrap_ci(strategy_returns)
    
    # Permutation test
    perm_p = 1.0  # Placeholder — need signal_fn for real test
    
    # Cost sensitivity (using actual turnover)
    avg_trade_value = equity.equity[0] if equity.equity else 100000
    total_cost = sum(equity.costs)
    cost_sensitivity = total_cost / (equity.equity[-1] - equity.equity[0] + total_cost) if equity.equity[-1] > equity.equity[0] else 1.0
    
    # Regime stability
    regime_stab = _regime_stability(strategy_returns)
    
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
    
    # Cost sensitivity
    if cost_sensitivity < 0.1:
        score += 10
    elif cost_sensitivity < 0.3:
        score += 5
    else:
        reasons.append(f"High cost sensitivity: {cost_sensitivity:.1%}")
    
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
    
    # Turnover penalty
    if turnover > 50:
        score -= 5
        reasons.append(f"High turnover: {turnover:.0f}")
    
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
        total_return=total_return,
        win_rate=win_rate,
        trades_count=trades_count,
        turnover=turnover,
        skewness=skewness,
        kurtosis=kurtosis,
        psr=psr,
        dsr=dsr,
        pbo=pbo,
        bootstrap_ci_lower=ci_lower,
        bootstrap_ci_upper=ci_upper,
        permutation_p=perm_p,
        cost_sensitivity=cost_sensitivity,
        regime_stability=regime_stab,
        reasons=reasons,
    )
