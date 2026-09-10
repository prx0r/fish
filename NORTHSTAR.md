# Fish Northstar: AI Trading Backtester

**Vision**: A mobile-first backtesting app where you can:
1. See your portfolio with TradingView charts
2. Run simulations at 1-day, 1-week, or 1-month intervals
3. Watch AI make trades vs your decisions
4. Benchmark against buy-and-hold
5. Prompt the AI with strategy ideas → it converts to algorithms
6. Paper trade live from your portfolio

---

## Core Loop

```
SELECT TICKER → SELECT INTERVAL → RUN SIMULATION
        │                │                │
        ▼                ▼                ▼
  Chart loads      AI + Human      Results show
  with history     make trades     buy/sell markers
  + buy/sell       at each step    + P&L comparison
  markers                             + benchmark
```

---

## TradingView Integration

Use Lightweight Charts (Apache 2.0, 35KB):
```html
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
```

Features needed:
- Candlestick chart with historical data
- Volume bars
- Buy/sell markers (like Hyperliquid)
- Support/resistance lines
- Moving averages (20, 50, 200 day)

---

## Backtesting Engine

### Input
- Portfolio positions (ticker, qty, entry price)
- Start date (Jan 1, 2026)
- End date (Sep 10, 2026)
- Interval: 1D, 1W, or 1M
- Strategy: Buy-and-hold, AI, or custom

### Process
```
FOR EACH INTERVAL:
  1. AI analyzes chart + signals
  2. AI proposes trade (BUY/SELL/HOLD)
  3. Human decides (accept/reject/modify)
  4. Execute trade
  5. Record P&L
  6. Move to next interval
```

### Output
- Chart with buy/sell markers
- P&L curve
- Win rate
- Sharpe ratio
- Max drawdown
- Comparison: AI vs Human vs Buy-and-Hold

---

## AI Strategy Builder

```
USER: "Buy when RSI < 30 and MACD crosses up"
        │
        ▼
AI: converts to algorithm:
  if rsi < 30 and macd_cross_up:
      BUY
  elif rsi > 70 and macd_cross_down:
      SELL
  else:
      HOLD
        │
        ▼
BACKTEST: run against historical data
        │
        ▼
RESULT: win rate, Sharpe, max drawdown
```

---

## Paper Trading (Live)

```
PORTFOLIO (19 positions)
        │
        ▼
AI MONITORS (real-time signals)
        │
        ▼
AI SUGGESTS (trade proposal)
        │
        ▼
HUMAN DECIDES (accept/reject)
        │
        ▼
RECORDED (paper trade log)
        │
        ▼
PERFORMANCE (AI vs Human tracking)
```

---

## Technical Architecture

### Backend (Python)
- `backtest_engine.py` — Core backtesting logic
- `strategy_compiler.py` — Convert prompts to algorithms
- `price_fetcher.py` — Historical + real-time prices
- `portfolio_manager.py` — Position tracking

### Frontend (JavaScript)
- TradingView Lightweight Charts
- Buy/sell markers
- Interactive controls (interval selector, strategy selector)
- Performance dashboard

### Data
- Historical prices (Yahoo Finance, Stooq)
- Technical indicators (RSI, MACD, MA)
- Portfolio snapshots (daily)
- Trade log (AI + Human)
