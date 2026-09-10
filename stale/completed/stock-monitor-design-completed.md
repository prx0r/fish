# Stock Monitor — Design Doc

**Purpose**: Daily investor reports for watched stocks, with AI chat that saves to memory.

---

## Architecture

```
WATCHLIST (stocks to monitor)
        │
        ▼
DAILY SCRAPE (price, news, filings)
        │
        ▼
KNOWLEDGE GRAPH (objects + edges)
        │
        ▼
DAILY REPORT (bitesized summary)
        │
        ▼
AI CHAT (ask questions, saves to memory)
```

---

## Data Model

### New Tables

```sql
-- Stock watchlist
CREATE TABLE watchlist (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    sector TEXT,
    thesis TEXT,
    entry_price REAL,
    current_price REAL,
    stop_loss REAL,
    target_price REAL,
    notes TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Daily snapshots
CREATE TABLE stock_snapshots (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    close REAL,
    high REAL,
    low REAL,
    volume INTEGER,
    market_cap REAL,
    news_headlines TEXT,  -- JSON array
    created_at TIMESTAMP,
    UNIQUE(ticker, date)
);

-- Investor reports
CREATE TABLE investor_reports (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    summary TEXT,
    bull_case TEXT,
    bear_case TEXT,
    key_levels TEXT,  -- JSON
    action TEXT,  -- HOLD/ADD/TRIM/EXIT
    confidence REAL,
    created_at TIMESTAMP,
    UNIQUE(ticker, date)
);

-- Chat memory
CREATE TABLE chat_memory (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    user_id TEXT,
    message TEXT,
    response TEXT,
    context TEXT,  -- JSON
    created_at TIMESTAMP
);
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stocks` | GET | List watched stocks |
| `/api/stocks` | POST | Add stock to watchlist |
| `/api/stocks/{ticker}` | GET | Stock detail + latest report |
| `/api/stocks/{ticker}/snapshots` | GET | Price history |
| `/api/stocks/{ticker}/report` | GET | Latest investor report |
| `/api/stocks/{ticker}/chat` | POST | AI chat about stock |
| `/api/stocks/daily-report` | GET | All stocks daily summary |

---

## Daily Report Format

```markdown
# MPAL Daily Report — Sep 10, 2026

## Price Action
- Close: 6.64 GBX (-0.91%)
- Volume: 44.5M (elevated)
- Support: 5.50 | Resistance: 7.50

## News
- Aug revenue: £1.83M (up 809% MoM)
- Oral GLP-1 launch progressing

## Thesis Status
- EBITDA breakeven target: Oct-Nov 2026
- Current run rate: ~£28M annualised
- Cash: ~£8M

## Action
HOLD — trim 30% at 7.00, stop at 5.50
```

---

## AI Chat Flow

```
User: "What's the outlook for MPAL?"
        │
        ▼
Feedify loads: stock data + latest report + chat memory
        │
        ▼
LLM generates response with context
        │
        ▼
Response saved to chat_memory table
        │
        ▼
Next chat: memory loaded as context
```

---

## Implementation Plan

1. Add `watchlist`, `stock_snapshots`, `investor_reports`, `chat_memory` tables
2. Build daily scrape job (price + news)
3. Build report generator (LLM-powered)
4. Build AI chat endpoint
5. Build web UI for reports + chat
6. Schedule daily reports via cron
