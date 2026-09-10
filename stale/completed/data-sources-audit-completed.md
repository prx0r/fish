# ML Training Data Sources

## Free Datasets

### For Price Data
| Source | Data | Size | Access |
|--------|------|------|--------|
| **Yahoo Finance (yfinance)** | Daily OHLCV, 20+ years | Unlimited | Python API |
| **HuggingFace: paperswithbacktest/Stocks-Daily-Price** | 26M rows, 7,764 symbols, 1962-2026 | 26M rows | Download |
| **Kaggle: jacksoncrow/stock-market-dataset** | All NASDAQ daily prices | Large | Download |
| **Interactive Brokers** | Tick-by-tick, historical bars | Unlimited | API (needs account) |

### For Order Book / Level 2
| Source | Data | Cost | Access |
|--------|------|------|--------|
| **Interactive Brokers** | Level 2, historical ticks | Free with account | API |
| **London Strategic Edge** | Live WebSocket, 4000+ instruments | Free tier (50GB/mo) | API key |

### For Fundamentals
| Source | Data | Cost | Access |
|--------|------|------|--------|
| **SEC EDGAR** | Form 4, 13F, 8-K, XBRL | Free | REST API |
| **FRED** | Macro indicators | Free | API |
| **Yahoo Finance** | Financials, estimates | Free | yfinance |

### For Sentiment
| Source | Data | Cost | Access |
|--------|------|------|--------|
| **FinBERT** | Financial sentiment | Free | HuggingFace |
| **RSS feeds** | News per stock | Free | HTTP |

---

## Key Datasets to Clone

| Dataset | Location | What |
|---------|----------|------|
| HuggingFace: paperswithbacktest/Stocks-Daily-Price | huggingface.co | 26M rows, 7,764 symbols |
| Kaggle: jacksoncrow/stock-market-dataset | kaggle.com | All NASDAQ daily |
| GitHub: Microsoft Qlib | github.com/microsoft/qlib | Alpha158/Alpha360 features |
| GitHub: AlphaGen | github.com/ICT-FinD-Lab/alphagen | Symbolic alpha generation |
| GitHub: RD-Agent | github.com/microsoft/rd-agent | Autonomous factor mining |

---

## What We Already Have

| Data | Source | Coverage |
|------|--------|----------|
| Daily OHLCV | Yahoo Finance | 15 tickers, 500+ days |
| Insider filings | SEC EDGAR | Form 4, 13F |
| Earnings dates | Hardcoded | 15 positions |
| News | None | Need to add |

---

## What to Build Next

1. **Fetch HuggingFace dataset** — 26M rows for cross-sectional training
2. **Fetch Qlib Alpha158 features** — Pre-computed factor set
3. **Build feature pipeline** — Price + fundamental + sentiment features
4. **Train LightGBM model** — On the 2,110-sample ML dataset
5. **Validate with walk-forward** — Train 2yr, test 6mo, roll forward
