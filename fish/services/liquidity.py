"""Liquidity — First-Class State.

Every Fish state should include:
- spread (estimated from price data)
- ADV (average daily volume)
- dollar volume
- Amihud illiquidity
- turnover
- realized volatility
- gap risk
- expected impact
- participation rate

Every backtest result needs:
PnL_net = PnL_gross - spread - fees - slippage - impact

This prevents the classic problem:
huge paper alpha → concentrated in illiquid stocks → huge spread/impact → little/no executable alpha
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LiquidityState:
    """Liquidity state for a stock."""
    ticker: str
    adv: float  # Average daily volume (shares)
    dollar_adv: float  # Average daily dollar volume
    amihud_illiquidity: float  # Amihud ratio (high = illiquid)
    estimated_spread_bps: float  # Estimated bid-ask spread in basis points
    estimated_impact_bps: float  # Estimated market impact in basis points
    turnover_rate: float  # Daily turnover rate
    realized_vol: float  # Realized volatility (annualized)
    gap_risk: float  # Average absolute overnight gap
    participation_rate: float  # Max participation rate (10% of ADV)
    liquidity_score: float  # 0-100 (100 = most liquid)
    tier: str  # "A", "B", "C", "D" (A = most liquid)


def calculate_liquidity(
    prices: list[dict],
    ticker: str,
    lookback: int = 20,
) -> LiquidityState:
    """Calculate liquidity state from price data."""
    if not prices or len(prices) < lookback:
        return LiquidityState(
            ticker=ticker, adv=0, dollar_adv=0, amihud_illiquidity=0,
            estimated_spread_bps=0, estimated_impact_bps=0, turnover_rate=0,
            realized_vol=0, gap_risk=0, participation_rate=0,
            liquidity_score=0, tier="D",
        )
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    volumes = [p.get("volume", 1000000) for p in prices]
    
    # ADV (average daily volume)
    recent_volumes = volumes[-lookback:]
    adv = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1000000
    
    # Dollar ADV
    recent_closes = closes[-lookback:]
    avg_price = sum(recent_closes) / len(recent_closes) if recent_closes else 100
    dollar_adv = adv * avg_price
    
    # Amihud illiquidity ratio
    # |return| / dollar_volume (high = illiquid)
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    recent_returns = returns[-lookback:]
    recent_dollar_volumes = [volumes[i] * closes[i] for i in range(1, len(closes))]
    recent_dollar_volumes = recent_dollar_volumes[-lookback:]
    
    amihud_vals = []
    for r, dv in zip(recent_returns, recent_dollar_volumes):
        if dv > 0:
            amihud_vals.append(abs(r) / dv)
    amihud_illiquidity = sum(amihud_vals) / len(amihud_vals) if amihud_vals else 0
    
    # Estimated spread (from Amihud and volatility)
    # Higher illiquidity = wider spread
    realized_vol = math.sqrt(sum((r - sum(recent_returns)/len(recent_returns))**2 
                                for r in recent_returns) / len(recent_returns)) * math.sqrt(252) if recent_returns else 0
    
    # Spread estimation (simplified)
    base_spread = 5  # 5 bps for liquid stocks
    vol_adjustment = realized_vol * 10  # Wider spreads in high vol
    size_adjustment = 1000000 / adv if adv > 0 else 1  # Wider for small volume
    estimated_spread_bps = base_spread + vol_adjustment + min(size_adjustment, 50)
    
    # Market impact (simplified)
    # Impact = spread/2 + volatility impact
    estimated_impact_bps = estimated_spread_bps / 2 + realized_vol * 5
    
    # Turnover rate
    turnover_rate = adv / 1000000  # Assuming 1M shares outstanding for simplicity
    
    # Gap risk (average absolute overnight gap)
    gaps = []
    for i in range(1, len(closes)):
        gap = abs((closes[i] - closes[i-1]) / closes[i-1])
        gaps.append(gap)
    gap_risk = sum(gaps[-lookback:]) / len(gaps[-lookback:]) if gaps else 0
    
    # Participation rate (max 10% of ADV without moving price)
    participation_rate = adv * 0.1
    
    # Liquidity score (0-100)
    # Higher is better (more liquid)
    score = 0
    
    # ADV component (higher = better)
    if adv > 10000000:
        score += 30
    elif adv > 1000000:
        score += 20
    elif adv > 100000:
        score += 10
    
    # Dollar ADV component
    if dollar_adv > 100000000:
        score += 30
    elif dollar_adv > 10000000:
        score += 20
    elif dollar_adv > 1000000:
        score += 10
    
    # Spread component (lower = better)
    if estimated_spread_bps < 10:
        score += 20
    elif estimated_spread_bps < 20:
        score += 10
    
    # Volatility component (lower = better)
    if realized_vol < 0.20:
        score += 20
    elif realized_vol < 0.40:
        score += 10
    
    # Tier assignment
    if score >= 80:
        tier = "A"
    elif score >= 60:
        tier = "B"
    elif score >= 40:
        tier = "C"
    else:
        tier = "D"
    
    return LiquidityState(
        ticker=ticker,
        adv=adv,
        dollar_adv=dollar_adv,
        amihud_illiquidity=amihud_illiquidity,
        estimated_spread_bps=estimated_spread_bps,
        estimated_impact_bps=estimated_impact_bps,
        turnover_rate=turnover_rate,
        realized_vol=realized_vol,
        gap_risk=gap_risk,
        participation_rate=participation_rate,
        liquidity_score=score,
        tier=tier,
    )


def calculate_net_pnl(
    gross_pnl: float,
    trades: int,
    avg_trade_value: float,
    liquidity: LiquidityState,
    fee_bps: float = 5,
) -> float:
    """Calculate net PnL after costs.
    
    PnL_net = PnL_gross - spread - fees - slippage - impact
    """
    # Spread cost (half spread per trade)
    spread_cost = trades * avg_trade_value * (liquidity.estimated_spread_bps / 2 / 10000)
    
    # Fee cost
    fee_cost = trades * avg_trade_value * (fee_bps / 10000)
    
    # Slippage (estimated)
    slippage_cost = trades * avg_trade_value * (liquidity.estimated_spread_bps / 4 / 10000)
    
    # Impact cost
    impact_cost = trades * avg_trade_value * (liquidity.estimated_impact_bps / 10000)
    
    total_costs = spread_cost + fee_cost + slippage_cost + impact_cost
    
    return gross_pnl - total_costs


def portfolio_liquidity_summary(
    positions: list[dict],
    prices: dict[str, list[dict]],
) -> dict:
    """Calculate liquidity summary for entire portfolio."""
    states = []
    for pos in positions:
        ticker = pos["ticker"]
        if ticker in prices:
            state = calculate_liquidity(prices[ticker], ticker)
            states.append(state)
    
    if not states:
        return {"avg_score": 0, "avg_tier": "D", "positions": []}
    
    avg_score = sum(s.liquidity_score for s in states) / len(states)
    
    # Count tiers
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in states:
        tier_counts[s.tier] += 1
    
    # Average tier
    tier_scores = {"A": 4, "B": 3, "C": 2, "D": 1}
    avg_tier_score = sum(tier_scores[s.tier] for s in states) / len(states)
    avg_tier = min(tier_scores, key=lambda t: abs(tier_scores[t] - avg_tier_score))
    
    return {
        "avg_score": round(avg_score, 1),
        "avg_tier": avg_tier,
        "tier_distribution": tier_counts,
        "positions": [
            {
                "ticker": s.ticker,
                "score": s.liquidity_score,
                "tier": s.tier,
                "adv": round(s.adv),
                "spread_bps": round(s.estimated_spread_bps, 1),
                "impact_bps": round(s.estimated_impact_bps, 1),
            }
            for s in states
        ],
    }
