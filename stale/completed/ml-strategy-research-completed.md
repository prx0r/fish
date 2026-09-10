# Dev Plan 9: Advanced Quant Strategy Architecture

**Date**: 2026-09-10
**Source**: Deep research on financial ML, arXiv papers, institutional datasets

---

## The Core Insight

The current avatar layer is too coarse. Avatars should be **persistent, testable strategy organisms** — each owning a hypothesis class, feature set, model family, horizon, regime preference, and learned parameters.

**Fish should contain a strategy ecology, not 10 fixed strategies.**

---

## A-Task Breakdown

### Phase 1: Strategy Zoo (100 transparent strategies)

| # | Task | Family | Strategies | Validation |
|---|------|--------|------------|------------|
| A61 | Build trend/momentum strategies | Bull | TSMOM 1/3/6/12m, EMA 10/30, MA 50/200, Donchian, ADX, residual momentum | Each must backtest on 19 positions |
| A62 | Build mean reversion strategies | Bear | z-score, Bollinger, RSI, OU process, Kalman filter | Each must backtest on 19 positions |
| A63 | Build cross-sectional factors | Eagle | momentum, value, quality, profitability, earnings revisions | Each must backtest on 19 positions |
| A64 | Build behavioral reversal strategies | Snake | short-term reversal, sentiment extremes, crowding | Each must backtest on 19 positions |
| A65 | Build ensemble/meta strategies | Wolf | Bayesian averaging, stacking, mixture-of-experts | Each must backtest on 19 positions |
| A66 | Build volatility strategies | Bee | Kelly variants, vol targeting, risk parity | Each must backtest on 19 positions |
| A67 | Build event-driven strategies | Shark | earnings, Form 4, abnormal volume | Each must backtest on 19 positions |
| A68 | Build factor allocation strategies | Owl | quality, profitability, momentum/value blends | Each must backtest on 19 positions |
| A69 | Build microstructure strategies | Cheetah | order imbalance, short-term reversal | Each must backtest on 19 positions |
| A70 | Build structural strategies | Turtle | fundamental growth, technological bottleneck | Each must backtest on 19 positions |

### Phase 2: Stock × Avatar × Regime

| # | Task | What | Validation |
|---|------|------|------------|
| A71 | Build AvatarInstance dataclass | ticker, avatar, strategy_id, horizon, features, model, regime, confidence | Must serialize to JSON |
| A72 | Train stock-specific populations | For each of 19 positions, train 20-50 avatars | Each avatar must backtest independently |
| A73 | Build regime detector | Bull/Bear/Range from VIX, rates, sector state | Must classify 2024-2026 correctly |
| A74 | Build meta-ensemble | Learn weights w_j = g(strategy, regime, recent_performance, stock) | Must outperform equal-weight |

### Phase 3: Cross-Sectional Training

| # | Task | What | Validation |
|---|------|------|------------|
| A75 | Fetch US equity universe data | 1995-2024 train, 2025 val, 2026 test | Must have 100K+ stock-months |
| A76 | Train generic model | Learn r_{i,t+h} = f(X_{i,t}, X_{market,t}, id_i) | Must outperform random |
| A77 | Fine-tune for Fish positions | Condition on 19 specific tickers | Must outperform generic |

### Phase 4: Factor Sanity Checking

| # | Task | What | Validation |
|---|------|------|------------|
| A78 | Fetch JRP Global Factors | 153 characteristics, 93 countries | Must load without errors |
| A79 | Regress strategies against factors | Each avatar's Sharpe → residual after known factors | Residual Sharpe must be positive |
| A80 | Build factor zoo comparison | For each strategy: what % of return is known factor exposure? | Must show residual alpha |

### Phase 5: Anti-Overfitting Infrastructure

| # | Task | What | Validation |
|---|------|------|------------|
| A81 | Implement Deflated Sharpe Ratio | Correct for multiple testing | Must reduce naive Sharpe |
| A82 | Implement CSCV/PBO | Estimate probability of overfitting | Must output P(overfit) |
| A83 | Implement walk-forward validation | Train 2yr, test 6mo, roll forward | Must show different train/test |
| A84 | Implement Monte Carlo perturbation | Block bootstrap, parameter perturbation | Must show confidence intervals |
| A85 | Build adversarial validation suite | +2x costs, +1 bar latency, missing data | Each test must pass or strategy dies |

### Phase 6: Meta-Labeling

| # | Task | What | Validation |
|---|------|------|------------|
| A86 | Build meta-label model | P(strategy correct \| state) for each avatar | Must outperform random |
| A87 | Wire meta-model to execution | Use meta-model to size positions | Must reduce drawdown |
| A88 | Build regime-conditional ensemble | Different weights per regime | Must outperform static weights |

---

## How This Turns Into Deterministic A-Tasks

The original prompt was: "build avatars, backtest on 19 stocks, use advanced ML"

I turned it into deterministic tasks by:

1. **Decomposed by family** — Each avatar family (Bear, Bull, etc.) becomes 15-25 specific strategies with known implementations
2. **Decomposed by validation** — Each strategy must pass: backtest → factor orthogonality → walk-forward → Monte Carlo → adversarial tests
3. **Decomposed by layer** — Strategy zoo → stock-specific populations → meta-ensemble → execution
4. **Made each task testable** — "Each must backtest on 19 positions" is binary pass/fail
5. **Sequenced by dependency** — Can't build meta-ensemble until you have strategies to ensemble

The key insight: **don't build "a trading system." Build 100 strategies, then let data decide which survive.**
