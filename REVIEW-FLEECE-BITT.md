# Fish Backtest & Evaluation — Cross-Repo Review

**Date**: 2026-09-10
**Source repos reviewed**: /fleece (DeltaTuna), /bitt (Bittensor/CGE)
**Scope**: Backtesting, strategy evaluation, game design, calibration, statistical rigor
**Principle**: Additive only — no rewrites, no infrastructure changes

---

## Executive Summary

Both /fleece and /bitt solve harder versions of Fish's problem. Fleece evolves options allocation strategies against ground-truth benchmarks with full statistical rigor. Bitt evaluates code analysis strategies across hundreds of Bittensor subnets with Bayesian scoring and layered evaluation.

Fish currently has: working ensemble, 41 strategies, walk-forward backtest, and a game kernel (V2) with locked forecasts. What it's missing is the **statistical discipline** that makes results trustworthy.

This document catalogs every adoptable pattern, ranked by impact × effort.

---

## Part 1: What Fleece Does That Fish Should Steal

### 1.1 Deterministic Paired Backtests (CRITICAL)

**File**: `/root/fleece/experiments/deltatuna_lab/runner.py`

Every strategy arm sees **identical returns** via deterministic RNG seeded by `(seed, period, strategy_id)`. Differences come from allocation logic only, never from data differences.

**Why this matters for Fish**: Our current ensemble backtest runs each strategy on the same price data, which is correct. But the ensemble *vote* changes based on strategy ordering (dict iteration order). Two runs can produce different results.

**Adopt**:
```python
# Seed every strategy call deterministically
rng = random.Random(hash((seed, ticker, strategy_name)) & 0xFFFFFFFF)
result = fn(prices=prices, rng=rng)
```

**Where**: `run_ensemble.py`, `run_backtest.py`

### 1.2 Wilson Score Intervals for Small-N

**File**: `/root/fleece/fleece/core/stats.py`

Wilson intervals are the standard for binomial proportions at small sample sizes. Our calibration bins have 3-17 observations — naive confidence intervals are meaningless there.

**Adopt**:
```python
def wilson(k: int, n: int, z: float = 1.959963984540054) -> dict:
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"p": p, "ci95": (center - half, center + half), "center": center}
```

**Where**: `game_v2.py` calibration bins, ensemble confidence reporting

### 1.3 Pilot vs Confirmatory Discipline

**File**: `/root/fleece/fleece/core/stats.py`

```python
def pilot_or_confirmatory(n_decided: int) -> str:
    return "CONFIRMATORY" if n_decided >= 30 else "PILOT"
```

n < 30 is **directional only, never confirmatory**. This is exactly what our game needs — don't claim someone "beat Fish" after 5 rounds.

**Adopt**: Add to game result output. After 30 rounds, upgrade from PILOT to CONFIRMATORY.

### 1.4 Immortal Controls

**File**: `/root/fleece/fleece/options/school_league.py`

Fixed "control" schools (buyhold, equal-weight) live permanently in the league. Evolution must beat these to earn capital. Prevents drift into garbage while feeling successful.

**Adopt**: In the game, always show Buy & Hold and Fish-only as fixed controls. The player must beat both to have a meaningful residual edge.

### 1.5 Log Score + Brier Score for Probability Assessment

**File**: `/root/fleece/experiments/scoring.py`

```python
def score_decision(decision, realized_return, flat_band=0.001):
    idx = outcome_class(realized_return, flat_band)  # 0=up, 1=flat, 2=down
    p = max(probs[idx], 1e-12)
    log_score = math.log(p)
    brier = sum((a - b) ** 2 for a, b in zip(probs, y)) / 3.0
```

Fleece scores probability assessments across 3 outcomes (up/flat/down), not just binary. Our current Brier score is binary (up/not-up). Adopt the 3-class version.

**Where**: `game_v2.py` calibration scoring

### 1.6 Exponential Forgetting for Hypotheses

**File**: `/root/fleece/fleece/options/tuna_hypothesis.py`

```python
def decay(self, lam=0.95):
    self.alpha *= lam
    self.beta *= lam
```

Old Bayesian evidence fades. Addresses non-stationarity — a stock's regime 6 months ago matters less than today's. Applicable to our ensemble vote memory.

**Where**: Ensemble caching in `run_ensemble.py`, strategy weight adaptation

### 1.7 Content-Hashed Scenario Locking

**File**: `/root/fleece/fleece/options/scenario_arena.py`

Every scenario is content-hashed before any strategy sees it. Prevents retrofitting strategies to known outcomes.

**Adopt**: Our game episodes should content-hash the price data at creation time. `data_hash` field already exists in `GameForecast` — wire it into verification.

### 1.8 CSCV/PBO for Overfit Detection

**File**: `/root/fleece/experiments/deltatuna_lab/analysis.py`

Probability of Backtest Overfitting via Combinatorially Symmetric Cross-Validation. Reports the fraction of combinations where the in-sample-best trial underperforms out-of-sample.

**Adopt**: Run PBO on our 41 strategies. If PBO > 0.5, the ensemble is overfit.

### 1.9 Deflated Sharpe Ratio

**File**: `/root/fleece/experiments/deltatuna_lab/analysis.py`

Bailey & López de Prado (2014) DSR accounts for multiple testing, non-normality, and sample length. We already have this in `judge_v2.py` but it's not wired into the ensemble ranking.

**Adopt**: Replace raw Sharpe ranking in `run_ensemble.py` with DSR ranking.

### 1.10 Vectorized Arena Scoring

**File**: `/root/fleece/fleece/options/arena_vectorized.py`

Instead of looping over strategies × scenarios, build weight matrices per regime and do batch matrix multiplication. ~100x faster.

**Adopt**: For the ensemble backtest, precompute all strategy signals into a matrix, then multiply by regime weights. Eliminates per-day strategy re-evaluation.

---

## Part 2: What Bitt Does That Fish Should Steal

### 2.1 Shrinkage Scoring for Small-N (CRITICAL)

**File**: `/root/bitt/integration/cge/shrinkage_scorer.py`

```python
score = (n * raw_mean + k * prior_mean) / (n + k)
```

When you have 4-15 observations per cell, don't trust the raw mean. Shrink toward the population average. **This directly fixes our ensemble confidence problem** — with only 500 days of data, strategy-level Sharpe estimates are noisy.

**Adopt**: Apply shrinkage to strategy Sharpe scores before ranking:
```python
k = 6  # prior weight
prior_sharpe = 0.5  # population average
shrunk_sharpe = (n * raw_sharpe + k * prior_sharpe) / (n + k)
```

**Where**: `run_ensemble.py` strategy ranking, `backtest_results.json`

### 2.2 Layered Evaluation (Dev / Validation / Secret)

**File**: `/root/bitt/integration/cge/eval/suite.py`

Successive halving across three layers:
1. **Dev**: Quick evaluation for initial filtering
2. **Validation**: Confirmation on separate data
3. **Secret**: Instances generated at eval time, never seen by proposers

**Adopt**: Our walk-forward should use 3 layers:
- Train (252d) → validate (63d) → test (63d, locked)
- The test layer is the "secret" — strategies are selected on train+validate, scored on test

**Where**: `walk_forward.py`, game episode creation

### 2.3 Bootstrap CI for Paired Differences

**File**: `/root/bitt/integration/cge/eval/gates.py`

```python
def bootstrap_ci(deltas, n_boot=2000, alpha=0.05, seed=7):
    means = sorted(statistics.mean(deltas[rng.randrange(len(deltas))] for _ in range(len(deltas)))
                   for _ in range(n_boot))
    return {"lower": means[int(n_boot * alpha / 2)], "upper": means[int(n_boot * (1 - alpha / 2))]}
```

Used for non-inferiority testing — a candidate must not regress more than a margin on any metric. **Adopt for ensemble validation**: new ensemble configurations must not regress on any ticker vs. the current best.

### 2.4 Confidence-Gated Spending

**File**: `/root/bitt/integration/bittensor_gym/oracle/scorer.py`

High-cost decisions require `source_confidence >= 0.95`. Low-confidence assessments don't trigger action.

**Adopt**: In the game, Fish's position sizing should be gated by confidence:
- confidence < 0.3: 0% (no trade)
- confidence 0.3-0.5: 25%
- confidence 0.5-0.7: 50%
- confidence 0.7-0.85: 75%
- confidence > 0.85: 100%

This replaces the current binary FLAT/LONG with proper Kelly-like sizing.

### 2.5 Evolved Scorer Weights

**File**: `/root/bitt/integration/cge/evolve_scorer.py`

The scoring function itself is a parameterized object that can be evolved. Weights like `0.30 * economic + 0.35 * lab_value` are genome parameters, not constants.

**Adopt**: Make ensemble vote weights evolveable. Instead of equal-weight voting, let each strategy's vote weight be a parameter:
```python
GENOME = {
    "momentum_20d_weight": [0.5, 1.0, 1.5, 2.0],
    "trend_20_100_weight": [0.5, 1.0, 1.5, 2.0],
    "rsi_14_weight": [0.5, 1.0, 1.5, 2.0],
    # ...
}
```

### 2.6 Failure Classification with Mutation Prescriptions

**File**: `/root/bitt/cge/feedback_classify.py`

When a strategy is rejected, classify WHY (regime mismatch, parameter drift, overfitting), then prescribe specific mutations. Not just "this failed" but "this failed because X, try Y."

**Adopt**: When a strategy gets a FAIL verdict from Judge, classify the failure mode and suggest which parameters to mutate. Wire into `judge_v2.py` verdict output.

### 2.7 Block-Pinned Immutable Snapshots

**File**: `/root/bitt/oracle/capture.py`

All data captured from a single finalized block. Never re-query. Store the capture, not the query.

**Adopt**: Our game episodes already freeze data at creation via `data_hash`. Extend this — every game step should include a content hash of the input bars, and verification should check the hash before scoring.

### 2.8 Sharpe + Max Drawdown as Terminal Metrics

**File**: `/root/bitt/integration/cge/school/world.py`

```python
return MetricVector(metrics=(
    Metric("total_return", total_return, "max"),
    Metric("sharpe", sharpe, "max"),
    Metric("max_drawdown", -max_dd, "max"),
))
```

Three metrics, not one. Sharpe for risk-adjusted return, MaxDD for tail risk, Total Return for absolute performance. **Adopt**: Our game scoreboard should show all three, not just total return.

---

## Part 3: Prioritized Action Items

### Tier 1 — Do This Week (High Impact, Low Effort)

| # | Action | From | Effort | Impact |
|---|--------|------|--------|--------|
| 1 | Add Wilson intervals to game calibration bins | Fleece | 30min | HIGH |
| 2 | Add PILOT/CONFIRMATORY label to game results (n<30) | Fleece | 15min | HIGH |
| 3 | Add shrinkage scoring to ensemble strategy ranking | Bitt | 30min | HIGH |
| 4 | Gate Fish position sizing by confidence (Kelly-like) | Bitt | 1hr | HIGH |
| 5 | Fix ensemble to seed strategy calls deterministically | Fleece | 30min | HIGH |
| 6 | Add Buy & Hold as immortal control in game scoreboard | Fleece | 15min | MEDIUM |
| 7 | Add Sharpe + MaxDD to game final scores (not just return) | Bitt | 30min | MEDIUM |

### Tier 2 — Do This Month (High Impact, Medium Effort)

| # | Action | From | Effort | Impact |
|---|--------|------|--------|--------|
| 8 | Run CSCV/PBO on 41 strategies to check overfit rate | Fleece | 2hr | HIGH |
| 9 | Replace raw Sharpe with DSR in ensemble ranking | Fleece | 1hr | HIGH |
| 10 | Wire exponential forgetting into ensemble vote memory | Fleece | 1hr | MEDIUM |
| 11 | Build 3-class Brier score (up/flat/down) for game | Fleece | 1hr | MEDIUM |
| 12 | Add bootstrap CI to ensemble confidence intervals | Bitt | 1hr | MEDIUM |
| 13 | Classify Judge failures into structured mutation prescriptions | Bitt | 2hr | MEDIUM |
| 14 | Content-hash verification for game episode data integrity | Fleece | 30min | LOW |

### Tier 3 — Future (Medium Impact, High Effort)

| # | Action | From | Effort | Impact |
|---|--------|------|--------|--------|
| 15 | Vectorize ensemble backtest (matrix multiply instead of loops) | Fleece | 3hr | MEDIUM |
| 16 | Evolve ensemble vote weights via genetic algorithm | Bitt | 4hr | MEDIUM |
| 17 | Build layered eval (train/validate/test) with successive halving | Bitt | 3hr | HIGH |
| 18 | Add non-inferiority testing for ensemble configuration changes | Bitt | 2hr | LOW |

---

## Part 4: Specific Code Changes

### Change 1: Shrinkage scoring in ensemble ranking

**File**: `run_ensemble.py` — `run_ticker()` function

```python
# Current (noisy):
results.sort(key=lambda r: r.sharpe if math.isfinite(r.sharpe) else -999, reverse=True)

# Proposed (shrunk):
prior_sharpe = 0.5
k = 6
for r in results:
    n = max(r.trades_count, 1)
    r.sharpe = (n * r.sharpe + k * prior_sharpe) / (n + k)
results.sort(key=lambda r: r.sharpe, reverse=True)
```

### Change 2: Confidence-gated position sizing

**File**: `fish/services/game_v2.py` — `_compute_ensemble_forecast()`

```python
# Current:
direction = 'LONG' if consensus > 0.6 else ('SHORT' if consensus < 0.4 else 'FLAT')

# Proposed:
confidence = abs(consensus - 0.5) * 2
if confidence < 0.3:
    sizing = 0.0
elif confidence < 0.5:
    sizing = 0.25
elif confidence < 0.7:
    sizing = 0.50
elif confidence < 0.85:
    sizing = 0.75
else:
    sizing = 1.0
direction = 'LONG' if consensus > 0.6 else ('SHORT' if consensus < 0.4 else 'FLAT')
```

### Change 3: Wilson intervals in calibration

**File**: `fish/services/game_v2.py` — `_compute_calibration()`

```python
# Add to each bucket:
from fish.services.stats import wilson
w = wilson(sum(b['actuals']), len(b['actuals']))
result.append({
    'confidence_range': f'{bucket*0.2:.1f}-{(bucket+1)*0.2:.1f}',
    'hit_rate': round(w['center'], 3),
    'ci95': (round(w['ci95'][0], 3), round(w['ci95'][1], 3)),
    'count': len(b['forecasts']),
})
```

### Change 4: PILOT/CONFIRMATORY label

**File**: `fish/services/game_v2.py` — `_finalize_episode()`

```python
n_steps = len([s for s in ep.steps if s.return_next is not None])
ep.status_label = 'CONFIRMATORY' if n_steps >= 30 else 'PILOT'
```

### Change 5: Deterministic strategy seeding

**File**: `fish/services/game_v2.py` — `_compute_ensemble_forecast()`

```python
# Add seed parameter:
def _compute_ensemble_forecast(bars: list[dict], seed: int = 0) -> dict:
    # ...
    for name, fn in all_strats.items():
        try:
            r = fn(prices=prices_fmt, seed=seed + hash(name))
        except TypeError:
            r = fn(prices=prices_fmt)  # Strategies that don't accept seed
```

### Change 6: PBO check on ensemble

**File**: New file `fish/services/overfit_check.py`

```python
def check_pbo(prices: dict, strategies: dict, n_splits: int = 16) -> float:
    """Probability of Backtest Overfitting."""
    # Split into n_splits blocks
    # For each combination of n/2 blocks as train:
    #   Select best strategy on train
    #   Check if it underperforms median on test
    # PBO = fraction of combinations where IS-best underperforms OOS
    ...
```

---

## Part 5: What NOT to Steal

| Pattern | Why Not |
|---------|---------|
| Fleece's Thompson Sampling for allocation | Overkill for 15 stocks. Kelly sizing is enough. |
| Bitt's world simulation framework | Too abstract. Fish has real price data, no need to simulate worlds. |
| Fleece's MAP-Elites quality-diversity pruning | We have 41 strategies, not thousands. Simple ranking works. |
| Bitt's evolved scorer weights | premature optimization. Fix the game first, then optimize. |
| Fleece's Orca meta-controller | Not needed until we have 100+ strategies. |
| Bitt's block-pinned blockchain capture | We're not on-chain. Content hashing is sufficient. |

---

## Part 6: North Star for the Game

Both repos converge on the same insight: **the scoring function is more important than the strategy**.

Fleece evolves the scorer weights. Bitt evolves the scorer parameters. Both use Wilson intervals and shrinkage to prevent false discoveries at small N.

Fish's game should do the same. The player isn't just playing against Fish's strategies — they're playing against Fish's **scoring function**. If the scoring function is wrong (fake stats, wrong metrics, no calibration), the game teaches nothing.

The correct north star from this review:

> **The game's statistical discipline must be strong enough that a player who beats Fish for 30 rounds has genuinely discovered a residual edge, not just gotten lucky against a broken benchmark.**

Every pattern in this document serves that goal.

---

## Appendix: Key File References

### Fleece
| Pattern | File | Lines |
|---------|------|-------|
| Deterministic backtest | `/root/fleece/experiments/deltatuna_lab/runner.py` | 1-100 |
| Wilson intervals | `/root/fleece/fleece/core/stats.py` | 1-60 |
| Pilot/confirmatory | `/root/fleece/fleece/core/stats.py` | 55-60 |
| Immortal controls | `/root/fleece/fleece/options/school_league.py` | 1-50 |
| Decision scoring | `/root/fleece/experiments/scoring.py` | 1-80 |
| Exponential forgetting | `/root/fleece/fleece/options/tuna_hypothesis.py` | 1-50 |
| Content hashing | `/root/fleece/fleece/options/scenario_arena.py` | 1-30 |
| CSCV/PBO | `/root/fleece/experiments/deltatuna_lab/analysis.py` | 200-296 |
| Deflated Sharpe | `/root/fleece/experiments/deltatuna_lab/analysis.py` | 100-150 |
| Vectorized arena | `/root/fleece/fleece/options/arena_vectorized.py` | 1-80 |

### Bitt
| Pattern | File | Lines |
|---------|------|-------|
| Shrinkage scoring | `/root/bitt/integration/cge/shrinkage_scorer.py` | 1-39 |
| Layered evaluation | `/root/bitt/integration/cge/eval/suite.py` | 1-81 |
| Bootstrap CI | `/root/bitt/integration/cge/eval/gates.py` | 74-92 |
| Confidence-gated | `/root/bitt/integration/bittensor_gym/oracle/scorer.py` | 150-170 |
| Evolved scorer | `/root/bitt/integration/cge/evolve_scorer.py` | 1-244 |
| Failure classification | `/root/bitt/cge/feedback_classify.py` | 196-258 |
| Sharpe+MaxDD scoring | `/root/bitt/integration/cge/school/world.py` | 1-60 |
| Block-pinned capture | `/root/bitt/oracle/capture.py` | 1-50 |
