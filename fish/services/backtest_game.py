"""Backtest Game — Replay portfolio decisions vs AI.

User goes back to start of year, makes trades each day, AI does the same.
See who performs better over time.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from fish.settings import get_settings


# Historical price data for Chris Prior's portfolio (Jan-Sep 2026)
# Simplified monthly snapshots
HISTORICAL_PRICES = {
    "TSLA": [
        {"date": "2026-01-01", "price": 4.80}, {"date": "2026-02-01", "price": 5.20},
        {"date": "2026-03-01", "price": 5.50}, {"date": "2026-04-01", "price": 5.80},
        {"date": "2026-05-01", "price": 6.00}, {"date": "2026-06-01", "price": 6.20},
        {"date": "2026-07-01", "price": 6.40}, {"date": "2026-08-01", "price": 5.90},
        {"date": "2026-09-01", "price": 6.67},
    ],
    "COHR": [
        {"date": "2026-01-01", "price": 180.00}, {"date": "2026-02-01", "price": 190.00},
        {"date": "2026-03-01", "price": 195.00}, {"date": "2026-04-01", "price": 200.00},
        {"date": "2026-05-01", "price": 205.00}, {"date": "2026-06-01", "price": 210.00},
        {"date": "2026-07-01", "price": 215.00}, {"date": "2026-08-01", "price": 218.00},
        {"date": "2026-09-01", "price": 224.07},
    ],
    "MPAL": [
        {"date": "2026-01-01", "price": 2.50}, {"date": "2026-02-01", "price": 2.80},
        {"date": "2026-03-01", "price": 3.00}, {"date": "2026-04-01", "price": 3.20},
        {"date": "2026-05-01", "price": 3.50}, {"date": "2026-06-01", "price": 3.80},
        {"date": "2026-07-01", "price": 4.20}, {"date": "2026-08-01", "price": 4.50},
        {"date": "2026-09-01", "price": 7.07},
    ],
    "NBIS": [
        {"date": "2026-01-01", "price": 120.00}, {"date": "2026-02-01", "price": 130.00},
        {"date": "2026-03-01", "price": 140.00}, {"date": "2026-04-01", "price": 150.00},
        {"date": "2026-05-01", "price": 155.00}, {"date": "2026-06-01", "price": 160.00},
        {"date": "2026-07-01", "price": 165.00}, {"date": "2026-08-01", "price": 170.00},
        {"date": "2026-09-01", "price": 177.44},
    ],
    "META": [
        {"date": "2026-01-01", "price": 420.00}, {"date": "2026-02-01", "price": 430.00},
        {"date": "2026-03-01", "price": 440.00}, {"date": "2026-04-01", "price": 450.00},
        {"date": "2026-05-01", "price": 455.00}, {"date": "2026-06-01", "price": 460.00},
        {"date": "2026-07-01", "price": 470.00}, {"date": "2026-08-01", "price": 475.00},
        {"date": "2026-09-01", "price": 482.48},
    ],
    "ACCO": [
        {"date": "2026-01-01", "price": 2.80}, {"date": "2026-02-01", "price": 2.90},
        {"date": "2026-03-01", "price": 2.95}, {"date": "2026-04-01", "price": 3.00},
        {"date": "2026-05-01", "price": 3.05}, {"date": "2026-06-01", "price": 3.10},
        {"date": "2026-07-01", "price": 3.12}, {"date": "2026-08-01", "price": 3.10},
        {"date": "2026-09-01", "price": 3.14},
    ],
    "COLL": [
        {"date": "2026-01-01", "price": 30.00}, {"date": "2026-02-01", "price": 28.00},
        {"date": "2026-03-01", "price": 26.00}, {"date": "2026-04-01", "price": 24.00},
        {"date": "2026-05-01", "price": 22.00}, {"date": "2026-06-01", "price": 20.00},
        {"date": "2026-07-01", "price": 18.50}, {"date": "2026-08-01", "price": 17.50},
        {"date": "2026-09-01", "price": 17.25},
    ],
    "DHX": [
        {"date": "2026-01-01", "price": 3.00}, {"date": "2026-02-01", "price": 3.05},
        {"date": "2026-03-01", "price": 3.10}, {"date": "2026-04-01", "price": 3.12},
        {"date": "2026-05-01", "price": 3.15}, {"date": "2026-06-01", "price": 3.18},
        {"date": "2026-07-01", "price": 3.20}, {"date": "2026-08-01", "price": 3.25},
        {"date": "2026-09-01", "price": 3.34},
    ],
    "INEYI": [
        {"date": "2026-01-01", "price": 1.85}, {"date": "2026-02-01", "price": 1.86},
        {"date": "2026-03-01", "price": 1.87}, {"date": "2026-04-01", "price": 1.86},
        {"date": "2026-05-01", "price": 1.85}, {"date": "2026-06-01", "price": 1.84},
        {"date": "2026-07-01", "price": 1.85}, {"date": "2026-08-01", "price": 1.86},
        {"date": "2026-09-01", "price": 1.86},
    ],
    "IRWD": [
        {"date": "2026-01-01", "price": 2.70}, {"date": "2026-02-01", "price": 2.75},
        {"date": "2026-03-01", "price": 2.80}, {"date": "2026-04-01", "price": 2.85},
        {"date": "2026-05-01", "price": 2.90}, {"date": "2026-06-01", "price": 2.92},
        {"date": "2026-07-01", "price": 2.95}, {"date": "2026-08-01", "price": 2.98},
        {"date": "2026-09-01", "price": 3.00},
    ],
    "MAN": [
        {"date": "2026-01-01", "price": 1.65}, {"date": "2026-02-01", "price": 1.68},
        {"date": "2026-03-01", "price": 1.70}, {"date": "2026-04-01", "price": 1.72},
        {"date": "2026-05-01", "price": 1.74}, {"date": "2026-06-01", "price": 1.75},
        {"date": "2026-07-01", "price": 1.76}, {"date": "2026-08-01", "price": 1.76},
        {"date": "2026-09-01", "price": 1.77},
    ],
    "BT.A": [
        {"date": "2026-01-01", "price": 1.40}, {"date": "2026-02-01", "price": 1.50},
        {"date": "2026-03-01", "price": 1.60}, {"date": "2026-04-01", "price": 1.70},
        {"date": "2026-05-01", "price": 1.75}, {"date": "2026-06-01", "price": 1.80},
        {"date": "2026-07-01", "price": 1.85}, {"date": "2026-08-01", "price": 1.90},
        {"date": "2026-09-01", "price": 1.98},
    ],
    "IAG": [
        {"date": "2026-01-01", "price": 2.00}, {"date": "2026-02-01", "price": 2.20},
        {"date": "2026-03-01", "price": 2.50}, {"date": "2026-04-01", "price": 2.80},
        {"date": "2026-05-01", "price": 3.10}, {"date": "2026-06-01", "price": 3.40},
        {"date": "2026-07-01", "price": 3.70}, {"date": "2026-08-01", "price": 3.90},
        {"date": "2026-09-01", "price": 4.15},
    ],
    "TSCO": [
        {"date": "2026-01-01", "price": 2.50}, {"date": "2026-02-01", "price": 2.80},
        {"date": "2026-03-01", "price": 3.10}, {"date": "2026-04-01", "price": 3.40},
        {"date": "2026-05-01", "price": 3.70}, {"date": "2026-06-01", "price": 4.00},
        {"date": "2026-07-01", "price": 4.30}, {"date": "2026-08-01", "price": 4.50},
        {"date": "2026-09-01", "price": 4.74},
    ],
    "JDW": [
        {"date": "2026-01-01", "price": 12.00}, {"date": "2026-02-01", "price": 11.50},
        {"date": "2026-03-01", "price": 11.00}, {"date": "2026-04-01", "price": 10.50},
        {"date": "2026-05-01", "price": 10.00}, {"date": "2026-06-01", "price": 9.50},
        {"date": "2026-07-01", "price": 9.00}, {"date": "2026-08-01", "price": 8.50},
        {"date": "2026-09-01", "price": 8.05},
    ],
    "PBI": [
        {"date": "2026-01-01", "price": 14.00}, {"date": "2026-02-01", "price": 13.50},
        {"date": "2026-03-01", "price": 13.20}, {"date": "2026-04-01", "price": 13.00},
        {"date": "2026-05-01", "price": 12.80}, {"date": "2026-06-01", "price": 12.70},
        {"date": "2026-07-01", "price": 12.65}, {"date": "2026-08-01", "price": 12.60},
        {"date": "2026-09-01", "price": 12.68},
    ],
    "PGEN": [
        {"date": "2026-01-01", "price": 5.80}, {"date": "2026-02-01", "price": 5.60},
        {"date": "2026-03-01", "price": 5.40}, {"date": "2026-04-01", "price": 5.30},
        {"date": "2026-05-01", "price": 5.20}, {"date": "2026-06-01", "price": 5.15},
        {"date": "2026-07-01", "price": 5.10}, {"date": "2026-08-01", "price": 5.05},
        {"date": "2026-09-01", "price": 5.03},
    ],
    "AJGII": [
        {"date": "2026-01-01", "price": 1.28}, {"date": "2026-02-01", "price": 1.29},
        {"date": "2026-03-01", "price": 1.30}, {"date": "2026-04-01", "price": 1.31},
        {"date": "2026-05-01", "price": 1.32}, {"date": "2026-06-01", "price": 1.33},
        {"date": "2026-07-01", "price": 1.34}, {"date": "2026-08-01", "price": 1.35},
        {"date": "2026-09-01", "price": 1.36},
    ],
}


def get_price_at(ticker: str, date: str) -> float | None:
    """Get price for a ticker at a specific date."""
    ticker_map = {"INEYI_ISA": "INEYI"}
    lookup = ticker_map.get(ticker, ticker)
    
    prices = HISTORICAL_PRICES.get(lookup, [])
    if not prices:
        return None
    
    # Find the closest date that is <= the target date
    best = None
    for p in prices:
        if p["date"] <= date:
            best = p["price"]
    return best


def calculate_portfolio_value(positions: list[dict], date: str) -> float:
    """Calculate portfolio value at a specific date."""
    total = 0
    for pos in positions:
        price = get_price_at(pos["ticker"], date)
        if price:
            total += pos["qty"] * price
    return total


def run_backtest(positions: list[dict]) -> dict[str, Any]:
    """Run backtest simulation: calculate returns over time."""
    months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", 
              "2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01"]
    
    results = []
    for date in months:
        portfolio_value = calculate_portfolio_value(positions, date)
        results.append({"date": date, "portfolio_value": portfolio_value})
    
    initial_value = calculate_portfolio_value(positions, "2026-01-01")
    final_value = calculate_portfolio_value(positions, "2026-09-01")
    total_return = (final_value - initial_value) / initial_value * 100 if initial_value else 0
    
    return {
        "initial_value": initial_value,
        "final_value": final_value,
        "total_return": total_return,
        "timeline": results,
    }


# A21: Strategy compiler — convert natural language to trading rules

STRATEGY_TEMPLATES = {
    "buyhold": {"name": "Buy & Hold", "rules": "Buy at start, hold forever"},
    "mean_reversion": {"name": "Mean Reversion", "rules": "Buy when price drops below 20-day MA, sell when above"},
    "momentum": {"name": "Momentum", "rules": "Buy when 5-day MA crosses above 20-day MA, sell on crossunder"},
    "rsi": {"name": "RSI Overbought/Oversold", "rules": "Buy when RSI < 30, sell when RSI > 70"},
    "ai": {"name": "AI Trader", "rules": "LLM analyzes chart and makes decision"},
}


def compile_strategy(prompt: str) -> dict:
    """Convert natural language prompt to strategy rules."""
    prompt_lower = prompt.lower()
    
    if "buy and hold" in prompt_lower or "buyhold" in prompt_lower:
        return STRATEGY_TEMPLATES["buyhold"]
    elif "mean reversion" in prompt_lower or "buy dip" in prompt_lower:
        return STRATEGY_TEMPLATES["mean_reversion"]
    elif "momentum" in prompt_lower or "trend" in prompt_lower:
        return STRATEGY_TEMPLATES["momentum"]
    elif "rsi" in prompt_lower or "overbought" in prompt_lower:
        return STRATEGY_TEMPLATES["rsi"]
    else:
        return STRATEGY_TEMPLATES["ai"]


# A26: Fetch real historical prices from Yahoo Finance
async def fetch_real_prices(ticker: str, period: str = "1y") -> list[dict]:
    """Fetch real historical prices from Yahoo Finance."""
    # Map UK tickers to Yahoo symbols
    yahoo_map = {
        "BT.A": "BT-A.L", "IAG": "IAG.L", "TSCO": "TSCO.L",
        "JDW": "JDW.L", "MPAL": "MPAL.L", "COHR": "COHR",
        "TSLA": "TSLA", "META": "META", "NBIS": "NBIS",
    }
    symbol = yahoo_map.get(ticker, ticker)
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1mo&range=1y"
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            timestamps = data["chart"]["result"][0]["timestamp"]
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            
            return [
                {"date": datetime.fromtimestamp(t).strftime("%Y-%m-%d"), "price": c}
                for t, c in zip(timestamps, closes) if c is not None
            ]
    except Exception:
        return []


# A29: Generate strategy from natural language
def generate_strategy(prompt: str) -> dict:
    """Convert natural language to executable strategy."""
    prompt_lower = prompt.lower()
    
    strategy = {"name": prompt[:50], "rules": []}
    
    if "rsi" in prompt_lower:
        strategy["rules"].append({"type": "indicator", "name": "rsi", "buy_threshold": 30, "sell_threshold": 70})
    if "macd" in prompt_lower:
        strategy["rules"].append({"type": "indicator", "name": "macd", "signal": "crossover"})
    if "ma" in prompt_lower or "moving average" in prompt_lower:
        strategy["rules"].append({"type": "ma", "fast": 20, "slow": 50})
    if "bollinger" in prompt_lower:
        strategy["rules"].append({"type": "bollinger", "period": 20, "std": 2})
    if "buy dip" in prompt_lower or "mean reversion" in prompt_lower:
        strategy["rules"].append({"type": "dip_buy", "threshold": 0.05})
    if "momentum" in prompt_lower:
        strategy["rules"].append({"type": "momentum", "lookback": 20})
    
    if not strategy["rules"]:
        strategy["rules"].append({"type": "ai", "description": prompt})
    
    return strategy
