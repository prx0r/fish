# Task Queue: A-Tasks vs H-Tasks

**Rule**: Do all A-tasks first. Only escalate to H-task when you hit a wall.

---

## A-Tasks (Agent Autonomous)

| # | Task | Status | Output |
|---|------|--------|--------|
| A1 | Fetch August data for all 102 accounts | ✅ Done | 1,043 August tweets |
| A2 | Build knowledge graph (7,121 objects, 5,207 edges) | ✅ Done | Graph complete |
| A3 | Fetch daily price data for 15 tickers | ✅ Done | 500+ days each |
| A4 | Implement 10 strategy avatars | ✅ Done | Bear, Bull, Eagle, etc. |
| A5 | Build regime detection | ✅ Done | BULL/BEAR/HIGH_VOL/RANGE |
| A6 | Monte Carlo validation | ✅ Done | 100 sims per stock |
| A7 | Confidence-based position sizing | ✅ Done | HIGH/MEDIUM/LOW |
| A8 | Rebalancing engine | ✅ Done | Sector allocation |
| A9 | TradingView charts | ✅ Done | Buy/sell markers |
| A10 | Earnings calendar | ✅ Done | 15 positions |
| A11 | Real-time prices | ✅ Done | Yahoo Finance |
| A12 | Portfolio health score | ✅ Done | 0-100 |
| A13 | Convergence detection | ✅ Done | 145 convergences |
| A14 | Backtest on daily data | ✅ Done | 500+ days |
| A15 | Strategy comparison | ✅ Done | All avatars vs B&H |
| A16 | Northstar spec | ✅ Done | Strategy avatars |
| A17 | ML strategy research | ✅ Done | López de Prado, Ernie Chan |
| A18 | Simplified signals (BUY/SELL) | ✅ Done | Clean output |
| A19 | Simplified signals with stops | ✅ Done | For AI agents |

---

## H-Tasks (Need Human Approval)

| # | Task | What I Need | Demo |
|---|------|-------------|------|
| H1 | Cathy Prior's portfolio screenshots | Upload screenshots of her AJ Bell | "I'll parse them and ask you to confirm" |
| H2 | Set AI trading parameters | How aggressive? Conservative? | "Default: 5% max, -10% stop, 2:1 R:R" |
| H3 | Choose X accounts for your tickers | From 100-account list | "I recommend @braaannigan, @GenAI_is_real" |
| H4 | Approve AI trade suggestions | Each suggestion needs OK | "AI suggests SELL 30% MPAL. Accept?" |
| H5 | Set daily brief preferences | What to include/exclude | "Include: movers, concentration, alerts" |
| H6 | Approve production deployment | Deploy v2 to v2.feedify.egoic.ai | "Ready when you are" |
| H7 | Approve x402 paid feeds | Enable paid machine-readable feeds | "£0.01 per feed request" |
| H8 | Approve email delivery | Send daily briefs to email | "£5/month for email" |

---

## What's Running

| Service | URL | Port |
|---------|-----|------|
| Feedify v1 | feedify.egoic.ai | 8787 |
| Feedify v2 | v2.feedify.egoic.ai | 8788 |

## Cost Summary

| Item | Cost |
|------|------|
| GetXAPI (3,357 tweets) | $0.17 |
| LLM (mimo-v2.5) | ~$0.01/1K tokens |
| **Total** | **~$0.18** |
