# Northstar: AI Trading Sequence Engine

## Core Concept

The AI maintains a **sequence of buy/sell recommendations** for each stock. At each price update, it increases or decreases confidence based on:
1. Technical signals (price action, levels, momentum)
2. Backtested historical performance
3. Fundamental analysis (earnings, news, macro)
4. Current regime (bull/bear/range)

**Output**: "SELL 50% here" or "BUY back at X" — with a confidence multiplier (0-1) that determines position sizing.

---

## The Sequence Logic

```
PRICE UPDATE → AI ANALYZES → CONFIDENCE CHANGES → POSITION SIZES ADJUST

Example sequence for MPAL:
  Step 1: BUY 100% at 3.70 (confidence: 0.9)
  Step 2: HOLD (confidence: 0.8)
  Step 3: SELL 50% at 7.00 (confidence: 0.7) ← dad sold here
  Step 4: HOLD remaining 50% (confidence: 0.6)
  Step 5: BUY back 30% at 5.50 (confidence: 0.5) ← if support holds
  Step 6: SELL 100% at 8.00 (confidence: 0.4) ← if target hit
```

---

## Confidence Multiplier

```
Position Size = Base Size × Confidence Multiplier

Confidence 0.9-1.0 → Multiplier 1.0 → Full position
Confidence 0.7-0.9 → Multiplier 0.7 → 70% position
Confidence 0.5-0.7 → Multiplier 0.5 → 50% position
Confidence 0.3-0.5 → Multiplier 0.3 → 30% position
Confidence <0.3   → Multiplier 0.0 → No trade
```

---

## How Confidence Updates

At each price tick:

```text
IF price near support AND momentum positive:
    confidence += 0.05 (up to max 1.0)
    
IF price near resistance AND momentum negative:
    confidence -= 0.05 (down to min 0.0)
    
IF regime matches strategy:
    confidence += 0.1
    
IF macro favorable:
    confidence += 0.05
    
IF fundamentals strong:
    confidence += 0.05
```

---

## Backtest Validation

For each historical period:
1. Run the sequence engine
2. Record all buy/sell recommendations with confidence
3. Check: did the AI make money?
4. Calculate: what % of recommendations were correct?
5. Use this to calibrate confidence multipliers

**Key metric**: Average confidence of correct trades vs incorrect trades.

If correct trades have avg confidence 0.7 and incorrect have 0.4, the system is working.
