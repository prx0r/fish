# Fish Strategy System — Based on Financial ML Research

## Source Material

### Books
1. **Advances in Financial Machine Learning** — Marcos López de Prado
   - Meta-labeling, purged k-fold CV, triple-barrier method, fractional differentiation
   - Deflated Sharpe Ratio, feature importance with substitution effects
   - THE foundational text for financial ML

2. **Quantitative Trading** — Ernie Chan
   - Mean reversion, pairs trading, cointegration
   - Backtest overfitting prevention
   - Simple strategies that work

3. **Algorithmic Trading** — Ernie Chan
   - Winning strategies and their rationale
   - Risk management, position sizing

4. **Machine Trading** — Ernie Chan
   - ML for risk management, not alpha generation
   - Meta-labeling architecture

### Blogs
- **Ernie Chan** (epchan.blogspot.com) — Quantitative trading strategies
- **Robert Alvaro** — Financial ML research
- **QuantResearch.org** — López de Prado's publications

### Key Concepts from Research

#### From López de Prado:
1. **Meta-labeling**: Don't predict direction. Predict probability of success.
2. **Purged K-Fold CV**: Standard cross-validation fails in finance (look-ahead bias).
3. **Triple-Barrier Method**: Label returns by entry/stop/target, not fixed time.
4. **Deflated Sharpe Ratio**: Correct for multiple testing bias.
5. **Feature importance with substitution effects**: Don't trust naive feature importance.

#### From Ernie Chan:
1. **Mean reversion** works in quiet markets
2. **Momentum** works in trending markets
3. **Keep it simple** — over-complexity kills
4. **Risk management** > alpha generation
5. **Backtest overfitting** is the #1 killer

#### From BEAR (crypto):
1. **Confluence scoring** — Multiple accounts agreeing = signal
2. **Regime detection** — Market state determines strategy viability
3. **Binary activation** — Strategy ON/OFF based on regime
4. **Point-in-time data** — Never use future information

---

## Strategy Avatars (Revised)

Each avatar is now based on a PROVEN strategy, not just a temperament.

### 🐻 Bear — Mean Reversion (Ernie Chan Style)
**Strategy**: Buy when price drops below 2-standard-deviation band, sell on mean reversion
**Based on**: Chan's pairs trading + mean reversion research
**Best for**: Range-bound markets, established companies
**Risk**: Trending markets (stop loss essential)

### 🐂 Bull — Momentum (Trend Following)
**Strategy**: Buy when 20-day MA crosses above 50-day MA, sell on crossunder
**Based on**: Classic trend following, validated across decades
**Best for**: Trending markets, growth stocks
**Risk**: False breakouts, whipsaws

### 🦅 Eagle — High-Conviction Value (Warren Buffett Style)
**Strategy**: Buy undervalued companies with durable moats, hold long-term
**Based on**: Value investing principles + margin of safety
**Best for**: Quality companies at discount
**Risk**: Value traps, long holding periods

### 🐍 Snake — Contrarian (Fade the Crowd)
**Strategy**: Buy when sentiment极度 bearish, sell when极度 bullish
**Based on**: Contrarian research, sentiment analysis
**Best for**: Overreaction markets
**Risk**: Catching falling knives

### 🐺 Wolf — Confluence (BEAR Style)
**Strategy**: Multiple independent signals align → high-confidence trade
**Based on**: BEAR's confluence scoring
**Best for**: High-conviction setups
**Risk**: Low frequency, missed opportunities

### 🐝 Bee — Consistent Gains (Kelly Criterion)
**Strategy**: Small consistent wins, strict risk management
**Based on**: Kelly criterion position sizing
**Best for**: Steady compounding
**Risk**: Small gains, slow growth

### 🦈 Shark — Opportunistic (Event-Driven)
**Strategy**: Strike on catalysts (earnings, news, macro events)
**Based on**: Event-driven trading research
**Best for**: Volatile periods
**Risk**: Timing risk, event misinterpretation

### 🦉 Owl — Long-Term Value (Buy & Hold + Rebalance)
**Strategy**: Buy quality, rebalance quarterly, ignore noise
**Based on**: Passive investing + periodic rebalancing
**Best for**: Core portfolio positions
**Risk**: Underperformance in momentum markets

### 🐆 Cheetah — Quick Trades (Scalping)
**Strategy**: Small quick profits, tight stops
**Based on**: Short-term mean reversion
**Best for**: Volatile liquid markets
**Risk**: Transaction costs eat profits

### 🐢 Turtle — Ultra-Long-Term (Decade View)
**Strategy**: Buy and hold for 10+ years, ignore everything
**Based on**: Buffett's favorite holding period
**Best for**: Core compounders
**Risk**: May underperform for years

---

## Stock Type × Strategy Matrix

| Stock Type | Best Strategies | Worst Strategies |
|------------|-----------------|------------------|
| **Growth** (TSLA, META) | 🐂 Bull, 🦈 Shark | 🐢 Turtle (too volatile) |
| **Value** (BT.A, TSCO) | 🦅 Eagle, 🦉 Owl | 🐆 Cheetah (no volatility) |
| **Defensive** (INEYI, MAN) | 🐝 Bee, 🦉 Owl | 🐂 Bull (low growth) |
| **Speculative** (MPAL, PGEN) | 🐺 Wolf, 🦈 Shark | 🐢 Turtle (too risky) |
| **Cyclical** (IAG, JDW) | 🐍 Snake, 🦅 Eagle | 🐝 Bee (too volatile) |
| **Turnaround** (COLL, PBI) | 🐻 Bear, 🐍 Snake | 🐂 Bull (declining) |

---

## Monte Carlo Validation

For each strategy, run 1000 simulations with random market conditions:

```python
def monte_carlo_backtest(strategy, prices, n_simulations=1000):
    results = []
    for _ in range(n_simulations):
        # Add noise to prices
        noisy_prices = add_noise(prices, volatility=0.02)
        # Run strategy
        result = run_strategy(strategy, noisy_prices)
        results.append(result)
    
    # Calculate confidence intervals
    mean_return = np.mean([r['return'] for r in results])
    std_return = np.std([r['return'] for r in results])
    sharpe = mean_return / std_return if std_return > 0 else 0
    
    return {
        'mean_return': mean_return,
        'std_return': std_return,
        'sharpe': sharpe,
        'percentile_5': np.percentile([r['return'] for r in results], 5),
        'percentile_95': np.percentile([r['return'] for r in results], 95),
    }
```

---

## Recommended Reading

### Must-Read Books
1. **Advances in Financial Machine Learning** — López de Prado (THE bible)
2. **Quantitative Trading** — Ernie Chan (practical strategies)
3. **Algorithmic Trading** — Ernie Chan (winning strategies)
4. **Machine Trading** — Ernie Chan (ML for risk)
5. **Algorithmic Trading with Python** — Yves Hilpisch

### Must-Read Blogs
1. **epchan.blogspot.com** — Ernie Chan's strategies
2. **QuantResearch.org** — López de Prado's publications
3. **QuantStart.com** — Algorithmic trading tutorials
4. **Quantocracy.com** — Aggregated quant research

### Key Papers
1. "The Myth and Reality of Financial Machine Learning" — López de Prado
2. "A Data Science Solution to the Multiple-Testing Crisis" — López de Prado
3. "Financial Machine Learning: An Engineering Problem" — López de Prado
