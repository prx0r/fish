"""Ensemble Orchestrator — Combines all animal classes.

The ensemble objective:
Utility = E[R] - λσ - γDD - ηTurnover - κCosts - ρCorrelationWithExisting

Key principles:
1. Every strategy mutation is recorded in the experiment ledger
2. Judge destroys bad strategies
3. Strategy uniqueness prevents redundant avatars
4. Online learning adapts weights
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from fish.services.baselines import BASELINE_STRATEGIES, StrategyResult, _closes
from fish.services.fox import FOX_STRATEGIES
from fish.services.shark import SHARK_STRATEGIES
from fish.services.hedgehog import HEDGEHOG_STRATEGIES
from fish.services.wolf import WOLF_STRATEGIES
from fish.services.judge import judge_strategy, JudgeVerdict


ALL_STRATEGIES = {
    **BASELINE_STRATEGIES,
    **FOX_STRATEGIES,
    **SHARK_STRATEGIES,
    **HEDGEHOG_STRATEGIES,
    **WOLF_STRATEGIES,
}

STRATEGY_META = {
    **{k: {"class": "baseline"} for k in BASELINE_STRATEGIES},
    **{k: {"class": "residual"} for k in FOX_STRATEGIES},
    **{k: {"class": "earnings"} for k in SHARK_STRATEGIES},
    **{k: {"class": "volatility"} for k in HEDGEHOG_STRATEGIES},
    **{k: {"class": "regime"} for k in WOLF_STRATEGIES},
}


@dataclass
class StrategyFingerprint:
    """Behavioral fingerprint for strategy uniqueness."""
    strategy_name: str
    ticker: str
    market_beta: float = 0.0
    sector_beta: float = 0.0
    momentum_beta: float = 0.0
    avg_holding_period: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trades_per_year: float = 0.0


@dataclass
class EnsembleSignal:
    """Combined signal from multiple strategies."""
    ticker: str
    direction: str  # "long", "short", "flat"
    confidence: float  # 0-1
    strategies_voting: int
    strategies_total: int
    avg_sharpe: float
    avg_dsr: float
    signals: list[dict] = field(default_factory=list)


def _fingerprint_strategy(name: str, result: StrategyResult, closes: list[float]) -> StrategyFingerprint:
    """Create behavioral fingerprint for uniqueness measurement."""
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    # Market beta (simplified: correlation with own returns)
    if len(returns) > 20:
        own_returns = returns[20:]
        market_returns = returns[:-20]
        min_len = min(len(own_returns), len(market_returns))
        if min_len > 0:
            o = own_returns[:min_len]
            m = market_returns[:min_len]
            mean_o = sum(o) / len(o)
            mean_m = sum(m) / len(m)
            cov = sum((o[i] - mean_o) * (m[i] - mean_m) for i in range(min_len)) / min_len
            var_m = sum((m[i] - mean_m)**2 for i in range(min_len)) / min_len
            market_beta = cov / var_m if var_m > 0 else 0
        else:
            market_beta = 0
    else:
        market_beta = 0
    
    # Trades per year
    if result.trades_count > 0 and len(closes) > 0:
        years = len(closes) / 252
        trades_per_year = result.trades_count / years if years > 0 else 0
    else:
        trades_per_year = 0
    
    return StrategyFingerprint(
        strategy_name=name,
        ticker="",
        market_beta=market_beta,
        avg_holding_period=result.avg_holding_period if hasattr(result, 'avg_holding_period') else 0,
        turnover=result.turnover if hasattr(result, 'turnover') else 0,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        trades_per_year=trades_per_year,
    )


def _strategy_uniqueness(fingerprints: list[StrategyFingerprint]) -> dict[str, float]:
    """Measure how unique each strategy is relative to others."""
    if len(fingerprints) < 2:
        return {fp.strategy_name: 1.0 for fp in fingerprints}
    
    uniqueness = {}
    for i, fp1 in enumerate(fingerprints):
        min_dist = float('inf')
        for j, fp2 in enumerate(fingerprints):
            if i == j:
                continue
            # Euclidean distance on normalized features
            dist = math.sqrt(
                (fp1.market_beta - fp2.market_beta)**2 +
                (fp1.max_drawdown - fp2.max_drawdown)**2 +
                (fp1.win_rate - fp2.win_rate)**2 +
                (fp1.trades_per_year - fp2.trades_per_year)**2
            )
            min_dist = min(min_dist, dist)
        
        # Normalize to 0-1 (higher = more unique)
        uniqueness[fp1.strategy_name] = min(min_dist / 2.0, 1.0)
    
    return uniqueness


def run_ensemble(
    prices: list[dict],
    ticker: str,
    strategies: dict[str, callable] = None,
    min_score: int = 40,
) -> EnsembleSignal:
    """Run all strategies and combine signals."""
    if strategies is None:
        strategies = ALL_STRATEGIES
    
    closes = _closes(prices)
    signals = []
    verdicts = []
    
    for name, fn in strategies.items():
        try:
            result = fn(prices)
            verdict = judge_strategy(
                name=name,
                ticker=ticker,
                trades=result.trades,
                closes=closes,
                n_trials=len(strategies),
            )
            
            if verdict.score >= min_score:
                # Determine direction from trades
                if result.trades and result.trades[-1].get("action") == "BUY":
                    direction = "long"
                elif result.trades and result.trades[-1].get("action") == "SELL":
                    direction = "flat"
                else:
                    direction = "flat"
                
                signals.append({
                    "strategy": name,
                    "direction": direction,
                    "confidence": verdict.score / 100,
                    "sharpe": verdict.sharpe,
                    "dsr": verdict.dsr,
                })
                verdicts.append(verdict)
        except Exception:
            pass
    
    # Aggregate signals
    long_votes = sum(1 for s in signals if s["direction"] == "long")
    flat_votes = sum(1 for s in signals if s["direction"] == "flat")
    total = len(signals)
    
    if long_votes > flat_votes:
        direction = "long"
        confidence = long_votes / total if total > 0 else 0
    elif flat_votes > long_votes:
        direction = "flat"
        confidence = flat_votes / total if total > 0 else 0
    else:
        direction = "flat"
        confidence = 0.5
    
    avg_sharpe = sum(s["sharpe"] for s in signals) / len(signals) if signals else 0
    avg_dsr = sum(s["dsr"] for s in signals) / len(signals) if signals else 0
    
    return EnsembleSignal(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        strategies_voting=len(signals),
        strategies_total=len(strategies),
        avg_sharpe=avg_sharpe,
        avg_dsr=avg_dsr,
        signals=signals,
    )


def run_full_backtest(
    all_prices: dict[str, list[dict]],
    strategies: dict[str, callable] = None,
) -> dict:
    """Run full backtest across all stocks and strategies."""
    if strategies is None:
        strategies = ALL_STRATEGIES
    
    results = {}
    all_fingerprints = []
    
    for ticker, prices in all_prices.items():
        closes = _closes(prices)
        if len(closes) < 100:
            continue
        
        ticker_results = []
        for name, fn in strategies.items():
            try:
                result = fn(prices)
                verdict = judge_strategy(
                    name=name,
                    ticker=ticker,
                    trades=result.trades,
                    closes=closes,
                    n_trials=len(strategies),
                )
                fingerprint = _fingerprint_strategy(name, result, closes)
                fingerprint.ticker = ticker
                all_fingerprints.append(fingerprint)
                
                ticker_results.append({
                    "strategy": name,
                    "verdict": verdict.verdict,
                    "score": verdict.score,
                    "sharpe": verdict.sharpe,
                    "dsr": verdict.dsr,
                    "pbo": verdict.pbo,
                    "return": result.total_return * 100,
                    "trades": result.trades_count,
                })
            except Exception:
                pass
        
        results[ticker] = ticker_results
    
    # Strategy uniqueness
    uniqueness = _strategy_uniqueness(all_fingerprints)
    
    # Summary
    total_combos = sum(len(v) for v in results.values())
    passed = sum(1 for v in results.values() for r in v if r["verdict"] == "PASS")
    warned = sum(1 for v in results.values() for r in v if r["verdict"] == "WARN")
    failed = sum(1 for v in results.values() for r in v if r["verdict"] == "FAIL")
    
    return {
        "results": results,
        "uniqueness": uniqueness,
        "summary": {
            "total_combos": total_combos,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "pass_rate": passed / total_combos if total_combos > 0 else 0,
            "n_strategies": len(strategies),
            "n_tickers": len(results),
        },
    }
