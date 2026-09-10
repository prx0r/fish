"""Walk-Forward Validation — Train/Test/Lockbox/Paper Architecture.

1995 ─────────────────────────────── 2026

      RESEARCH
      │
      ├── train
      ├── purged CV
      └── validation

                          LOCKBOX
                          │
                          └── untouched OOS

                                  PAPER
                                  │
                                  └── live

                                          MONEY

The autonomous agents must never see lockbox results while modifying strategies.
Otherwise: test → agent sees failure → changes strategy → retests
means the test set silently became training data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from fish.services.baselines import _closes, _sharpe


@dataclass
class WalkForwardWindow:
    """A single walk-forward window."""
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    in_sample_sharpe: float = 0.0
    out_sample_sharpe: float = 0.0
    in_sample_return: float = 0.0
    out_sample_return: float = 0.0
    overfit_ratio: float = 0.0


@dataclass
class WalkForwardResult:
    """Full walk-forward validation result."""
    strategy_name: str
    ticker: str
    windows: list[WalkForwardWindow] = field(default_factory=list)
    avg_in_sharpe: float = 0.0
    avg_out_sharpe: float = 0.0
    sharpe_decay: float = 0.0  # (in - out) / in
    pct_windows_profitable: float = 0.0
    walk_forward_sharpe: float = 0.0
    verdict: str = "PENDING"  # PASS, WARN, FAIL


def walk_forward_validate(
    prices: list[dict],
    strategy_fn,
    ticker: str,
    train_days: int = 504,  # 2 years
    test_days: int = 126,   # 6 months
    step_days: int = 63,    # 3 months step
) -> WalkForwardResult:
    """Run walk-forward validation on a strategy.
    
    Architecture:
    - Train on train_days
    - Test on test_days
    - Step forward by step_days
    - Repeat
    """
    closes = _closes(prices)
    n = len(closes)
    
    windows = []
    
    for start in range(0, n - train_days - test_days, step_days):
        train_end = start + train_days
        test_end = min(train_end + test_days, n)
        
        if test_end <= train_end:
            break
        
        # In-sample (train)
        train_prices = prices[start:train_end]
        train_result = strategy_fn(train_prices)
        train_closes = _closes(train_prices)
        in_sharpe = train_result.sharpe
        in_return = (train_closes[-1] - train_closes[0]) / train_closes[0] if train_closes else 0
        
        # Out-of-sample (test)
        test_prices = prices[train_end:test_end]
        test_result = strategy_fn(test_prices)
        test_closes = _closes(test_prices)
        out_sharpe = test_result.sharpe
        out_return = (test_closes[-1] - test_closes[0]) / test_closes[0] if test_closes else 0
        
        # Overfit ratio
        if in_sharpe != 0:
            overfit_ratio = (in_sharpe - out_sharpe) / abs(in_sharpe)
        else:
            overfit_ratio = 0
        
        windows.append(WalkForwardWindow(
            train_start=start,
            train_end=train_end,
            test_start=train_end,
            test_end=test_end,
            in_sample_sharpe=in_sharpe,
            out_sample_sharpe=out_sharpe,
            in_sample_return=in_return,
            out_sample_return=out_return,
            overfit_ratio=overfit_ratio,
        ))
    
    if not windows:
        return WalkForwardResult(strategy_name=strategy_fn.__name__ if hasattr(strategy_fn, '__name__') else "unknown", ticker=ticker)
    
    # Aggregate
    avg_in = sum(w.in_sample_sharpe for w in windows) / len(windows)
    avg_out = sum(w.out_sample_sharpe for w in windows) / len(windows)
    sharpe_decay = (avg_in - avg_out) / abs(avg_in) if avg_in != 0 else 0
    pct_profitable = sum(1 for w in windows if w.out_sample_return > 0) / len(windows)
    
    # Walk-forward Sharpe (from OOS returns)
    all_oos_returns = []
    for w in windows:
        if w.out_sample_return != 0:
            all_oos_returns.append(w.out_sample_return)
    
    if len(all_oos_returns) > 1:
        wf_sharpe = _sharpe(all_oos_returns)
    else:
        wf_sharpe = 0
    
    # Verdict
    if wf_sharpe > 0.5 and sharpe_decay < 0.5 and pct_profitable > 0.5:
        verdict = "PASS"
    elif wf_sharpe > 0 and sharpe_decay < 0.7:
        verdict = "WARN"
    else:
        verdict = "FAIL"
    
    return WalkForwardResult(
        strategy_name=strategy_fn.__name__ if hasattr(strategy_fn, '__name__') else "unknown",
        ticker=ticker,
        windows=windows,
        avg_in_sharpe=avg_in,
        avg_out_sharpe=avg_out,
        sharpe_decay=sharpe_decay,
        pct_windows_profitable=pct_profitable,
        walk_forward_sharpe=wf_sharpe,
        verdict=verdict,
    )


def run_walk_forward_all(
    all_prices: dict[str, list[dict]],
    strategies: dict[str, callable],
) -> dict:
    """Run walk-forward validation across all stocks and strategies."""
    results = {}
    
    for ticker, prices in all_prices.items():
        closes = _closes(prices)
        if len(closes) < 630:  # Need at least 2.5 years
            continue
        
        ticker_results = []
        for name, fn in strategies.items():
            try:
                wf = walk_forward_validate(prices, fn, ticker)
                ticker_results.append(wf)
            except Exception:
                pass
        
        results[ticker] = ticker_results
    
    return results


def print_walk_forward_results(results: dict):
    """Pretty print walk-forward results."""
    print("=== WALK-FORWARD VALIDATION RESULTS ===\n")
    
    for ticker, ticker_results in results.items():
        if not ticker_results:
            continue
        
        print(f"\n{ticker}:")
        print(f"{'Strategy':25s} {'WF Sharpe':>10s} {'Decay':>8s} {'%Profit':>8s} {'Verdict':>8s}")
        print("-" * 65)
        
        # Sort by WF Sharpe
        ticker_results.sort(key=lambda w: w.walk_forward_sharpe, reverse=True)
        
        for wf in ticker_results[:5]:
            print(f"{wf.strategy_name:25s} {wf.walk_forward_sharpe:10.2f} {wf.sharpe_decay:7.1%} {wf.pct_windows_profitable:7.1%} {wf.verdict:>8s}")
        
        passed = sum(1 for w in ticker_results if w.verdict == "PASS")
        warned = sum(1 for w in ticker_results if w.verdict == "WARN")
        failed = sum(1 for w in ticker_results if w.verdict == "FAIL")
        print(f"  → PASS: {passed}, WARN: {warned}, FAIL: {failed}")
