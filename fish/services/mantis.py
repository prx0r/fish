"""Mantis — Microstructure / Execution Avatar.

Operates on milliseconds → hours.

Inputs:
- spread
- microprice
- L1 imbalance
- L5 imbalance
- L10 imbalance
- OFI
- MLOFI
- trade imbalance
- aggressor flow
- depth slope
- depth convexity
- cancel/add ratios
- queue age
- wall persistence
- volume bursts
- realized vol

Outputs:
- P(ΔMidPrice_1s > 0)
- P(ΔMidPrice_10s > 0)
- P(ΔMidPrice_1m > 0)
- expected move
- expected spread
- fill probability
- execution confidence

Job: Given that Turtle/Bull/Shark want to buy COHR, when exactly should we execute?
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class OrderBookState:
    """Snapshot of the order book at a point in time."""
    timestamp: str
    ticker: str
    
    # Bid side
    bid_price_1: float = 0.0
    bid_size_1: float = 0.0
    bid_price_2: float = 0.0
    bid_size_2: float = 0.0
    bid_price_3: float = 0.0
    bid_size_3: float = 0.0
    bid_price_5: float = 0.0
    bid_size_5: float = 0.0
    bid_price_10: float = 0.0
    bid_size_10: float = 0.0
    
    # Ask side
    ask_price_1: float = 0.0
    ask_size_1: float = 0.0
    ask_price_2: float = 0.0
    ask_size_2: float = 0.0
    ask_price_3: float = 0.0
    ask_size_3: float = 0.0
    ask_price_5: float = 0.0
    ask_size_5: float = 0.0
    ask_price_10: float = 0.0
    ask_size_10: float = 0.0
    
    # Trade flow
    trade_volume_1m: float = 0.0
    trade_volume_5m: float = 0.0
    buy_volume_1m: float = 0.0
    sell_volume_1m: float = 0.0
    
    # Derived features
    spread: float = 0.0
    midpoint: float = 0.0
    microprice: float = 0.0
    obi_1: float = 0.0
    obi_3: float = 0.0
    obi_5: float = 0.0
    obi_10: float = 0.0
    ofi: float = 0.0
    trade_imbalance: float = 0.0
    depth_slope: float = 0.0


@dataclass
class MantisSignal:
    """Mantis execution signal."""
    ticker: str
    timestamp: str
    
    # Price predictions
    p_up_1s: float = 0.5
    p_up_10s: float = 0.5
    p_up_1m: float = 0.5
    
    # Execution metrics
    expected_move: float = 0.0
    expected_spread: float = 0.0
    fill_probability: float = 0.5
    execution_confidence: float = 0.5
    
    # Optimal execution
    recommended_action: str = "WAIT"
    recommended_limit: float = 0.0
    recommended_size_pct: float = 0.0
    
    # Feature importance
    features: dict = field(default_factory=dict)


def compute_order_book_features(book: OrderBookState) -> OrderBookState:
    """Compute order book features from snapshot."""
    # Spread
    if book.bid_price_1 > 0 and book.ask_price_1 > 0:
        book.spread = book.ask_price_1 - book.bid_price_1
        book.midpoint = (book.bid_price_1 + book.ask_price_1) / 2
        
        # Microprice
        total_bid_size = book.bid_size_1
        total_ask_size = book.ask_size_1
        if total_bid_size + total_ask_size > 0:
            book.microprice = (
                book.ask_price_1 * total_bid_size + 
                book.bid_price_1 * total_ask_size
            ) / (total_bid_size + total_ask_size)
    
    # Order book imbalance
    if book.bid_size_1 + book.ask_size_1 > 0:
        book.obi_1 = (book.bid_size_1 - book.ask_size_1) / (book.bid_size_1 + book.ask_size_1)
    
    bid_size_3 = book.bid_size_1 + book.bid_size_2 + book.bid_size_3
    ask_size_3 = book.ask_size_1 + book.ask_size_2 + book.ask_size_3
    if bid_size_3 + ask_size_3 > 0:
        book.obi_3 = (bid_size_3 - ask_size_3) / (bid_size_3 + ask_size_3)
    
    bid_size_5 = bid_size_3 + book.bid_size_5
    ask_size_5 = ask_size_3 + book.ask_size_5
    if bid_size_5 + ask_size_5 > 0:
        book.obi_5 = (bid_size_5 - ask_size_5) / (bid_size_5 + ask_size_5)
    
    bid_size_10 = bid_size_5 + book.bid_size_10
    ask_size_10 = ask_size_5 + book.ask_size_10
    if bid_size_10 + ask_size_10 > 0:
        book.obi_10 = (bid_size_10 - ask_size_10) / (bid_size_10 + ask_size_10)
    
    # Trade imbalance
    total_trade = book.buy_volume_1m + book.sell_volume_1m
    if total_trade > 0:
        book.trade_imbalance = (book.buy_volume_1m - book.sell_volume_1m) / total_trade
    
    # Depth slope (simplified)
    if book.bid_price_1 > 0 and book.ask_price_1 > 0:
        bid_depth = book.bid_size_1 + book.bid_size_2 + book.bid_size_3
        ask_depth = book.ask_size_1 + book.ask_size_2 + book.ask_size_3
        mid = (book.bid_price_1 + book.ask_price_1) / 2
        if mid > 0:
            book.depth_slope = (bid_depth - ask_depth) / (bid_depth + ask_depth) if bid_depth + ask_depth > 0 else 0
    
    return book


def mantis_signal(
    book: OrderBookState,
    recent_books: list[OrderBookState] = None,
    realized_vol: float = 0.0,
) -> MantisSignal:
    """Generate Mantis execution signal from order book state."""
    book = compute_order_book_features(book)
    
    signal = MantisSignal(
        ticker=book.ticker,
        timestamp=book.timestamp,
    )
    
    # Simple heuristic model (to be replaced with ML)
    # P(up) based on order book features
    
    # Base: 50%
    p_up = 0.5
    
    # OBI contribution
    p_up += book.obi_1 * 0.1  # Strong L1 imbalance
    p_up += book.obi_3 * 0.05  # Moderate L3 imbalance
    
    # Microprice contribution
    if book.midpoint > 0:
        microprice_signal = (book.microprice - book.midpoint) / book.midpoint
        p_up += microprice_signal * 10  # Scale up
    
    # Trade imbalance contribution
    p_up += book.trade_imbalance * 0.1
    
    # Depth slope contribution
    p_up += book.depth_slope * 0.05
    
    # Clamp to [0.1, 0.9]
    p_up = max(0.1, min(0.9, p_up))
    
    signal.p_up_1s = p_up
    signal.p_up_10s = p_up * 0.9 + 0.05  # Decay toward 0.5
    signal.p_up_1m = p_up * 0.8 + 0.1
    
    # Expected move
    signal.expected_move = abs(p_up - 0.5) * book.spread * 2
    
    # Expected spread
    signal.expected_spread = book.spread
    
    # Fill probability (simplified)
    if p_up > 0.6:
        # Buying: higher fill prob if price drops
        signal.fill_probability = 1 - p_up
    elif p_up < 0.4:
        # Selling: higher fill prob if price rises
        signal.fill_probability = p_up
    else:
        signal.fill_probability = 0.5
    
    # Execution confidence
    signal.execution_confidence = abs(p_up - 0.5) * 2  # Higher when more certain
    
    # Recommended action
    if p_up > 0.65:
        signal.recommended_action = "BUY_NOW"
        signal.recommended_limit = book.midpoint
        signal.recommended_size_pct = min(0.3, signal.execution_confidence)
    elif p_up < 0.35:
        signal.recommended_action = "SELL_NOW"
        signal.recommended_limit = book.midpoint
        signal.recommended_size_pct = min(0.3, signal.execution_confidence)
    else:
        signal.recommended_action = "WAIT"
        signal.recommended_limit = 0
        signal.recommended_size_pct = 0
    
    # Feature importance
    signal.features = {
        "obi_1": book.obi_1,
        "obi_3": book.obi_3,
        "microprice": book.microprice,
        "trade_imbalance": book.trade_imbalance,
        "depth_slope": book.depth_slope,
        "spread": book.spread,
    }
    
    return signal


def optimal_execution_strategy(
    book: OrderBookState,
    target_size: float,
    side: str = "buy",
    urgency: float = 0.5,
) -> list[dict]:
    """Generate optimal execution strategy.
    
    Returns list of limit orders with sizes and prices.
    """
    book = compute_order_book_features(book)
    
    if side == "buy":
        # Buy: place limits below ask
        base_price = book.bid_price_1
        spread = book.spread
    else:
        # Sell: place limits above bid
        base_price = book.ask_price_1
        spread = book.spread
    
    # Split into tranches
    tranches = []
    remaining = target_size
    
    # Tranche 1: Aggressive (near spread)
    t1_size = target_size * 0.3 * urgency
    t1_price = base_price + (spread * 0.1 if side == "buy" else -spread * 0.1)
    tranches.append({
        "limit": round(t1_price, 2),
        "size_pct": round(t1_size / target_size * 100, 1) if target_size > 0 else 0,
        "fill_prob": 0.7 if side == "buy" else 0.7,
    })
    remaining -= t1_size
    
    # Tranche 2: Patient (middle of spread)
    t2_size = target_size * 0.4
    t2_price = base_price + (spread * 0.3 if side == "buy" else -spread * 0.3)
    tranches.append({
        "limit": round(t2_price, 2),
        "size_pct": round(t2_size / target_size * 100, 1) if target_size > 0 else 0,
        "fill_prob": 0.4 if side == "buy" else 0.4,
    })
    remaining -= t2_size
    
    # Tranche 3: Very patient (deep in book)
    t3_size = remaining
    t3_price = base_price + (spread * 0.6 if side == "buy" else -spread * 0.6)
    tranches.append({
        "limit": round(t3_price, 2),
        "size_pct": round(t3_size / target_size * 100, 1) if target_size > 0 else 0,
        "fill_prob": 0.15 if side == "buy" else 0.15,
    })
    
    return tranches
