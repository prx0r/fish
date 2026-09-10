# Fish Data Acquisition Plan — Autonomous Data Stack

**Saved**: 2026-09-10T23:00:00Z
**Status**: Active reference
**Key insight**: 95%+ of data workflow can be autonomous

---

## What You Need to Do (One-Time)

| Action | Source | Time |
|--------|--------|------|
| Create IBKR account + enable L2 | Interactive Brokers | 30 min |
| Create Kaggle API token | Kaggle | 2 min |
| Create HuggingFace token + approve China L2 | HuggingFace | 5 min |
| Optional: Alpaca API key | Alpaca | 5 min |
| Optional: MT5 broker/demo login | MetaTrader 5 | 10 min |
| Optional: Sierra Chart temporary subscription | Sierra Chart | varies |

**Everything after those actions can be delegated to the agent.**

---

## Autonomous Data Sources (No Manual Steps)

### Long Horizon (months → years)

| Source | Data | Cost |
|--------|------|------|
| Yahoo/yfinance | Daily/intraday OHLCV | Free |
| HuggingFace: paperswithbacktest/Stocks-Daily-Price | 26M rows daily | Free |
| HuggingFace: paperswithbacktest/Stocks-1Min-Price | 5.7B rows minute | Free |
| Qlib | Factor pipeline/Alpha158 | Free |
| SEC EDGAR | 10-K/Q, 8-K, Form 4, XBRL | Free |
| FRED + ALFRED | Macro + historical vintages | Free |
| Companies House | UK filings | Free |

### Intraday (minutes → hours)

| Source | Data | Cost |
|--------|------|------|
| HuggingFace: TroveLedger | Large intraday datasets | Free |
| Alpaca IEX | US trades/quotes WebSocket | Free |
| MT5 broker histories | Ticks/bid-ask/last | Free with broker |

### Microstructure (milliseconds → minutes)

| Source | Data | Cost |
|--------|------|------|
| HuggingFace: China L2 | 555B rows, 10-level book | Free (request) |
| FI-2010 (Kaggle) | 5 Nasdaq Nordic stocks, 10 levels | Free |
| LOBSTER samples | AAPL/MSFT/GOOG L1-L50 | Free |
| Nasdaq ITCH samples | Full-depth order events | Free |
| Databento PCAP samples | Raw TotalView captures | Free |
| Cboe Europe sample PITCH | European depth | Free |
| GitHub researcher datasets | Various LOB datasets | Free |

### Live/Exact Portfolio

| Source | Data | Cost |
|--------|------|------|
| IBKR L2 | Real-time depth for Chris's 19 stocks | £7/mo |
| Record ourselves | Build historical dataset from day 1 | Storage only |

---

## The DataHunter Agent

A permanent agent that continuously:

1. **Discovers** datasets on HF, Kaggle, GitHub, Nasdaq, Cboe, SEC, FRED, academic supplements
2. **Records** metadata (source, markets, symbols, dates, frequency, depth, license, cost, auth)
3. **Downloads** anything with cost=0 AND acceptable license AND novel information
4. **Alerts** only when manual auth or payment required

### DataHunter Universe

```
HuggingFace
Kaggle
GitHub
Nasdaq
Cboe
SEC
FRED/ALFRED
Companies House
exchange public FTPs
academic supplementary files
Zenodo
Figshare
Dataverse
broker APIs
x402
```

### DataHunter Output Schema

```json
{
  "dataset_id": "venvoo/china-a-share-l2",
  "source": "huggingface",
  "markets": ["china", "a-share"],
  "symbols": "all",
  "date_start": "2017-01-01",
  "date_end": "2026-09-10",
  "frequency": "tick",
  "depth": "L10",
  "trades": true,
  "orders": true,
  "cancellations": true,
  "size_tb": 6.18,
  "license": "cc-by-nc-4.0",
  "cost": 0,
  "auth_required": true,
  "point_in_time_safe": true,
  "survivorship_safe": true,
  "quality_score": 0.9,
  "download_method": "huggingface_hub",
  "content_hash": "abc123"
}
```

---

## Priority Download Order

### Phase 1: Immediate (no auth needed)

1. **FI-2010 from Kaggle** — LOB benchmark, 940MB
2. **LOBSTER samples** — AAPL/MSFT/GOOG L1-L50
3. **Nasdaq ITCH samples** — Full-depth order events
4. **HF: Stocks-Daily-Price** — 26M rows
5. **HF: Stocks-1Min-Price** — 5.7B rows

### Phase 2: After auth tokens

6. **HF: China L2** — 555B rows, 10-level book (request access)
7. **HF: TroveLedger** — Large intraday datasets
8. **SEC EDGAR** — US fundamentals
9. **FRED/ALFRED** — Macro vintages

### Phase 3: After IBKR setup

10. **IBKR L2 recording** — Start recording depth from day 1
11. **Cboe Europe PITCH** — European depth

---

## Key Insight

> **Train the microstructure models globally, then fine-tune/calibrate them on your own UK stream.**

The China L2 dataset (555B rows) trains Mantis on:
- Wall persistence
- Cancellation behavior
- Queue dynamics
- OFI/MLOFI
- Microprice
- LOB forecasting
- Volatility transitions
- Liquidity regimes

Those primitives transfer between markets better than exact stock-price processes.

---

## What Fish Gets

```
LONG HORIZON
Yahoo
HF 26M daily rows
Qlib
SEC
FRED/ALFRED

INTRADAY
HF 5.7B minute rows
TroveLedger
MT5 broker histories
Alpaca IEX

MICROSTRUCTURE
HF China L2 555B rows
FI-2010
Kaggle LOB mirrors
LOBSTER L1-L50 samples
Nasdaq ITCH samples
Databento PCAP samples
Cboe Europe sample PITCH
GitHub researcher datasets

LIVE / EXACT PORTFOLIO
IBKR L2
↓
record ourselves forever
```

**This is enough data to build the entire Sequence/Mantis architecture before spending meaningful money on data.**
