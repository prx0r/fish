"""Simple trading signals: BUY or SELL at a level.

Internal: AI agents use stops, indicators, regimes
External: Human sees only BUY/SELL + price level + confidence
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    """A clean trading signal."""
    ticker: str
    action: str  # "BUY" or "SELL"
    level: float  # price level
    confidence: float  # 0-1
    reasoning: str
    source: str  # which agent generated this


def generate_signal(
    ticker: str,
    action: str,
    level: float,
    confidence: float,
    reasoning: str,
    source: str = "agent",
) -> Signal:
    """Generate a clean BUY/SELL signal."""
    return Signal(
        ticker=ticker,
        action=action.upper(),
        level=level,
        confidence=confidence,
        reasoning=reasoning,
        source=source,
    )
