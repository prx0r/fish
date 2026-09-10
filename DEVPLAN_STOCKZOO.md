# StockZoo.app — Hierarchical Probabilistic World Model with Receding-Horizon Portfolio Control

**Saved**: 2026-09-10T22:00:00Z
**Status**: Active reference
**Codename**: Fish / StockZoo

---

## The One Sentence

> **Fish is a hierarchical probabilistic world model with receding-horizon portfolio control, where Sequence is the policy it exposes to the user.**

Monte Carlo is only one mechanism for sampling the futures; the real conceptual core is **probabilistic forecasting + stochastic MPC + continuous Bayesian/recalibrated updating**.

---

## The Architecture

### Three Nested World Models

```
MACRO WORLD MODEL
months → years
rates, inflation, growth, technology, sector, fundamentals, Feedify

MARKET WORLD MODEL
days → months
price, volume, factor state, earnings, options, analyst revisions, flows

MICROSTRUCTURE WORLD MODEL
milliseconds → days
book, OFI, trades, queues, spreads, liquidity
```

Then:

```
P(S_future | S_today)
```

is hierarchical. Sequence asks all three.

### The Core Loop

```
OBSERVE → INFER DISTRIBUTION → SIMULATE FUTURES → OPTIMIZE SEQUENCE → SIZE BY UNCERTAINTY → EXECUTE FIRST ACTION → OBSERVE AGAIN
```

### The Time-Scale Hierarchy

```
Turtle / Eagle
months → years
fundamentals, technology, Feedify, macro

Bull / Bear / Shark
days → months
price, earnings, momentum, revisions

Wolf
hours → weeks
regime, volatility, cross-asset

Mantis
milliseconds → hours
LOB, order flow, microprice, execution
```

---

## The Key Insight

Do **not** train Fish to predict this:

```
COHR price in 3 months = $127
```

Train it to predict distributions over multiple horizons:

```
               1d       5d       20d      60d      252d

expected       +0.2%     +1.0%     +4%      +11%      +24%
median         +0.1%     +0.7%     +3%       +8%      +18%

P(up)           54%       59%       66%       70%       68%

q05             -4%      -10%      -19%      -34%      -55%
q95             +5%      +12%      +25%      +51%      +96%
```

Then Fish solves:

```
w*_t:t+H = argmax_w E[U(w, future worlds)]
```

And only executes today's w_t. Tomorrow it solves again.

---

## The Four Avatars

### Turtle / Eagle — Structural (months → years)
- Fundamentals
- Technology
- Feedify signals
- Macro regime

### Bull / Bear / Shark — Tactical (days → months)
- Price momentum
- Earnings
- Analyst revisions
- Factor state

### Wolf — Regime (hours → weeks)
- Volatility regime
- Cross-asset correlation
- Macro regime

### Mantis — Microstructure (milliseconds → hours)
- Order book
- Order flow
- Microprice
- Execution timing

---

## Mantis — The New Avatar

### Inputs

```
spread
microprice
L1 imbalance
L5 imbalance
L10 imbalance
OFI
MLOFI
trade imbalance
aggressor flow
depth slope
depth convexity
cancel/add ratios
queue age
wall persistence
volume bursts
realized vol
```

### Outputs

```
P(ΔMidPrice_1s > 0)
P(ΔMidPrice_10s > 0)
P(ΔMidPrice_1m > 0)

expected move
expected spread
fill probability
execution confidence
```

### Job

Mantis shouldn't decide whether COHR is attractive for six months.

Its job is: **Given that Turtle/Bull/Shark want to buy COHR, when exactly should we execute?**

---

## Order Book Features

### Order-book imbalance

```
OBI_k = (ΣBidSize_1:k - ΣAskSize_1:k) / (ΣBidSize + ΣAskSize)
```

for L1, L1-3, L1-5, L1-10.

### Microprice

```
MicroPrice = (Ask·BidSize + Bid·AskSize) / (BidSize + AskSize)
```

### Multi-level OFI

```
new bids, cancelled bids
new asks, cancelled asks
executed buys, executed sells
```

at every level.

### Wall features

```
wall_age
wall_distance_from_mid
wall_size / normal_depth
wall_size / ADV
wall_survival_probability
fraction_cancelled_as_price_approaches
fraction_executed
repeat_replenishment
queue_position
movement_of_wall
```

---

## Sequence UI

```
                  ─── optimistic 10%
               ╱
          ────
       ╱       ╲
──────            ─ median
       ╲
         ─────
               ╲
                  ─── pessimistic 10%

TODAY       1M       3M       6M       1Y

      ▲ BUY 5%
                       ▼ SELL 4%
                                 ▲ BUY 2%

CURRENT TARGET       14.2%
ACTUAL POSITION       8.1%
ACTION                BUY 6.1%

Confidence            74%

Why:
+ structural model    87%
+ earnings model      72%
+ factor model        68%
- order flow          41%

Preferred execution:
limit 98.20           3%
limit 97.40           2%
reserve                1%
```

---

## Sequence API Response

```json
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
  },

  "why": {
    "structural": 0.87,
    "tactical": 0.72,
    "factor": 0.68,
    "microstructure": 0.41
  },

  "execution": {
    "preferred": [
      {"limit": 99.70, "size_pct": 3, "fill_prob": 0.71},
      {"limit": 99.15, "size_pct": 2, "fill_prob": 0.51},
      {"limit": 98.20, "size_pct": 5, "fill_prob": 0.28},
      {"limit": 96.90, "size_pct": 4, "fill_prob": 0.11}
    ],
    "reserve_pct": 1
  }
}
```

---

## Data Sources

### Free (immediate)

| Source | What | Cost |
|--------|------|------|
| yfinance | Daily OHLCV, some intraday | Free |
| SEC EDGAR | US filings/XBRL/Form 4/13F | Free |
| FRED + ALFRED | Macro + vintage macro data | Free |
| Companies House | UK filings | Free |
| RNS/ISS | UK company announcements | Free |
| Bank of England | UK macro | Free |
| ONS | UK economic data | Free |
| Qlib | Factor engineering + ML pipeline | Free |

### Low Cost (test first)

| Source | What | Cost |
|--------|------|------|
| IBKR Cboe EU L2 | European depth | Fee-waived non-pro |
| IBKR LSE UK L2 | UK depth | £7/mo non-pro |
| IBKR Historical Ticks | Trades/BID_ASK/MIDPOINT | Free for clients |

### Build Yourself

| Source | What | How |
|--------|------|-----|
| Historical L2 | Order book events | Record from IBKR daily |

---

## Build Your Own L2 Dataset

Run a small process whenever markets are open:

```
IBKR TWS/Gateway
      │
      ├── trades
      ├── top bid/ask
      └── market depth
              ↓
       raw event recorder
              ↓
       compressed Parquet
              ↓
              R2
```

Record every:

```
timestamp_ns
ticker
venue

bid_px_1 ... bid_px_10
bid_sz_1 ... bid_sz_10

ask_px_1 ... ask_px_10
ask_sz_1 ... ask_sz_10
```

After three months: proprietary microstructure history.
After a year: even better.

---

## Free LOB Datasets for Mantis Training

| Dataset | What | Use |
|---------|------|-----|
| FI-2010 | LOB benchmark | Learn mechanics |
| LOBFrame | Large-scale LOB research framework | Training pipeline |
| NASDAQ ITCH | Event-driven L3 reconstruction | Event-driven mechanics |

---

## Confidence = Statistically Precise Uncertainty

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

Track: did 80% intervals actually contain reality 80% of the time?
If not: **confidence gets recalibrated downward automatically.**

---

## Benchmark: Richer Than UP/DOWN

Normal ML benchmarks ask:
```
Did you correctly predict: UP / DOWN?
```

Your Sequence benchmark asks whether a model correctly understood:
- direction
- magnitude
- timing
- volatility
- drawdowns
- regime
- reversal points
- confidence
- uncertainty
- conditional reactions

Suppose Model A says:
```
+30% within 12 months, confidence 90%
```

and Model B says:
```
+30% within 12 months, confidence 55%
likely -15% drawdown first
```

Reality: -17% → +34%

Directional accuracy calls them both correct.
Sequence knows B understood the path much better.

---

## Build Order

| Priority | Component | Why |
|----------|-----------|-----|
| **P0** | State model | Everything depends on this |
| **P0** | Block bootstrap scenarios | Baseline scenario engine |
| **P0** | Policy optimizer | Core MPC component |
| **P0** | MPC planner | The main loop |
| **P0** | Mantis avatar | Microstructure execution |
| **P1** | FRED + ALFRED integration | Vintage macro data |
| **P1** | SEC EDGAR integration | US fundamentals |
| **P1** | UK filings integration | UK fundamentals |
| **P1** | Regime-conditioned bootstrap | Better scenarios |
| **P1** | Calibration engine | Conformal prediction |
| **P1** | Avatar ensemble blending | Multi-expert |
| **P2** | IBKR L2 recording | Build historical dataset |
| **P2** | VAR/factor state-space | Factor-aware scenarios |
| **P2** | Gaussian process scenarios | Probabilistic |
| **P2** | Diffusion world model | Generative |
| **P2** | Qlib integration | Cross-sectional ML |
| **P3** | LOBFrame/Mantis training | Microstructure models |
| **P3** | Three nested world models | Full hierarchy |

---

## The Really Insane Version

Eventually Fish has **three nested world models**.

### Macro world model
```
months → years
rates, inflation, growth, technology, sector, fundamentals, Feedify
```

### Market world model
```
days → months
price, volume, factor state, earnings, options, analyst revisions, flows
```

### Microstructure world model
```
milliseconds → days
book, OFI, trades, queues, spreads, liquidity
```

Then:

```
P(S_future | S_today)
```

is hierarchical. Sequence asks all three.

---

## References

| Paper | Relevance |
|-------|-----------|
| DeepLOB (2018) | LOB prediction from deep learning |
| Multi-Level OFI (2019) | Deeper book improves prediction |
| Order Flows and LOB Resiliency (2017) | Additions/cancellations informativeness |
| Deep LOB Forecasting (2024) | High accuracy ≠ executable profit |
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
