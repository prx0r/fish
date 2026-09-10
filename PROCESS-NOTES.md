# Fish — Process Notes
**Date**: 2026-09-10
**Session**: Full day — ensemble, backtest, game V2, cross-repo review

---

## What Actually Happened Today

### Morning
- Reviewed fish repo structure. Found it's a Feedify fork with 50 service files, 41 strategies, 15 tickers.
- Fixed `_build_result` bug — strategies were all returning the same Sharpe because it was computed on raw stock returns, not strategy equity curves.
- Built `run_ensemble.py` — ran all 41 strategies on Chris Prior's 15 tickers, consensus voting.
- Built `run_backtest.py` — walk-forward ensemble backtest vs buy-and-hold.
- **Result**: 3/14 beat buy-and-hold. Ensemble too conservative — goes flat when consensus 40-60%, misses bull market rallies.
- **Key insight**: Moonshots (NBIS +1102%, PGEN +594%) had -20-40% crashes on the way up. Ensemble correctly went flat during crashes, couldn't re-enter fast enough.

### Afternoon
- Reviewed /fleece (DeltaTuna) and /bitt (Bittensor/CGE) repos for backtesting patterns.
- Created `REVIEW-FLEECE-BITT.md` — 18 adoptable patterns ranked by impact × effort.
- Top 3: Wilson intervals for small-N, shrinkage scoring, confidence-gated position sizing.

### Evening
- Built Game V2 kernel (`game_v2.py`) — proper state machine with locked forecasts, no future leakage, Brier calibration, attribution.
- Merged judge.py/judge_v2.py into one canonical Judge.
- Fixed equity.py — win_rate now computed from trade PnL, calmar uses CAGR.
- Rewrote `backtest.html` — wired to Game V2 API. Three modes (Blind/Context/Signal Only).
- Tested full loop end-to-end via API. Works.

---

## Current State (Honest)

### What Works
- 41 strategies run correctly with proper equity-curve metrics
- Ensemble produces consensus signals per ticker
- Game V2 kernel: create episode → get state → lock decision → advance → get result
- Calibration scoring (Brier by confidence bucket)
- Attribution (sizing edge, direction alignment)
- Frontend: mode selection, incremental chart, Fish forecast card, position slider, results screen
- All committed and pushed to GitHub (4 commits)

### What's Broken or Missing
1. **Ensemble is bad at making money** — 3/14 beat B&H. The consensus voting is too binary (long/flat/short). Needs position sizing based on confidence strength, not just direction.

2. **No real data integration** — The ensemble uses `prices.json` (289KB, 501 days per ticker). No live prices, no fundamentals, no Feedify graph data feeding into Fish's forecast.

3. **Game has no players** — Zero human decisions recorded. Can't train HumanResidual model. Can't validate calibration. Can't measure residual edge.

4. **Forecast is primitive** — Fish's forecast is just "majority of 41 strategies say long/short/flat." No Sequence engine, no MPC planner, no Mantis execution, no regime detection wired into the game. All that infrastructure exists but isn't connected.

5. **No persistence** — Game state is in-memory dict. Server restart loses all games. Need SQLite.

6. **No authentication** — Anyone can play. No user accounts, no leaderboard, no session history.

7. **Data gaps** — 3 tickers (MPAL, BT.A, JDW) have no data in the daily parquet. MPAL only has 265 days (not enough for some strategies).

---

## What To Do Next (Grounded)

### This Week: Get 50 Rounds Played

The entire product thesis is untested until someone plays. Not "someone" — **you**.

1. **Play 50 rounds yourself** on `localhost:8790/backtest`. Blind mode. Record:
   - Did you beat Fish?
   - When did you override Fish? Why?
   - Which confidence levels did you trust vs fade?
   - Did the game feel fair? Or did it feel like the deck was stacked?

2. **Fix what breaks** — There will be UX bugs, edge cases, moments where the game feels wrong. Fix them as you encounter them. Don't pre-optimize.

3. **After 50 rounds**, look at the calibration table. Is Fish's 70% confidence actually right 70% of the time? If not, the forecast is miscalibrated and the game teaches the wrong lesson.

### Next Week: Make Fish's Forecast Better

The current forecast is just ensemble voting. The infrastructure for a real forecast exists but isn't wired:

- **Sequence engine** (`fish/services/sequence/`) — MPC planner, scenario generator, optimizer. Exists but not connected to the game.
- **Wolf** — regime detection. Should gate whether ensemble is in the right mode.
- **Mantis** — microstructure execution. Not relevant for daily game but will matter for real trading.

Wire the Sequence engine's output into the game's Fish forecast. This means the game shows actual MPC recommendations, not just "majority vote."

### Month 2: HumanResidual Model

After 100+ decisions, train a model:

```python
# For each decision, features are:
# - Fish direction, confidence, consensus
# - Forecast quantiles
# - Recent returns
# - Volatility regime
# - Player's override reason

# Label:
# - Did the player outperform Fish on this step?

# Train a classifier: P(player beats fish | features)
```

This becomes the HumanResidual avatar — the 42nd strategy in the ensemble, trained on your actual decisions.

### Don't Do Yet
- Don't add more data sources (SEC, FRED, etc.) until the game loop is validated
- Don't build a native app until the web version works
- Don't add more strategies until the existing 41 are properly evaluated
- Don't deploy to production until calibration is verified

---

## The Honest Assessment

The fish repo has **too much code and not enough validation**. 50 service files, 41 strategies, Sequence/MPC/Mantis infrastructure — all built but most of it untested against real decisions.

The game V2 is the right direction because it forces validation. Every round produces a calibration data point. After 100 rounds, you'll know:
- Is Fish's confidence well-calibrated?
- Where does the human add value?
- Which strategies actually contribute to the ensemble?

The risk is that we keep building infrastructure (more avatars, more data, more backtests) instead of playing the game. The game is the feedback loop. Everything else is a distraction until the game works.

**One sentence**: Play the game, fix what breaks, then make Fish's forecast better based on what you learn from playing.

---

## Files Changed Today

| File | What Changed |
|------|-------------|
| `fish/services/baselines.py` | Fixed `_build_result` — Sharpe from strategy equity, not stock returns |
| `fish/services/equity.py` | Fixed win_rate (trade PnL), calmar (CAGR), rebuilt trade list |
| `fish/services/judge.py` | Merged into thin re-export from judge_v2.py |
| `fish/services/game_v2.py` | New — game state machine, point-in-time data, calibration, attribution |
| `fish/api.py` | Added 5 game endpoints, fixed typo |
| `static/backtest.html` | Complete rewrite — Game V2 frontend |
| `run_ensemble.py` | New — 41 strategies × 15 tickers ensemble |
| `run_backtest.py` | New — walk-forward ensemble backtest |
| `REVIEW-FLEECE-BITT.md` | New — cross-repo pattern review |

## Commits

```
78ddc0f  Backtest page wired to Game V2 API
4254c9d  Cross-repo review (fleece + bitt patterns)
c3fe13a  Game V2 kernel (point-in-time, locked forecasts)
125ba28  Ensemble backtest + equity curve fix
```
