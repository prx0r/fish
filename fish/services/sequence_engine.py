"""Trading Sequence Engine — AI maintains buy/sell sequence with confidence.

The AI doesn't just give a single signal. It maintains a running sequence
of recommendations that update as price changes. Each recommendation has
a confidence that determines position sizing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SequenceStep:
    """One step in the trading sequence."""
    action: str  # BUY, SELL, HOLD
    price: float
    pct: float  # % of position to trade (0-100)
    confidence: float  # 0-1
    reasoning: str
    timestamp: str


@dataclass
class TradingSequence:
    """AI's current sequence of recommendations for a stock."""
    ticker: str
    steps: list[SequenceStep] = field(default_factory=list)
    current_step: int = 0
    position_pct: float = 100.0  # Current position as % of portfolio


def calculate_confidence(
    price: float,
    support: float,
    resistance: float,
    momentum: float,
    regime: str,
    fundamentals: float,
    macro: float,
    backtest_score: float,
) -> float:
    """Calculate confidence based on multiple factors."""
    confidence = 0.5  # Base
    
    # Price position
    if support > 0:
        dist_to_support = (price - support) / support
        if dist_to_support < 0.02:  # Near support
            confidence += 0.15
        elif dist_to_support < 0.05:
            confidence += 0.1
    
    if resistance > 0:
        dist_to_resistance = (resistance - price) / price
        if dist_to_resistance < 0.02:  # Near resistance
            confidence -= 0.15
        elif dist_to_resistance < 0.05:
            confidence -= 0.1
    
    # Momentum
    if momentum > 0.02:
        confidence += 0.1
    elif momentum < -0.02:
        confidence -= 0.1
    
    # Regime
    if regime == "BULL":
        confidence += 0.05
    elif regime == "BEAR":
        confidence -= 0.05
    
    # Fundamentals
    confidence += fundamentals * 0.1
    
    # Macro
    confidence += macro * 0.05
    
    # Backtest
    confidence += backtest_score * 0.1
    
    return max(0.0, min(1.0, confidence))


def confidence_to_multiplier(confidence: float) -> float:
    """Convert confidence to position size multiplier."""
    if confidence >= 0.9:
        return 1.0
    elif confidence >= 0.7:
        return 0.7
    elif confidence >= 0.5:
        return 0.5
    elif confidence >= 0.3:
        return 0.3
    else:
        return 0.0


def generate_sequence(
    ticker: str,
    prices: list[dict],
    support: float,
    resistance: float,
    regime: str,
    fundamentals: float = 0.5,
    macro: float = 0.5,
    backtest_score: float = 0.5,
) -> TradingSequence:
    """Generate a trading sequence for a stock."""
    sequence = TradingSequence(ticker=ticker)
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    dates = [p.get("date", "") for p in prices]
    
    for i in range(len(prices)):
        price = closes[i]
        
        # Calculate momentum
        if i >= 5:
            momentum = (closes[i] - closes[i-5]) / closes[i-5]
        else:
            momentum = 0
        
        # Calculate confidence
        confidence = calculate_confidence(
            price, support, resistance, momentum, regime, fundamentals, macro, backtest_score
        )
        
        # Determine action based on confidence and price position
        if confidence >= 0.7 and price < support * 1.05:
            action = "BUY"
            pct = confidence * 100
        elif confidence <= 0.3 and price > resistance * 0.95:
            action = "SELL"
            pct = (1 - confidence) * 100
        else:
            action = "HOLD"
            pct = 0
        
        # Create step
        step = SequenceStep(
            action=action,
            price=price,
            pct=round(pct, 1),
            confidence=round(confidence, 3),
            reasoning=f"Confidence: {confidence:.2f}, momentum: {momentum:+.2%}, regime: {regime}",
            timestamp=prices[i]["date"],
        )
        sequence.steps.append(step)
    
    # Find optimal entry/exit points
    buy_steps = [s for s in sequence.steps if s.action == "BUY" and s.confidence >= 0.7]
    sell_steps = [s for s in sequence.steps if s.action == "SELL" and s.confidence <= 0.3]
    
    return sequence
