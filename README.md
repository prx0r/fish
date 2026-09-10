# Fish — Personal Portfolio Intelligence for Chris Prior

**Codename**: Fish
**Repo**: github.com/prx0r/fish
**Based on**: Feedify 2.0 knowledge graph

---

## What This Is

Fish is Chris Prior's personal stock portfolio intelligence system. It:
1. Watches his 19 positions
2. Generates daily briefs (bitesized, actionable)
3. Lets him chat with an AI that reasons over the knowledge graph
4. Tracks paper trades (AI vs Human performance)
5. Discovers other traders who discuss his tickers

**The graph is the source of truth. The LLM is the reasoning engine.**

---

## Portfolio

| Account | Positions | Value |
|---------|-----------|-------|
| Dealing | 14 | £163,933 |
| ISA | 5 | £26,383 |
| **Total** | **19** | **£183,826** |

**Unrealised P/L**: +£13,082 (+7.66%)

---

## How to Run

```bash
cd /root/fish
source .venv/bin/activate
uvicorn fish.api:app --reload --port 8789

# Daily brief
curl http://localhost:8789/api/portfolio/brief

# AI chat
curl -X POST http://localhost:8789/api/portfolio/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What should I do with MPAL?"}'

# Paper trade
curl -X POST http://localhost:8789/api/trading/suggest \
  -H "Content-Type: application/json" \
  -d '{"ticker":"COHR"}'
```

---

## Relationship to Feedify

```
Feedify (knowledge graph)     Fish (portfolio intelligence)
┌─────────────────────┐      ┌─────────────────────────┐
│ X posts → Objects   │      │ Portfolio → Briefs      │
│ Convergence         │◄────▶│ AI Chat                 │
│ Scarcity engine     │GRAPH │ Paper Trading           │
│ Prediction tracking │      │ Daily Reports           │
└─────────────────────┘      └─────────────────────────┘
```

Feedify provides the intelligence. Fish provides the decisions.
