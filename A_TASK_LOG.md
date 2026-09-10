# Fish — A-Task Log & Next Steps

**Session**: 2026-09-10
**Status**: A1-A37 complete, deployed to fish.egoic.ai

---

## Completed A-Tasks

| # | Task | Output |
|---|------|--------|
| A1-A10 | Core features | Dashboard, portfolio, brief, chat, trading, backtest, social |
| A11-A15 | Enhanced brief | Sector allocation, risk assessment, technical indicators |
| A16-A17 | Alerts + macro | Portfolio alerts, GBP/USD, VIX, yields |
| A18-A19 | Stock research | Research pages, trade history |
| A20 | SVG chart | TradingView Lightweight Charts |
| A21 | Strategy compiler | Prompt → algorithm conversion |
| A22-A24 | Chart features | Support/resistance, multi-interval, comparison |
| A25 | Macro context | Market indicators in backtest |
| A26-A29 | Price fetching + strategy gen | Yahoo Finance, strategy templates |
| A30-A32 | API wiring | Strategy compilation, comparison endpoints |
| A33-A35 | Portfolio backtest + metrics | Full portfolio simulation, Sharpe/Sortino |
| A36-A37 | Comparison page | AI vs Human vs Buy&Hold |

---

## Evidence: What We Built

### Dashboard (fish.egoic.ai)
- 19 positions loaded
- Daily brief with sector allocation, risk assessment
- AI chat with graph context
- Macro indicators (GBP/USD, VIX, yields)
- Portfolio alerts (concentration, losers, winners)

### Backtest (fish.egoic.ai/backtest)
- TradingView Lightweight Charts (35KB, Apache 2.0)
- Candlestick chart with volume
- Buy/sell markers (Hyperliquid style)
- Configurable intervals (1D, 1W, 1M)
- Strategy selector (Buy&Hold, AI, Custom)
- Support/resistance lines
- Trade log with P&L
- Performance metrics (Sharpe 3.16, 99.36% return)

### Comparison (fish.egoic.ai/compare)
- Chris vs Cathy vs AI model
- Portfolio value, gain, return comparison

### API Endpoints (new)
| Endpoint | Purpose |
|----------|---------|
| `GET /api/backtest/metrics` | Sharpe, volatility, max drawdown |
| `POST /api/backtest/portfolio` | Full portfolio simulation |
| `POST /backtest/compare` | Strategy comparison |
| `GET /api/portfolio/brief/enhanced` | Enhanced brief with technicals |
| `GET /api/macro` | Macro indicators |
| `GET /api/alerts` | Portfolio alerts |
| `GET /api/stocks/{ticker}/research` | Stock research page |

---

## Next A-Tasks (With Justification)

### A38: Wire real Yahoo Finance prices into backtest
**Why**: Current prices are hardcoded monthly snapshots. Real prices would show actual intraday volatility and more accurate backtest results.
**Evidence**: MPAL moved from 3.60 to 7.50 in one day (Sep 9). Monthly snapshots miss this.
**Validation**: Compare backtest results with real vs simulated prices.

### A39: Add real-time price tracking
**Why**: Daily brief shows static prices. Real-time tracking enables live alerts when positions hit key levels.
**Evidence**: Current brief says "MPAL: £3,677" but doesn't update during the day.
**Validation**: Check if price updates every 5 minutes during market hours.

### A40: Build AI strategy generation from prompts
**Why**: User should be able to say "buy when RSI < 30" and have it converted to an executable algorithm.
**Evidence**: Strategy compiler exists but only handles 5 templates. Need full natural language → algorithm.
**Validation**: Test with 10 different prompts, verify each produces correct strategy.

### A41: Add trade history persistence
**Why**: Paper trades are logged but not persisted across sessions. Need database storage.
**Evidence**: Current paper trades are in-memory only. Server restart loses them.
**Validation**: Create trade, restart server, verify trade persists.

### A42: Build comparison charts (AI vs Human vs Buy&Hold)
**Why**: Users need to see visual comparison of strategies over time.
**Evidence**: Comparison page exists but only shows numbers, not charts.
**Validation**: Generate chart with three lines (AI, Human, B&H) and verify they're distinct.

### A43: Add portfolio drift alerts
**Why**: Users need to know when their allocation drifts from target.
**Evidence**: Alert endpoint exists but doesn't check against target allocation.
**Validation**: Set target allocation, drift portfolio, verify alert fires.

### A44: Add earnings date tracking
**Why**: Earnings are major catalysts. Users need to know when each position reports.
**Evidence**: No earnings tracking exists currently.
**Validation**: Add earnings dates for all 19 positions, verify they show in daily brief.

### A45: Build strategy backtester (prompt → algorithm → backtest)
**Why**: Users should be able to describe a strategy and immediately see how it would have performed.
**Evidence**: Strategy compiler exists but isn't wired to backtest engine.
**Validation**: "Buy when RSI < 30" → compile → backtest → show results.

---

## Priority Matrix

| | High Value | Low Value |
|---|-----------|-----------|
| **Easy** | A38, A39, A41 | A44 |
| **Hard** | A40, A42, A45 | A43 |

**Recommendation**: Do A38 → A39 → A41 → A40 → A42 → A45 (easy high-value first)

---

## Cost Summary

| Item | Cost |
|------|------|
| All A-tasks | $0 (agent work) |
| GetXAPI (2,553 tweets) | $0.14 (already paid) |
| LLM (mimo-v2.5) | ~$0.01/1K tokens |
| **Total session** | **~$0.15** |
