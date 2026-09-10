"""Rebalancing engine — suggests trades to restore target allocation.

When portfolio drifts > threshold, suggest trims/adds to get back to target.
Compares against buy-and-hold benchmark.
"""
from __future__ import annotations

import json
from typing import Any

from fish.models import Watchlist
from fish.services.backtest_game import get_price_at, HISTORICAL_PRICES


# Chris Prior's target allocation (by sector, % of portfolio)
TARGET_ALLOCATION = {
    "technology": 35,    # TSLA, META, NBIS, COHR
    "healthcare": 10,    # MPAL, COLL, IRWD
    "finance": 30,       # AJGII, INEYI, MAN, INEYI_ISA
    "consumer": 15,      # TSCO, JDW, ACCO
    "energy": 5,         # PBI
    "other": 5,          # DHX, PGEN, BT.A, IAG
}

# Rebalancing thresholds
DRIFT_THRESHOLD = 5.0  # % drift before suggesting rebalance
MIN_TRADE_SIZE = 500   # Don't trade if < £500


def get_current_allocation(positions: list[dict]) -> dict[str, float]:
    """Calculate current sector allocation."""
    total = sum(p.get("value", 0) for p in positions)
    if total == 0:
        return {}
    
    sectors = {}
    for p in positions:
        sector = p.get("sector", "other")
        sectors[sector] = sectors.get(sector, 0) + p.get("value", 0)
    
    return {s: v / total * 100 for s, v in sectors.items()}


def calculate_drift(current: dict[str, float], target: dict[str, float]) -> dict[str, float]:
    """Calculate drift from target allocation."""
    drift = {}
    all_sectors = set(list(current.keys()) + list(target.keys()))
    for sector in all_sectors:
        curr = current.get(sector, 0)
        tgt = target.get(sector, 0)
        drift[sector] = curr - tgt
    return drift


def suggest_rebalance(positions: list[dict], target: dict[str, float]) -> list[dict[str, Any]]:
    """Suggest trades to restore target allocation."""
    current = get_current_allocation(positions)
    drift = calculate_drift(current, target)
    
    total_value = sum(p.get("value", 0) for p in positions)
    suggestions = []
    
    for sector, drift_pct in drift.items():
        if abs(drift_pct) < DRIFT_THRESHOLD:
            continue
        
        # Find positions in this sector
        sector_positions = [p for p in positions if p.get("sector") == sector]
        
        if drift_pct > 0:
            # Overweight — suggest trimming
            # Trim the biggest winner
            if sector_positions:
                biggest = max(sector_positions, key=lambda p: p.get("pct", 0))
                trim_value = total_value * drift_pct / 100
                if trim_value >= MIN_TRADE_SIZE:
                    suggestions.append({
                        "action": "TRIM",
                        "ticker": biggest["ticker"],
                        "reason": f"{sector} overweight by {drift_pct:.1f}%",
                        "estimated_value": round(trim_value),
                        "priority": "high" if abs(drift_pct) > 10 else "medium",
                    })
        elif drift_pct < 0:
            # Underweight — suggest adding
            if sector_positions:
                cheapest = min(sector_positions, key=lambda p: p.get("pct", 0))
                add_value = total_value * abs(drift_pct) / 100
                if add_value >= MIN_TRADE_SIZE:
                    suggestions.append({
                        "action": "ADD",
                        "ticker": cheapest["ticker"],
                        "reason": f"{sector} underweight by {abs(drift_pct):.1f}%",
                        "estimated_value": round(add_value),
                        "priority": "high" if abs(drift_pct) > 10 else "medium",
                    })
    
    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: priority_order.get(s["priority"], 3))
    
    return suggestions
