# Avatar Backtest Northstar — Fish Quantitative Laboratory

**Saved**: 2026-09-10T16:00:00Z
**Source**: Peer review of Fish backtest material against quant literature
**Status**: Active reference for A-task breakdown

---

## The Core Problem

**Fish does not yet have a financial backtest.** What exists is a prediction→evidence validation experiment: 258 predictions, only 3 connected to later evidence. That is interesting for Feedify, but cannot establish tradable alpha.

The next version must be less about adding exotic ML and more about building a **proper experimental laboratory where hundreds of avatars can fail safely**.

---

## Three Outcomes Per Event

Every Fish event needs three distinct outcomes:

```
CLAIM OUTCOME
Did prediction become true?

INFORMATION OUTCOME
Did it contain information not already priced?

TRADING OUTCOME
Could Fish have made money from it?
```

This distinction prevents false discovery.

---

## The 23 Principles

### Principle 1: Test Ideas, Not Just Trades
Current result: "researcher predicts X → later evidence supports X" doesn't establish:
- E[r_stock,t+h | X] > E[r_stock,t+h]
- E[r_net_strategy] > 0 after spread, commissions, slippage, impact, opportunity cost

### Principle 2: Sample Size Matters
258 predictions with 3 resolved observations cannot support inference. Need to freeze all predictions at T, wait/fetch complete future interval, evaluate ALL including where nothing happened.

### Principle 3: Start With 30 Dumb Baselines
Before AlphaGen, transformers, LLMs or RL:
- Buy & Hold
- Momentum: 20d, 60d, 120d, 252d, 12-1 month
- Trend: 10/50, 20/100, 50/200, Donchian 20, Donchian 55
- Reversal: 1d, 5d, 20d, RSI, Bollinger, residual reversal
- Volatility: vol-target momentum, low-vol, breakout × vol
- Relative: stock vs sector momentum, stock vs market momentum, industry momentum
- Fundamental: value, quality, profitability
- Events: earnings surprise, earnings gap, insider purchase

If an elaborate agent cannot beat these, it dies.

### Principle 4: Cross-Sectional Avatars (JKP)
Don't ask "is COHR's P/E low?" Ask "where should COHR rank among comparable stocks?"
- 🦅 Value, 🏰 Quality, 🚀 Momentum, 🐌 Low Investment
- 💰 Profitability, 🧊 Low Risk, 🪶 Size, 💧 Liquidity, 🧮 Composite

### Principle 5: Residual Strategies (Fox)
Trade properties of ε_t (residuals after removing market/sector exposure) rather than raw price.
- Market-neutral residual momentum
- Sector-neutral momentum
- Residual reversal
- Pairs, cointegration, PCA residuals, factor residuals

### Principle 6: Earnings Avatars (Shark Family)
Don't encode PEAD = true. Create competing hypotheses:
- 🦈 Shark-SUE (earnings surprise)
- 🦈 Shark-Gap (announcement return)
- 🦈 Shark-Revision (analyst revisions)
- 🦈 Shark-Volume (earnings × abnormal volume)
- 🦈 Shark-Retail (earnings × retail pressure)
- 🦈 Shark-Liquidity (earnings × liquidity)
- 🦈 Shark-Expectation (surprise relative to expected-return state)

### Principle 7: Liquidity First-Class State
Every Fish state should include:
- spread, ADV, dollar volume, Amihud illiquidity, turnover
- realized volatility, gap risk, expected impact, participation rate

Every backtest result needs:
PnL_net = PnL_gross - spread - fees - slippage - impact

### Principle 8: Experiment Ledger
Every mutation recorded:
- experiment_id, parent_id, hypothesis, ticker, parameters, features
- training period, validation period, result
- INCLUDING FAILURES. Never delete experiments.

### Principle 9: Judge Avatar (Statistical Prosecutor)
Judge never trades. Judge's only purpose is to destroy strategies.
Outputs: PASS, WARN, FAIL
- Sharpe, Sortino, Calmar, max DD, turnover
- PSR, DSR, PBO
- Bootstrap CI, permutation p-value
- Cost sensitivity, parameter sensitivity, start-date sensitivity
- Regime stability, cross-stock stability, cross-sector stability

### Principle 10: Train/Test/Lockbox/Paper Architecture
```
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
```

### Principle 11: Point-in-Time Universe Reconstruction
Backtest using only securities actually investable on that date. Include delisted companies, bankruptcies, acquisitions, ticker changes, historical index membership, historical fundamentals as published.

### Principle 12: Information Timestamps
Mandatory at schema level:
- event_time, published_time, received_time, processed_time, tradable_time

### Principle 13: Feedify Event Study
For every graph event compute abnormal returns:
AR_i,t = r_i,t - β_i × r_benchmark,t
CAR_i,[0,h] = Σ AR_i,t
Measure at 1d, 5d, 20d, 60d, 120d, 252d

### Principle 14: Randomized Controls
Compare against random companies, random dates, same-sector, same-size, same-momentum, random posts, low-alpha posts.

### Principle 15: Disagreement Avatar
Alpha can arise from disagreement. Measure Var(P_agents) across quant models, researchers, analysts, options market, momentum, fundamentals.

### Principle 16: Options-Implied Information
For stocks with liquid options:
- ATM IV, term structure, skew, put/call skew, IV - realized vol
- Earnings implied move, open interest, volume, delta-adjusted option flow

### Principle 17: Volatility Strategies (Hedgehog)
Historical vol, EWMA, GARCH, HAR-RV, range estimators, realized vol, ML vol forecast, event-conditioned vol.

### Principle 18: Competing Regime Models
HMM, change-point detection, vol regimes, trend/dispersion regimes, macro regimes, liquidity regimes, correlation regimes, learned embeddings.

### Principle 19: Online Learning
EWA, Hedge algorithm, online gradient descent, Bayesian model averaging, Thompson sampling, contextual bandits.

### Principle 20: Ensemble Objective
Utility = E[R] - λσ - γDD - ηTurnover - κCosts - ρCorrelationWithExisting

### Principle 21: Strategy Uniqueness
Behavioral fingerprint: market beta, sector beta, momentum beta, value beta, quality beta, vol beta, average horizon, turnover, drawdown profile, regime performance, event exposure.

### Principle 22: Known-Factor Residual Gate
For candidate S:
r_S = α + Σ β_k r_k + ε
Display both Raw Sharpe and Residual Sharpe after removing known factor exposure.

### Principle 23: Every Famous Strategy Is Falsifiable
Treat every famous strategy as a falsifiable avatar, not gospel.

---

## Priority Order

| Priority | Addition | Why |
|----------|----------|-----|
| **P0** | Point-in-time data + immutable experiment ledger | Everything else is invalid without it |
| **P0** | Judge: DSR/PBO/permutation/walk-forward | Prevent autonomous overfitting |
| **P0** | 30-50 dumb baseline strategies | Establish difficulty |
| **P1** | Cross-sectional JKP factor avatars | Huge missing strategy class |
| **P1** | Residual/sector-neutral Fox | Particularly relevant to Fish stocks |
| **P1** | Proper earnings/event avatars | Strong literature + lots of observations |
| **P1** | Learned strategy ensemble | Turns avatars into actual system |
| **P2** | Feedify event-study engine | Tests genuinely differentiated data |
| **P2** | Options avatar | Independent market expectations |
| **P2** | Online-learning ensemble | Adaptive weighting |
| **P2** | AlphaGen/RD-Agent strategy mutation | Automated discovery |
| **P3** | LOB/microstructure | Only for sufficiently liquid stocks |
| **P3** | RL/deep MoE/TS foundation models | Earn complexity only after baselines |

---

## The Key Insight

The biggest missing primitive isn't another strategy. It's **scientific governance of the search process**. Once autonomous agents can generate thousands of avatars, Fish's competitive advantage becomes its ability to:
- Remember every experiment
- Prevent information leakage
- Punish multiple testing
- Model execution
- Identify duplicated exposures
- Maintain a genuinely untouched lockbox

Then unleash AlphaGen/RD-Agent. Judge is harder to fool than the strategy generator is clever.
