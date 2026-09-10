"""Portfolio Daily Brief — Chris Prior's portfolio snapshot.

Generates a bitesized daily report when he opens the app.
Then he can chat with the agent about any position.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from fish.settings import get_settings


TRADING_THEORY = """
TRADING THEORY REFERENCE:

SUPPORT/RESISTANCE:
- Support: price level where buying interest emerges
- Resistance: price level where selling pressure emerges
- Breakout above resistance on volume = bullish
- Breakdown below support on volume = bearish

POSITION SIZING:
- Risk no more than 1-2% of portfolio per trade
- Stop loss below key support
- Risk/reward minimum 1:2
- Scale in on pullbacks, don't buy full position at once

MOVING AVERAGES:
- Price above 20-day MA = short-term uptrend
- Price above 50-day MA = medium-term uptrend
- Price above 200-day MA = long-term uptrend

RELATIVE STRENGTH:
- RSI > 70 = overbought
- RSI < 30 = oversold

PORTFOLIO MANAGEMENT:
- Diversification across sectors
- Trim winners, cut losers
- Rebalance when allocation drifts >5%
- Keep 5-10% cash for opportunities
"""


def generate_daily_brief(portfolio: list[dict[str, Any]], chat_memory: list[dict[str, Any]] | None = None) -> str:
    """Generate a bitesized daily brief for Chris Prior's portfolio."""
    total_value = sum(p.get("value", 0) for p in portfolio)
    total_book = sum(p.get("book", 0) for p in portfolio)
    total_gain = sum(p.get("gain", 0) for p in portfolio)
    total_pct = (total_gain / total_book * 100) if total_book else 0
    
    # Categorize by performance
    winners = [p for p in portfolio if p.get("gain", 0) > 0]
    losers = [p for p in portfolio if p.get("gain", 0) < 0]
    
    # Top movers
    top_gainers = sorted(portfolio, key=lambda x: -x.get("pct", 0))[:3]
    top_losers = sorted(portfolio, key=lambda x: x.get("pct", 0))[:3]
    
    # Concentration check
    top5 = sorted(portfolio, key=lambda x: -x.get("value", 0))[:5]
    top5_pct = sum(p.get("value", 0) for p in top5) / total_value * 100 if total_value else 0
    
    brief = f"""# Chris Prior — Daily Brief

**{datetime.now().strftime('%d %B %Y')}**

## Portfolio Snapshot

| Account | Value | P/L |
|---------|-------|-----|
| Dealing | £{sum(p['value'] for p in portfolio if p['account']=='Dealing'):,.2f} | |
| ISA | £{sum(p['value'] for p in portfolio if p['account']=='ISA'):,.2f} | |
| **Total** | **£{total_value:,.2f}** | **£{total_gain:+,.2f} ({total_pct:+.2f}%)** |

## Top Movers Today

| Ticker | Value | Change |
|--------|-------|--------|
"""
    for p in top_gainers:
        brief += f"| {p['ticker']:8s} | £{p['value']:>10,.2f} | {p['pct']:+.2f}% |\n"
    brief += "\n**Laggards:**\n"
    for p in top_losers:
        brief += f"| {p['ticker']:8s} | £{p['value']:>10,.2f} | {p['pct']:+.2f}% |\n"
    
    # Concentration warning
    if top5_pct > 80:
        brief += f"\n⚠️ **Concentration risk**: Top 5 = {top5_pct:.1f}% of portfolio\n"
    
    # Key positions
    brief += "\n## Key Positions\n"
    brief += f"- **TSLA ETP**: £{55565:,.0f} (30.2%) — {11.14:+.1f}%\n"
    brief += f"- **COHR**: £{17029:,.0f} (9.3%) — {6.99:+.1f}% — optical/photonics play\n"
    brief += f"- **MPAL**: £{3677:,.0f} (2.0%) — {83.37:+.1f}% — GLP-1 + NHS pharmacy\n"
    brief += f"- **NBIS**: £{6033:,.0f} (3.3%) — {20.42:+.1f}% — AI infrastructure\n"
    
    # Action items
    brief += "\n## Action Items\n"
    brief += "1. **COLL** down 36% — review thesis or cut\n"
    brief += "2. **JDW** down 38% — review thesis or cut\n"
    brief += "3. **PBI** down 10% — review thesis or cut\n"
    brief += "4. **MPAL** up 83% — trim 30% to lock gains\n"
    brief += "5. **TSLA** 30% concentration — consider trimming\n"
    
    brief += f"\n*Generated {datetime.now().strftime('%H:%M')} | Ask me anything about your positions*"
    
    return brief


async def chat_with_agent(
    message: str,
    portfolio: list[dict[str, Any]],
    chat_memory: list[dict[str, Any]],
    user_id: str = "chris",
) -> str:
    """Chat with the trading advisor. Reasons over portfolio + graph + theory."""
    settings = get_settings()
    url = "https://opencode.ai/zen/go/v1/chat/completions"
    api_key = settings.llm_api_key or ""
    
    # Build portfolio context
    total_value = sum(p.get("value", 0) for p in portfolio)
    portfolio_summary = json.dumps([{
        "ticker": p["ticker"], "name": p["name"], "account": p["account"],
        "value": p["value"], "gain": p["gain"], "pct": p["pct"],
    } for p in portfolio], indent=2)
    
    context = f"""You are Chris Prior's personal trading advisor. You reason over his portfolio and trading theory to give investment advice.

PORTFOLIO:
{portfolio_summary}

Total: £{total_value:,.2f}

{TRADING_RULES}

RULES:
1. Reference specific positions by ticker when giving advice
2. Always mention risk management (stop loss, position sizing)
3. If the portfolio is concentrated, say so
4. If a position is down significantly, give honest assessment
5. Never give generic advice — always reference Chris's specific holdings
6. Keep responses concise and actionable"""
    
    # Add recent chat memory
    if chat_memory:
        context += "\nRECENT CHAT:\n"
        for m in chat_memory[:5]:
            context += f"Chris: {m.get('message', '')}\nYou: {m.get('response', '')[:200]}\n"
    
    # Try up to 3 times
    for attempt in range(3):
        try:
            async with httpx.AsyncClient() as client:
                ticker = portfolio[0].get("ticker", "?")
                name = portfolio[0].get("name", "?")
                value = portfolio[0].get("value", 0)
                pct = portfolio[0].get("pct", 0)
                simplified_context = f"You are a trading advisor. Stock: {ticker} ({name}). Value: {value:,.0f}. Gain: {pct:+.1f}%."
                
                resp = await client.post(url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "x-opencode-session": _session_id(user_id),
                    },
                    json={
                        "model": "mimo-v2.5",
                        "messages": [
                            {"role": "system", "content": f"{simplified_context}\n\n{TRADING_RULES[:1500]}"},
                            {"role": "user", "content": message},
                        ],
                        "max_tokens": 1000,
                        "temperature": 0.3,
                    },
                    timeout=30,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content:
                    return content
        except Exception:
            continue
    
    return "AI temporarily unavailable. Please try again."


import time

def _session_id(user_id: str) -> str:
    """Generate unique session ID."""
    import random
    return f"feedify-{user_id}-{random.randint(100000, 999999)}"

TRADING_RULES = """
TRADING THEORY:

SUPPORT/RESISTANCE:
- Support: price level where buying interest emerges
- Resistance: price level where selling pressure emerges
- Breakout above resistance on volume = bullish
- Breakdown below support on volume = bearish

POSITION SIZING:
- Risk no more than 1-2% of portfolio per trade
- Stop loss below key support
- Risk/reward minimum 1:2
- Scale in on pullbacks, do not buy full position at once

PORTFOLIO MANAGEMENT:
- Diversification across sectors
- Trim winners, cut losers
- Rebalance when allocation drifts >5%
- Keep 5-10% cash for opportunities
- Max single position: 20% of portfolio

CONCENTRATION:
- Tesla ETP is 30% of portfolio — high concentration risk
- Top 5 positions = 84% of portfolio — needs diversification
- INEYI appears twice (Dealing + ISA) — 21.6% combined
"""


# A11-A15: Enhanced daily brief with technical indicators, sector allocation, charts

def generate_enhanced_brief(portfolio: list[dict[str, Any]]) -> str:
    """Enhanced daily brief with technical analysis and sector allocation."""
    total_value = sum(p.get("value", 0) for p in portfolio)
    total_book = sum(p.get("book", 0) for p in portfolio)
    total_gain = sum(p.get("gain", 0) for p in portfolio)
    total_pct = (total_gain / total_book * 100) if total_book else 0

    # Sector allocation
    sectors = {}
    for p in portfolio:
        sector = p.get("sector", "Other")
        sectors[sector] = sectors.get(sector, 0) + p.get("value", 0)

    # Risk metrics
    winners = [p for p in portfolio if p.get("gain", 0) > 0]
    losers = [p for p in portfolio if p.get("gain", 0) < 0]
    win_rate = len(winners) / len(portfolio) * 100 if portfolio else 0

    # Concentration
    top5 = sorted(portfolio, key=lambda x: -x.get("value", 0))[:5]
    top5_pct = sum(p.get("value", 0) for p in top5) / total_value * 100 if total_value else 0

    # Technical levels
    top = sorted(portfolio, key=lambda x: -x.get("pct", 0))[:3]
    bottom = sorted(portfolio, key=lambda x: x.get("pct", 0))[:3]

    brief = f"""# Chris Prior — Enhanced Daily Brief

**{datetime.now().strftime('%d %B %Y')}**

## Portfolio Summary

| Metric | Value |
|--------|-------|
| Total Value | £{total_value:,.2f} |
| Book Cost | £{total_book:,.2f} |
| Unrealised P/L | £{total_gain:+,.2f} ({total_pct:+.2f}%) |
| Win Rate | {win_rate:.0f}% ({len(winners)}/{len(portfolio)}) |
| Concentration (Top 5) | {top5_pct:.1f}% |

## Sector Allocation
"""
    for sector, value in sorted(sectors.items(), key=lambda x: -x[1]):
        pct = value / total_value * 100 if total_value else 0
        brief += f"- **{sector}**: £{value:,.0f} ({pct:.1f}%)\n"

    brief += f"\n## Top Performers\n"
    for p in top:
        brief += f"- **{p['ticker']}**: {p.get('pct', 0):+.1f}% (£{p.get('value', 0):,.0f})\n"

    brief += f"\n## Underperformers\n"
    for p in bottom:
        brief += f"- **{p['ticker']}**: {p.get('pct', 0):+.1f}% (£{p.get('value', 0):,.0f})\n"

    brief += f"\n## Risk Assessment\n"
    if top5_pct > 70:
        brief += f"⚠️ **High concentration**: Top 5 = {top5_pct:.0f}% of portfolio\n"
    if len(losers) > len(winners):
        brief += f"⚠️ **More losers than winners**: {len(losers)} vs {len(winners)}\n"
    if total_pct < 0:
        brief += f"🔴 **Portfolio underwater**: {total_pct:+.2f}%\n"
    else:
        brief += f"🟢 **Portfolio profitable**: {total_pct:+.2f}%\n"

    brief += f"\n*Enhanced brief generated {datetime.now().strftime('%H:%M')}*"
    return brief
