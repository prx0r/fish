# Paper Trading Simulator — Design Doc

**Purpose**: AI suggests trades, you decide. Track who's better — AI or human.

---

## Architecture

```
AI SUGGESTION                    USER DECISION
    │                                │
    ▼                                ▼
┌──────────────┐              ┌──────────────┐
│  AI TRADE    │              │  YOUR TRADE  │
│  (proposed)  │              │  (accepted/  │
│              │              │   rejected)  │
└──────────────┘              └──────────────┘
    │                                │
    ▼                                ▼
┌──────────────────────────────────────────┐
│           PAPER TRADE LOG                │
│  date | ticker | action | qty | price    │
│  reason | ai_score | user_decision       │
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│         PERFORMANCE TRACKER              │
│  AI P&L vs User P&L                      │
│  Win rate | Sharpe | Max drawdown        │
└──────────────────────────────────────────┘
```

---

## Data Model

```sql
-- Paper trades
CREATE TABLE paper_trades (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,  -- BUY/SELL
    qty REAL NOT NULL,
    price REAL NOT NULL,
    reason TEXT,
    source TEXT,  -- 'ai' or 'user'
    ai_score REAL,
    ai_reasoning TEXT,
    user_decision TEXT,  -- 'accepted'/'rejected'/'modified'
    created_at TIMESTAMP
);

-- Performance snapshots
CREATE TABLE paper_snapshots (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    portfolio_value REAL,
    cash REAL,
    ai_pnl REAL,
    user_pnl REAL,
    created_at TIMESTAMP
);

-- AI trade suggestions
CREATE TABLE ai_suggestions (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    qty REAL,
    price REAL,
    reasoning TEXT,
    confidence REAL,
    status TEXT,  -- 'pending'/'accepted'/'rejected'/'expired'
    created_at TIMESTAMP
);
```

---

## AI Trade Suggestion Format

```json
{
  "ticker": "MPAL",
  "action": "SELL",
  "qty": 26000,
  "reasoning": "MPAL up 83% in 3 months. Support at 5.50, resistance at 7.50. Current price 6.64 is -12% from high. Trim 50% to lock £835 profit.",
  "confidence": 0.75,
  "risk_reward": "1:3",
  "stop_loss": 5.50,
  "target": 10.00
}
```

---

## Performance Tracking

```python
# AI performance
ai_trades = [t for t in trades if t.source == "ai"]
ai_pnl = sum(t.qty * (current_price - t.price) for t in ai_trades if t.action == "BUY")
ai_win_rate = wins / total_ai_trades

# User performance
user_trades = [t for t in trades if t.source == "user"]
user_pnl = sum(t.qty * (current_price - t.price) for t in user_trades if t.action == "BUY")
user_win_rate = wins / total_user_trades

# Comparison
if ai_pnl > user_pnl:
    print("AI is outperforming you")
else:
    print("You're beating the AI")
```

---

## Other Traders (from X)

```
TICKER: MPAL
├── @braaannigan (source_distance=0) — last mentioned MPAL on Aug 7
├── @GenAI_is_real (source_distance=0) — no MPAL mentions
├── @advaith_sridhar (source_distance=0) — materials/thermal constraints
└── Market consensus: 3 analysts rate BUY, 1 HOLD
```

When multiple traders discuss the same ticker, that's a signal.
