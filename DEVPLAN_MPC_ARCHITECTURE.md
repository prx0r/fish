# Fish Development Plan — MPC/Stochastic Control Architecture

**Saved**: 2026-09-10T20:00:00Z
**Status**: Active reference for next development phase
**Based on**: Peer review + 10 research papers + MPC vision

---

## The Vision

Fish is not a buy/sell signal generator. It is a **continually replanned probabilistic policy over future portfolio states**.

For each stock, Fish maintains a rolling one-year distribution over possible future paths, evaluates many candidate buy/sell sequences across those paths, chooses the sequence with the highest expected risk-adjusted utility, executes only the near-term action, then recompute everything as new information arrives.

This is **model predictive control (MPC) / receding-horizon stochastic control**, with Monte Carlo or generative models supplying the future scenarios.

---

## The Core Loop

```
OBSERVE → INFER DISTRIBUTION → SIMULATE FUTURES → OPTIMIZE SEQUENCE → SIZE BY UNCERTAINTY → EXECUTE FIRST ACTION → OBSERVE AGAIN
```

Mathematically:

```
s_t = everything known now
p(s_{t+1:t+H} | s_t)  # H = 252 days (1 year)

a* = argmax_a E[
  PnL(a)
  - λ Risk(a)
  - γ Drawdown(a)
  - η Costs(a)
]

Execute only a_t, then replan.
```

---

## What We Built Today

### Completed (P0)

| Component | File | Status |
|-----------|------|--------|
| **Equity Curve** | `equity.py` | ✅ Canonical strategy returns |
| **Judge v2** | `judge_v2.py` | ✅ All 12 bugs fixed |
| **Baselines** | `baselines.py` | ✅ 23 dumb strategies |
| **Fox** | `fox.py` | ✅ 3 residual strategies |
| **Shark** | `shark.py` | ✅ 5 earnings strategies |
| **Hedgehog** | `hedgehog.py` | ✅ 5 volatility strategies |
| **Wolf** | `wolf.py` | ✅ 5 regime strategies |
| **Experiment Ledger** | `experiment_ledger.py` | ✅ Immutable record |
| **Walk-Forward** | `walk_forward.py` | ✅ Train/Test architecture |
| **Liquidity** | `liquidity.py` | ✅ First-class state |
| **Online Ensemble** | `online_ensemble.py` | ✅ Adaptive weighting |
| **Mutation Engine** | `mutation.py` | ✅ Genetic programming |
| **Northstar** | `AVATAR_BACKTEST_NORTHSTAR.md` | ✅ 23 principles |

### In Progress (P1)

| Component | File | Status |
|-----------|------|--------|
| **Strategy Uniqueness** | `ensemble.py` | ⚠️ Needs return-based correlation |
| **PBO** | `judge_v2.py` | ⚠️ Cross-strategy CSCV working |
| **Permutation Test** | `judge_v2.py` | ⚠️ Signal-based, needs validation |

### Not Started (P2) — The MPC Vision

| Component | Description | Priority |
|-----------|-------------|----------|
| **State Model** | World state representation | P2 |
| **Scenario Engine** | Generate plausible futures | P2 |
| **Policy Optimizer** | Find optimal allocation sequence | P2 |
| **MPC Planner** | Receding-horizon control | P2 |
| **Calibration** | Conformal prediction intervals | P2 |
| **Diffusion World Model** | Generative future scenarios | P3 |

---

## The 12 Fixes (Completed)

| # | Bug | Fix | File |
|---|-----|-----|------|
| 1 | Judge scored stock returns | Strategy equity curve | `equity.py` |
| 2 | StrategyResult used closes | Canonical positions/returns | `equity.py` |
| 3 | Cost sensitivity wrong | Real trade-based costs | `equity.py` |
| 4 | Skewness/kurtosis wrong | Standardized moments | `equity.py` |
| 5 | Permutation test broken | Shuffles signals, not returns | `judge_v2.py` |
| 6 | PBO wasn't CSCV | Cross-strategy matrix | `judge_v2.py` |
| 7 | Overlapping OOS windows | Non-overlapping stitched | `walk_forward.py` |
| 8 | No train/freeze/test | Signal factories | `equity.py` |
| 9 | Uniqueness fictional | Return correlation | `ensemble.py` |
| 10 | DSR too punitive | Effective independent trials | `judge_v2.py` |
| 11 | Exceptions swallowed | Ledger failure logging | `judge_v2.py` |
| 12 | No unit tests | Known-answer tests | `tests/` |

---

## Unit Tests Passed

```
Test 1: Flat strategy → Sharpe = 0.0 ✓
Test 2: Buy-and-hold → Strategy returns ≈ stock returns ✓
Test 3: Judge uses strategy returns ✓
Test 4: Different strategies get different metrics ✓
```

---

## Chris Prior Portfolio Analysis (Validated)

| Stock | Best Strategy | Sharpe | Verdict |
|-------|--------------|--------|---------|
| TSLA | buyhold | 3.85 | PASS |
| COHR | buyhold | 4.46 | PASS |
| COHR | reversal_20d | 3.75 | WARN |
| NBIS | buyhold | 1.75 | PASS |
| META | buyhold | 3.82 | WARN |
| MPAL | All strategies | <1.3 | FAIL |
| BT.A | rsi_14 | 2.56 | WARN |
| TSCO | buyhold | 2.92 | WARN |

**Key insight**: Strategies that add value (momentum, reversal) now get different verdicts than strategies that don't.

---

## Rebalancing Recommendations (Validated)

| Action | Count | Positions |
|--------|-------|-----------|
| HOLD | 11 | AJGII, COHR, COLL, INEYI, MAN, META, NBIS, IAG, TSCO, JDW |
| REDUCE | 2 | MPAL (FAIL), TSLA (oversized 30.2%) |
| SELL | 6 | ACCO, DHX, IRWD, PBI, PGEN, BT.A |

---

## Next Phase: MPC Architecture

### Phase 1: State Model

```python
# fish/services/sequence/state.py

@dataclass
class WorldState:
    """Complete world state at time t."""
    ticker: str
    date: str
    
    # Price state
    price: float
    returns_1d: float
    returns_5d: float
    returns_20d: float
    returns_60d: float
    
    # Volatility state
    vol_20d: float
    vol_60d: float
    vol_regime: str  # "low", "mid", "high"
    
    # Momentum state
    momentum_20d: float
    momentum_60d: float
    momentum_120d: float
    
    # Regime state
    ma_regime: str  # "bull", "bear"
    trend_strength: float
    
    # Liquidity state
    adv: float
    spread_bps: float
    liquidity_tier: str
    
    # Avatar signals
    avatar_signals: dict[str, float]  # {avatar_name: signal}
    
    # External state
    spy_return: float
    sector_return: float
    vix: float
    rates: float
```

### Phase 2: Scenario Engine

```python
# fish/services/sequence/scenario_model.py

class ScenarioEngine:
    """Generate plausible future world trajectories."""
    
    def generate_scenarios(
        self,
        state: WorldState,
        n_scenarios: int = 10000,
        horizon: int = 252,
    ) -> list[list[WorldState]]:
        """Generate n_scenarios possible futures of length horizon."""
        
        # Method 1: Block bootstrap (simplest)
        # Method 2: Regime-conditioned bootstrap
        # Method 3: VAR/factor state-space
        # Method 4: Gaussian process
        # Method 5: Diffusion world model
        pass
```

### Phase 3: Policy Optimizer

```python
# fish/services/sequence/optimizer.py

class PolicyOptimizer:
    """Find optimal allocation sequence across scenarios."""
    
    def optimize(
        self,
        scenarios: list[list[WorldState]],
        current_weight: float,
        risk_aversion: float = 1.0,
        turnover_penalty: float = 0.001,
    ) -> list[dict]:
        """Return optimal weight sequence."""
        
        # Objective:
        # max E[PnL] - λ*Var(PnL) - γ*CVaR - η*Turnover
        
        # Output:
        # [
        #   {"day": 0, "weight": 0.14, "confidence": 0.73},
        #   {"day": 20, "weight": 0.18, "confidence": 0.66},
        #   {"day": 60, "weight": 0.23, "confidence": 0.54},
        #   {"day": 120, "weight": 0.17, "confidence": 0.39},
        #   {"day": 252, "weight": 0.09, "confidence": 0.19},
        # ]
        pass
```

### Phase 4: MPC Planner

```python
# fish/services/sequence/planner.py

class MPCPlanner:
    """Receding-horizon stochastic control."""
    
    def plan(
        self,
        state: WorldState,
        current_weight: float,
    ) -> dict:
        """Generate sequence, execute first action, then recompute."""
        
        # 1. Generate scenarios
        scenarios = self.scenario_engine.generate_scenarios(state)
        
        # 2. Optimize policy
        policy = self.optimizer.optimize(scenarios, current_weight)
        
        # 3. Return sequence with confidence decay
        return {
            "ticker": state.ticker,
            "as_of": state.date,
            "current_weight": current_weight,
            "optimal_weight": policy[0]["weight"],
            "confidence": policy[0]["confidence"],
            "sequence": policy,
            "distribution": self._compute_distribution(scenarios),
        }
```

### Phase 5: Calibration

```python
# fish/services/sequence/calibration.py

class CalibrationEngine:
    """Conformal prediction + recalibration."""
    
    def calibrate(
        self,
        predictions: list[float],
        actuals: list[float],
    ) -> dict:
        """Check and recalibrate prediction intervals."""
        
        # Track: did 80% intervals contain reality 80% of the time?
        # If not, recalibrate downward automatically.
        pass
```

---

## The Sequence Endpoint

```json
GET /api/portfolio/{ticker}/sequence

{
  "ticker": "COHR",
  "as_of": "2026-09-10",
  "current_weight": 0.08,
  "optimal_weight": 0.14,
  "confidence": 0.73,

  "sequence": [
    {"horizon_days": 0, "target_weight": 0.14, "action": "BUY", "delta_weight": 0.06, "confidence": 0.73},
    {"horizon_days": 20, "target_weight": 0.18, "confidence": 0.66},
    {"horizon_days": 60, "target_weight": 0.23, "confidence": 0.54},
    {"horizon_days": 120, "target_weight": 0.17, "confidence": 0.39},
    {"horizon_days": 252, "target_weight": 0.09, "confidence": 0.19}
  ],

  "distribution": {
    "p_profit": 0.72,
    "expected_return": 0.21,
    "median_return": 0.17,
    "p05": -0.24,
    "p95": 0.68,
    "expected_drawdown": -0.16
  }
}
```

---

## Scenario Engine Progression

| Version | Method | Complexity | Value |
|---------|--------|------------|-------|
| v0.1 | Block bootstrap | Low | Baseline |
| v0.2 | Regime-conditioned bootstrap | Low | Better scenarios |
| v0.3 | VAR/factor state-space | Medium | Factor-aware |
| v0.4 | Gaussian process | Medium | Probabilistic |
| v0.5 | Diffusion world model | High | Generative |
| v0.6 | Avatar ensemble | High | Multi-expert |
| v0.7 | Feedify/SEC/options-conditioned | High | Full state |

**Key principle**: Keep the same optimizer and benchmark protocol. Then you'll know whether a fancy generative world model actually adds economic value.

---

## Confidence = Statistically Precise Uncertainty

Avoid: `confidence = 82` (LLM said so).

Fish should expose:

### 1. Aleatoric uncertainty
The market is intrinsically unpredictable.
```
Var(Y|X)
```

### 2. Epistemic uncertainty
Fish hasn't learned enough.
```
Var_θ[E(Y|X,θ)]
```

### 3. Model disagreement
Avatars disagree.
```
Var_j(ŷ_j)
```

### 4. Distribution-shift uncertainty
Today's state looks unlike training data.

### 5. Forecast-horizon uncertainty
One week is much easier than one year.

```json
{
  "forecast_confidence": 0.76,
  "model_agreement": 0.84,
  "in_distribution_score": 0.91,
  "regime_confidence": 0.62,
  "data_freshness": 0.98,
  "overall": 0.73
}
```

---

## Conformal Prediction on Top

```json
{
  "20_day_return": {
    "median": 0.042,
    "interval_50": [-0.01, 0.09],
    "interval_80": [-0.08, 0.17],
    "interval_95": [-0.20, 0.31]
  }
}
```

Then track: did 80% intervals actually contain reality ≈ 80% of the time?
If not: **confidence gets recalibrated downward automatically.**

---

## Avatars Become Scenario-Conditioned Policy Experts

Don't have Bull say simply: `BUY`

Have Bull produce: `π_Bull(a|s)`

Bear: `π_Bear(a|s)`

Shark: `π_Shark(a|s)`

For each simulated future world, see how each avatar behaves:

```
SIMULATED WORLD #82,193

today          COHR 100
day 34         COHR 113
day 71         COHR 95
day 150        COHR 141
day 252        COHR 173

Bull:   BUY → HOLD → HOLD → HOLD
Bear:   HOLD → SELL → BUY → SELL
Shark:  BUY → SELL → BUY → HOLD
Fox:    HOLD → SELL → BUY → HOLD
```

Run each through many worlds. Eventually learn:

```
P(avatar profitable | s_t)
```

Then the meta-policy blends them.

---

## The Final Architecture

```
                 OBSERVED STATE
                       │
                       ▼
             TEMPORAL REPRESENTATION
                       │
           ┌───────────┴─────────────┐
           │                         │
     deterministic              generative
     predictors                 world model
                                   │
                                   ▼
                          diffusion scenario model
                                   │
                   ┌───────────────┼───────────────┐
                   ▼               ▼               ▼
                future 1        future 2        future N
                   │               │               │
                   └───────────────┼───────────────┘
                                   ▼
                           AVATAR POLICIES
                                   │
                                   ▼
                      STOCHASTIC OPTIMIZER
                                   │
                                   ▼
                [14%, 18%, 23%, 17%, 9%, ...]
                                   │
                                   ▼
                        EXECUTE FIRST STEP
                                   │
                            new observation
                                   │
                                   └────────── ↺
```

---

## Build Order

| Priority | Component | Why |
|----------|-----------|-----|
| **P0** | State model | Everything depends on this |
| **P0** | Block bootstrap scenarios | Baseline scenario engine |
| **P0** | Policy optimizer | Core MPC component |
| **P0** | MPC planner | The main loop |
| **P1** | Regime-conditioned bootstrap | Better scenarios |
| **P1** | Calibration engine | Conformal prediction |
| **P1** | Avatar ensemble blending | Multi-expert |
| **P2** | VAR/factor state-space | Factor-aware |
| **P2** | Gaussian process scenarios | Probabilistic |
| **P2** | Diffusion world model | Generative |
| **P3** | Feedify/SEC/options conditioning | Full state |

---

## Known-Answer Tests for MPC

```
Test 1: Flat world → optimal policy = buy-and-hold
Test 2: Guaranteed +50% → optimal = 100% allocation
Test 3: Guaranteed -50% → optimal = 0% allocation
Test 4: 50/50 +50%/-50% → optimal = risk-adjusted
Test 5: High uncertainty → optimal = small position
Test 6: Transaction costs > alpha → optimal = hold
Test 7: Regime change → optimal adjusts
Test 8: Conformal intervals → 80% coverage
```

---

## The One Sentence

> **Fish is a continually replanned probabilistic policy over future portfolio states, using model predictive control with Monte Carlo scenario generation, avatar ensemble policies, and conformal calibration.**

---

## References

| Paper | Relevance |
|-------|-----------|
| MPC for Trade Execution (2026) | Receding-horizon structure |
| Score-based Diffusion for Portfolio (2025) | Generative world model |
| FinFlowRL (2025) | Action sequences, imitation+RL |
| ProbFM (2026) | Aleatoric/epistemic decomposition |
| Conformal Prediction for Time Series (2026) | Calibrated intervals |
| One-Shot Stochastic Trajectory Optimization (2025) | Whole-path optimization |
| Adaptive-Robust Portfolio (2025) | Model misspecification |
| Learning-Based Portfolio Policies (2026) | Distributional stability |
| Diffusion Models in Finance Survey (2026) | Full landscape |
| Diffolio (2025) | Multivariate probabilistic forecasts |
