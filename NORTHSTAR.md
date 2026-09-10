# Fish Northstar: AI Strategy Arena

**Vision**: Gamified backtesting where each strategy is an avatar/animal with a temperament. Users compete against AI models and their own past decisions.

---

## Strategy Avatars

| Avatar | Name | Temperament | Strategy |
|--------|------|-------------|----------|
| 🐻 | **Bear** | Conservative | Sell on weakness, buy on deep dips |
| 🐂 | **Bull** | Aggressive | Buy momentum, ride trends |
| 🦅 | **Eagle** | Selective | High-conviction, low-frequency |
| 🐍 | **Snake** | Contrarian | Mean reversion, fade the crowd |
| 🐺 | **Wolf** | Pack hunter | Confluence of signals |
| 🐝 | **Bee** | Industrious | Small consistent gains |
| 🦈 | **Shark** | Opportunistic | Strike when blood in water |
| 🦉 | **Owl** | Wisdom | Long-term value, ignore noise |
| 🐆 | **Cheetah** | Fast | Quick entries, quick exits |
| 🐢 | **Turtle** | Patient | Buy and hold forever |

---

## Backtest Game Flow

```
SELECT AVATAR (strategy)
    │
    ▼
SELECT TICKER (Chris's basket)
    │
    ▼
SELECT INTERVAL (1D / 1W / 1M)
    │
    ▼
SELECT PERIOD (Jan 2026 → Sep 2026)
    │
    ▼
SIMULATE
    │
    ├── Avatar makes trades at each step
    ├── Human makes trades (or does nothing)
    ├── Buy & Hold runs as benchmark
    │
    ▼
RESULTS
    ├── Chart with buy/sell markers
    ├── P&L comparison
    ├── Win rate, Sharpe, max drawdown
    ├── Leaderboard ranking
    └── Regime analysis (bull/bear/range)
```

---

## Regime Analysis

| Regime | Definition | Best Avatar |
|--------|-----------|-------------|
| Bull | >10% rise in 3 months | 🐂 Bull, 🐆 Cheetah |
| Bear | >10% fall in 3 months | 🐻 Bear, 🐍 Snake |
| Range | -10% to +10% | 🦅 Eagle, 🦉 Owl |
| High Vol | >20% swing | 🐺 Wolf, 🦈 Shark |
| Low Vol | <5% swing | 🐝 Bee, 🐢 Turtle |

---

## Scoring

```
Avatar Score = (Return × Sharpe × Win Rate) / (Max Drawdown × Volatility)

Normalized to 0-100 scale.
Leaderboard: Best score across all avatars for a given ticker.
```
