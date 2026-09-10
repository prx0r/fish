"""Trading signals with confidence-based position sizing.

Based on BEAR's signal schema + fleece's trader patterns.

Confidence → Position Size:
  HIGH (0.8-1.0)   → Full position (100% of allocated capital)
  MEDIUM (0.5-0.8) → Half position (50% of allocated capital)
  LOW (0.2-0.5)    → Quarter position (25% of allocated capital)
  VERY LOW (<0.2)  → No trade
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class Confidence(str, Enum):
    HIGH = "high"        # 0.8-1.0
    MEDIUM = "medium"    # 0.5-0.8
    LOW = "low"          # 0.2-0.5
    VERY_LOW = "very_low"  # <0.2


class SignalType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    UPDATE = "update"
    TRIM = "trim"
    ADD = "add"


@dataclass
class TradingSignal:
    """A structured trading signal with confidence-based sizing."""
    ticker: str
    direction: Direction
    signal_type: SignalType
    confidence: float  # 0.0-1.0
    reasoning: str
    
    # Position sizing
    position_pct: float = 0.0  # % of allocated capital
    allocated_capital: float = 0.0  # £ to trade
    
    # Price levels
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Metadata
    source: str = "ai"
    timeframe: str = "1D"


def confidence_to_position(confidence: float, allocated_capital: float) -> float:
    """Convert confidence to position size (% of allocated capital)."""
    if confidence >= 0.8:
        return allocated_capital * 1.0   # Full position
    elif confidence >= 0.5:
        return allocated_capital * 0.5   # Half position
    elif confidence >= 0.2:
        return allocated_capital * 0.25  # Quarter position
    else:
        return 0.0  # No trade


def confidence_to_label(confidence: float) -> str:
    """Convert confidence to human-readable label."""
    if confidence >= 0.8:
        return "HIGH"
    elif confidence >= 0.5:
        return "MEDIUM"
    elif confidence >= 0.2:
        return "LOW"
    else:
        return "VERY LOW"


def generate_signal(
    ticker: str,
    action: str,
    confidence: float,
    reasoning: str,
    entry: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    allocated_capital: float = 10000,
) -> TradingSignal:
    """Generate a trading signal with confidence-based sizing."""
    direction = Direction.LONG if action in ("BUY", "ADD") else Direction.SHORT if action in ("SELL", "TRIM") else Direction.NEUTRAL
    signal_type = SignalType(action.lower()) if action.lower() in [s.value for s in SignalType] else SignalType.ENTRY
    
    position_pct = confidence_to_position(confidence, allocated_capital)
    
    return TradingSignal(
        ticker=ticker,
        direction=direction,
        signal_type=signal_type,
        confidence=confidence,
        reasoning=reasoning,
        position_pct=position_pct,
        allocated_capital=allocated_capital,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
