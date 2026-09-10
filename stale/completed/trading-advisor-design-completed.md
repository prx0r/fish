# Trading Advisor — Design Doc

**Purpose**: Chat with an agent that reasons over the knowledge graph to give trading advice.

---

## Architecture

```
USER (Chris Prior)
    │
    ▼
DAILY BRIEF (auto-generated, high-level)
    │
    ▼
CHAT INTERFACE (ask anything)
    │
    ▼
AGENT REASONS OVER:
  ├── Knowledge graph (7,120 objects, 5,685 edges)
  ├── Stock watchlist (entry, stop, target, thesis)
  ├── Convergence signals (multi-author, same topic)
  ├── Predictions (with evidence)
  ├── Scarcity chains (bottleneck migration)
  ├── Technical levels (support/resistance)
  └── Trading theory (price action, volume, patterns)
    │
    ▼
RESPONSE (backed by graph, not LLM internal knowledge)
    │
    ▼
SAVED TO MEMORY (next chat loads this context)
```

---

## The Key Insight

The LLM should NOT answer from its training data. It should answer from:
1. What the knowledge graph says
2. What the stock data shows
3. What trading theory dictates

The graph is the source of truth. The LLM is the reasoning engine.

---

## Daily Brief Format

```
# MPAL Daily — Sep 10, 2026

Price: 6.64 GBX (-0.9%)
Volume: 44.5M (elevated)

🟢 SIGNAL: EBITDA breakeven target Oct-Nov (80K items/month)
⚠️ WATCH: AIOS growing faster ($420M vs £28M)
📊 LEVELS: Support 5.50 | Resistance 7.50

Action: HOLD — trim 30% at 7.00, stop 5.50
```

Short. Actionable. No fluff.

---

## Chat Interface

```
User: "Should I add to MPAL at current levels?"

Agent reasons over:
1. Graph: 6 theories about MPAL, 3 contradictions found
2. Stock: Price 6.64, entry 3.70, stop 5.50, target 10.00
3. Technical: -12% from high, support at 5.50
4. Thesis: Permission scarcity + physical infrastructure
5. Trading theory: After 80% run, adding is high-risk unless new catalyst

Response: "At 6.64 you're -12% from the 7.50 high. The stock ran 125% in 3 months. 
Adding here is high-risk unless you have conviction on the Oct-Nov breakeven. 
If you want to add, wait for a pullback to 5.50 support. 
If you're holding, trim 30% at 7.00 to lock gains. 
Stop at 5.50. Target 10.00."
```

Every claim backed by graph data or trading theory.
