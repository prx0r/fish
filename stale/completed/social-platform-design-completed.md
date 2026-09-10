# Fish — Social Portfolio Platform

**Vision**: Create account → upload screenshots → track performance → compare with friends → AI vs Human.

---

## Architecture

```
USER ACCOUNTS
    │
    ├── Chris Prior (19 positions)
    ├── Cathy Prior (?? positions)
    └── Future users
         │
         ▼
┌─────────────────────────────────────────┐
│           PORTFOLIO ENGINE              │
│  ├── Screenshot OCR → positions         │
│  ├── Live price tracking                │
│  ├── Performance calculation            │
│  └── Historical snapshots               │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         SOCIAL LAYER                    │
│  ├── Friend connections                 │
│  ├── Portfolio comparison               │
│  ├── Leaderboard (AI vs Human)          │
│  └── Shared insights                    │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         AI LAYER                        │
│  ├── Daily briefs per user              │
│  ├── Chat with graph context            │
│  ├── Paper trading (AI vs Human)        │
│  └── Custom report generation           │
└─────────────────────────────────────────┘
```

---

## Data Model

```sql
-- User accounts
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMP
);

-- Portfolios (one per user)
CREATE TABLE portfolios (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT DEFAULT 'My Portfolio',
    created_at TIMESTAMP
);

-- Friends
CREATE TABLE friendships (
    user_id TEXT NOT NULL,
    friend_id TEXT NOT NULL,
    created_at TIMESTAMP,
    PRIMARY KEY (user_id, friend_id)
);

-- Performance snapshots (daily)
CREATE TABLE performance_snapshots (
    id INTEGER PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    total_value REAL,
    cash REAL,
    daily_return REAL,
    cumulative_return REAL,
    ai_suggested_value REAL,  -- what AI would have returned
    created_at TIMESTAMP
);
```

---

## Screenshot OCR Flow

```
USER UPLOADS SCREENSHOT
    │
    ▼
OCR EXTRACTION (extract positions)
    │
    ▼
PARSED POSITIONS (ticker, qty, price, value)
    │
    ▼
CONFIRM WITH USER
    │
    ▼
SAVE TO PORTFOLIO
```

---

## Performance Comparison

```
CHRIS PRIOR vs CATHY PRIOR vs AI MODEL

             Chris    Cathy    AI Model
Return       +7.66%   +12.3%   +9.8%
Sharpe       1.2      1.5      1.4
Max DD       -8.2%    -5.1%    -6.3%
Win Rate     65%      72%      68%

AI Model: What if we gave the AI full control?
- Backtest on historical data
- Calculate hypothetical returns
- Compare to actual human performance
```
