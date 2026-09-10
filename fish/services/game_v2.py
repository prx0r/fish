"""Fish Game V2 — Training environment for learning when to trust AI forecasts.

North star:
> Fish Backtest is not a strategy simulator. It is a training environment
> for learning when and how much to trust an AI trading forecast.
> The objective is to outperform Fish after seeing Fish's call,
> uncertainty and reasoning, without receiving any future information.

Architecture:
- Game server controls the reveal cursor. Client NEVER gets future bars.
- Fish forecast is precomputed using ONLY data available at time T.
- Every forecast is an immutable record joined against outcomes later.
- Confidence calibration is the core mechanic, not just PnL.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Point-in-Time Data Provider
# ═══════════════════════════════════════════════════════════════════════════════

def load_real_prices() -> dict[str, list[dict]]:
    """Load real daily prices from prices.json."""
    from pathlib import Path
    path = Path(__file__).parent.parent.parent / 'data' / 'prices.json'
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    result = {}
    for ticker, rows in raw.items():
        result[ticker] = [
            {'date': r['date'], 'close': r.get('close', r.get('price', 0)),
             'open': r.get('open', r.get('price', 0)),
             'high': r.get('high', r.get('price', 0)),
             'low': r.get('low', r.get('price', 0)),
             'volume': r.get('volume', 1_000_000)}
            for r in rows
        ]
    return result


ALL_PRICES = load_real_prices()


def get_bars_up_to(ticker: str, asof: str) -> list[dict]:
    """Return bars for ticker where date <= asof. NO future leakage."""
    prices = ALL_PRICES.get(ticker, [])
    return [b for b in prices if b['date'] <= asof]


def get_future_bars(ticker: str, after: str, limit: int = 63) -> list[dict]:
    """Return bars for ticker where date > after. Used only for outcome scoring."""
    prices = ALL_PRICES.get(ticker, [])
    return [b for b in prices if b['date'] > after][:limit]


# ═══════════════════════════════════════════════════════════════════════════════
# Fish Forecast Engine
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_ensemble_forecast(bars: list[dict]) -> dict:
    """Run full Fish pipeline: regime → filtered ensemble → sequence sizing."""
    from fish.services.fish_signal import compute_fish_signal

    signal = compute_fish_signal(bars)

    # Build return dict compatible with existing game code
    return {
        'direction': signal.direction,
        'confidence': signal.ensemble_confidence,
        'consensus': signal.active_consensus,
        'votes_long': signal.animal_summary.get('Bull', {}).get('long', 0) +
                      signal.animal_summary.get('Turtle', {}).get('long', 0),
        'votes_short': signal.animal_summary.get('Bull', {}).get('short', 0) +
                       signal.animal_summary.get('Bear', {}).get('short', 0),
        'total': sum(a.get('total', 0) for a in signal.animal_summary.values()),
        'strategy_votes': {},  # Deprecated — use animal_summary instead
        'animal_summary': signal.animal_summary,
        'forecast': signal.forecast,
        'vol_20d': signal.vol_20d,
        'returns': signal.returns,
        # New Fish-specific fields
        'regime': {
            'combined': signal.regime.combined,
            'ma': signal.regime.ma_regime,
            'vol': signal.regime.vol_regime,
            'trend': signal.regime.trend_regime,
            'confidence': signal.regime.confidence,
            'active_animals': signal.regime.active_animals,
            'inactive_animals': signal.regime.inactive_animals,
        },
        'sizing': {
            'target_weight': signal.sizing.target_weight,
            'confidence': signal.sizing.confidence,
            'expected_return_20d': signal.sizing.expected_return_20d,
            'quantile_10': signal.sizing.quantile_10,
            'quantile_90': signal.sizing.quantile_90,
            'rationale': signal.sizing.sizing_rationale,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Game Engine
# ═══════════════════════════════════════════════════════════════════════════════
    for n in SHARK_STRATEGIES: ANIMAL_MAP[n] = 'Shark'
    for n in HEDGEHOG_STRATEGIES: ANIMAL_MAP[n] = 'Hedgehog'
    for n in WOLF_STRATEGIES: ANIMAL_MAP[n] = 'Wolf'

    animal_votes = {}
    for strat_name, vote in strategy_votes.items():
        animal = ANIMAL_MAP.get(strat_name, 'Unknown')
        animal_votes.setdefault(animal, {'long': 0, 'short': 0, 'flat': 0, 'total': 0})
        animal_votes[animal][vote.lower()] += 1
        animal_votes[animal]['total'] += 1

    animal_summary = {}
    for animal, counts in animal_votes.items():
        net = counts['long'] - counts['short']
        animal_summary[animal] = {
            'direction': 'LONG' if net > 0 else ('SHORT' if net < 0 else 'FLAT'),
            'net': net,
            'long': counts['long'],
            'short': counts['short'],
            'total': counts['total'],
        }

    # Compute simple forecast distribution from recent returns
    closes = [b['close'] for b in bars]
    returns_1d = (closes[-1] - closes[-2]) / closes[-2] if len(closes) > 1 else 0
    returns_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) > 6 else 0
    returns_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) > 21 else 0

    # Volatility for quantiles
    daily_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, min(61, len(closes)))]
    vol = (sum((r - sum(daily_returns)/len(daily_returns))**2 for r in daily_returns) / len(daily_returns)) ** 0.5 if daily_returns else 0.02

    # Simple forecast: expected return ≈ trend × confidence
    expected_20d = returns_20d * 0.3 + (0.01 if direction == 'LONG' else -0.01 if direction == 'SHORT' else 0)
    q10 = expected_20d - 1.28 * vol * math.sqrt(20)
    q90 = expected_20d + 1.28 * vol * math.sqrt(20)
    p_up = 0.5 + expected_20d / (2 * vol * math.sqrt(20)) if vol > 0 else 0.5
    p_up = max(0.1, min(0.9, p_up))

    return {
        'direction': direction,
        'confidence': round(confidence, 3),
        'consensus': round(consensus, 3),
        'votes_long': long_count,
        'votes_short': short_count,
        'total': total,
        'strategy_votes': strategy_votes,
        'animal_summary': animal_summary,
        'forecast': {
            '1d': {'p_up': round(p_up, 3), 'expected': round(returns_1d * 100, 2)},
            '5d': {'p_up': round(p_up * 0.95 + 0.025, 3), 'expected': round(returns_5d * 100, 2)},
            '20d': {
                'p_up': round(p_up * 0.9 + 0.05, 3),
                'expected': round(expected_20d * 100, 2),
                'q10': round(q10 * 100, 2),
                'q50': round(expected_20d * 100, 2),
                'q90': round(q90 * 100, 2),
            },
        },
        'vol_20d': round(vol * math.sqrt(252) * 100, 1),  # Annualized vol %
        'returns': {
            '1d': round(returns_1d * 100, 2),
            '5d': round(returns_5d * 100, 2),
            '20d': round(returns_20d * 100, 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Game State Machine
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GameForecast:
    """Immutable Fish forecast at time T. Frozen before outcome revealed."""
    asof: str
    direction: str
    confidence: float
    consensus: float
    votes_long: int
    votes_short: int
    votes_total: int
    forecast: dict
    vol_20d: float
    returns: dict
    data_hash: str  # Hash of input bars for reproducibility
    animal_summary: dict = field(default_factory=dict)
    strategy_votes: dict = field(default_factory=dict)
    sizing: dict = field(default_factory=dict)
    failures: int = 0
    failure_names: list = field(default_factory=list)


@dataclass
class PlayerDecision:
    """Player's locked decision at time T."""
    target_weight: float  # 0.0 (flat) to 1.0 (full long)
    probability_estimate: float | None = None  # Optional: P(up in 20d)
    override_reason: str | None = None


@dataclass
class GameStep:
    """One step in a game episode."""
    step: int
    ticker: str
    asof: str
    price: float
    fish_forecast: GameForecast
    player_decision: PlayerDecision | None = None
    # Outcome (filled after reveal)
    price_next: float | None = None
    return_next: float | None = None
    fish_pnl: float | None = None
    player_pnl: float | None = None
    bh_pnl: float | None = None
    brier_score: float | None = None


@dataclass
class GameEpisode:
    """A complete game episode."""
    id: str
    ticker: str
    mode: str  # blind, context, signal_only, adversarial
    start_date: str
    end_date: str
    steps: list[GameStep] = field(default_factory=list)
    current_step: int = 0
    status: str = 'pending'  # pending, active, completed
    created_at: str = ''
    # Final scores
    fish_total_return: float | None = None
    player_total_return: float | None = None
    bh_total_return: float | None = None
    residual_edge: float | None = None
    calibration_score: float | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Game Engine
# ═══════════════════════════════════════════════════════════════════════════════

# In-memory game store (replace with DB in production)
GAMES: dict[str, GameEpisode] = {}


def create_episode(
    ticker: str | None = None,
    mode: str = 'blind',
    episode_days: int = 126,  # ~6 months
    seed: int | None = None,
) -> GameEpisode:
    """Create a new game episode with randomized start.

    In blind mode, server picks ticker randomly if not specified.
    """
    eligible = [t for t, bars in ALL_PRICES.items() if len(bars) >= episode_days + 252]

    if mode == 'blind' and ticker is None:
        rng = random.Random(seed)
        ticker = rng.choice(eligible)
    elif ticker is None:
        ticker = eligible[0] if eligible else 'TSLA'

    prices = ALL_PRICES.get(ticker, [])
    if len(prices) < episode_days + 252:
        raise ValueError(f"Not enough data for {ticker}: need {episode_days + 252} bars, have {len(prices)}")

    rng = random.Random(seed)
    # Start after 252 days (need lookback for strategies), end episode_days later
    max_start = len(prices) - episode_days
    start_idx = rng.randint(252, max_start)
    start_date = prices[start_idx]['date']
    end_date = prices[start_idx + episode_days - 1]['date']

    episode = GameEpisode(
        id=str(uuid.uuid4())[:8],
        ticker=ticker,
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Precompute all steps (but don't reveal outcomes)
    for i in range(episode_days):
        bar = prices[start_idx + i]
        bars_up_to = prices[:start_idx + i + 1]

        # Fish forecast using ONLY data up to this bar
        forecast_data = _compute_ensemble_forecast(bars_up_to)
        bars_hash = hashlib.sha256(json.dumps([(b['date'], b['close']) for b in bars_up_to[-5:]]).encode()).hexdigest()[:16]

        fish_forecast = GameForecast(
            asof=bar['date'],
            direction=forecast_data['direction'],
            confidence=forecast_data['confidence'],
            consensus=forecast_data['consensus'],
            votes_long=forecast_data['votes_long'],
            votes_short=forecast_data['votes_short'],
            votes_total=forecast_data['total'],
            forecast=forecast_data['forecast'],
            vol_20d=forecast_data['vol_20d'],
            returns=forecast_data['returns'],
            data_hash=bars_hash,
            animal_summary=forecast_data.get('animal_summary', {}),
            strategy_votes=forecast_data.get('strategy_votes', {}),
            sizing=forecast_data.get('sizing', {}),
            failures=forecast_data.get('failures', 0),
            failure_names=forecast_data.get('failure_names', []),
        )

        step = GameStep(
            step=i,
            ticker=ticker,
            asof=bar['date'],
            price=bar['close'],
            fish_forecast=fish_forecast,
        )
        episode.steps.append(step)

    episode.status = 'active'
    GAMES[episode.id] = episode
    return episode


def get_episode_state(episode_id: str) -> dict | None:
    """Get current game state. Only reveals information up to current step."""
    ep = GAMES.get(episode_id)
    if not ep:
        return None

    step = ep.steps[ep.current_step]

    # Build visible chart — signal_only mode shows no chart
    if ep.mode == 'signal_only':
        chart = []
    else:
        chart = [{'date': s.asof, 'price': s.price} for s in ep.steps[:ep.current_step + 1]]

    # Fish forecast (frozen)
    f = step.fish_forecast

    # Reveal mode depends on game mode
    ticker_revealed = ep.mode != 'blind'
    date_revealed = ep.mode != 'blind'

    return {
        'episode_id': ep.id,
        'status': ep.status,
        'ticker': ep.ticker if ticker_revealed else '???',
        'asof': step.asof if date_revealed else f'Day {step.step + 1}/{len(ep.steps)}',
        'step': step.step,
        'total_steps': len(ep.steps),
        'price': step.price,
        'chart': chart,
        'fish': {
            'direction': f.direction,
            'confidence': f.confidence,
            'consensus': f.consensus,
            'votes_long': f.votes_long,
            'votes_short': f.votes_short,
            'votes_total': f.votes_total,
            'forecast': f.forecast,
            'vol_20d': f.vol_20d,
            'recent_returns': f.returns,
            'animal_summary': f.animal_summary,
            'strategy_votes': f.strategy_votes,
            'sizing': f.sizing,
        },
        'player_decision': None,  # Not yet made
        'outcome': None,  # Not yet revealed
    }


def lock_decision(episode_id: str, target_weight: float,
                  probability_estimate: float | None = None,
                  override_reason: str | None = None) -> dict | None:
    """Lock player's decision for current step. Cannot be changed after."""
    ep = GAMES.get(episode_id)
    if not ep or ep.status != 'active':
        return None

    step = ep.steps[ep.current_step]
    if step.player_decision is not None:
        return {'error': 'Decision already locked for this step'}

    step.player_decision = PlayerDecision(
        target_weight=max(0.0, min(1.0, target_weight)),
        probability_estimate=probability_estimate,
        override_reason=override_reason,
    )

    return {'locked': True, 'step': step.step, 'target_weight': step.player_decision.target_weight}


def advance_episode(episode_id: str) -> dict | None:
    """Reveal outcome of current step and advance to next. Both Fish and Player are scored."""
    ep = GAMES.get(episode_id)
    if not ep or ep.status != 'active':
        return None

    step = ep.steps[ep.current_step]
    if step.player_decision is None:
        return {'error': 'Must lock decision before advancing'}

    # Get next bar (the outcome)
    prices = ALL_PRICES.get(ep.ticker, [])
    current_idx = None
    for i, p in enumerate(prices):
        if p['date'] == step.asof:
            current_idx = i
            break

    if current_idx is None or current_idx + 1 >= len(prices):
        # End of data — episode over
        ep.status = 'completed'
        return {'completed': True}

    next_bar = prices[current_idx + 1]
    step.price_next = next_bar['close']
    step.return_next = (next_bar['close'] - step.price) / step.price

    # Transaction costs (10 bps each way)
    COST_BPS = 10

    # Score Fish: use target_weight from Sequence sizing (long-only [0,1])
    fish_target = step.fish_forecast.sizing.get('target_weight', 0.0) if hasattr(step.fish_forecast, 'sizing') else 0.0
    # Fallback: if sizing not available, derive from direction + confidence
    if fish_target == 0.0 and step.fish_forecast.direction != 'FLAT':
        fish_target = step.fish_forecast.confidence  # Scale by confidence
    # Cost: turnover × cost_bps
    fish_turnover = abs(fish_target - (ep.steps[ep.current_step - 1].fish_forecast.sizing.get('target_weight', 0.0) if ep.current_step > 0 else 0))
    fish_cost = fish_turnover * (COST_BPS / 10000)
    step.fish_pnl = fish_target * step.return_next - fish_cost

    # Score Player (long-only [0,1])
    prev_weight = ep.steps[ep.current_step - 1].player_decision.target_weight if ep.current_step > 0 and ep.steps[ep.current_step - 1].player_decision else 0
    player_turnover = abs(step.player_decision.target_weight - prev_weight)
    player_cost = player_turnover * (COST_BPS / 10000)
    step.player_pnl = step.player_decision.target_weight * step.return_next - player_cost

    # Buy-and-hold benchmark (always 100% long, no turnover after day 1)
    step.bh_pnl = step.return_next

    # Brier score for probability estimate
    if step.player_decision.probability_estimate is not None:
        actual_up = 1.0 if step.return_next > 0 else 0.0
        step.brier_score = (step.player_decision.probability_estimate - actual_up) ** 2

    # Advance
    ep.current_step += 1

    # Check if episode is complete
    if ep.current_step >= len(ep.steps):
        ep.status = 'completed'
        _finalize_episode(ep)

    return {
        'revealed': True,
        'price_next': step.price_next,
        'return_next': round(step.return_next * 100, 2),
        'fish_pnl': round(step.fish_pnl * 100, 2),
        'player_pnl': round(step.player_pnl * 100, 2),
        'bh_pnl': round(step.bh_pnl * 100, 2),
        'brier_score': step.brier_score,
        'completed': ep.status == 'completed',
    }


def _finalize_episode(ep: GameEpisode) -> None:
    """Compute final scores for completed episode."""
    # Compound returns
    fish_equity = 1.0
    player_equity = 1.0
    bh_equity = 1.0
    brier_scores = []

    for step in ep.steps:
        if step.return_next is None:
            continue
        fish_weight = 1.0 if step.fish_forecast.direction == 'LONG' else (-1.0 if step.fish_forecast.direction == 'SHORT' else 0.0)
        fish_equity *= (1 + fish_weight * step.return_next)
        player_equity *= (1 + step.player_decision.target_weight * step.return_next)
        bh_equity *= (1 + step.return_next)
        if step.brier_score is not None:
            brier_scores.append(step.brier_score)

    ep.fish_total_return = round((fish_equity - 1) * 100, 2)
    ep.player_total_return = round((player_equity - 1) * 100, 2)
    ep.bh_total_return = round((bh_equity - 1) * 100, 2)
    ep.residual_edge = round(ep.player_total_return - ep.fish_total_return, 2)
    ep.calibration_score = round(sum(brier_scores) / len(brier_scores), 4) if brier_scores else None


def get_episode_result(episode_id: str) -> dict | None:
    """Get final results for a completed episode."""
    ep = GAMES.get(episode_id)
    if not ep or ep.status != 'completed':
        return None

    # Build step-by-step results
    step_results = []
    for s in ep.steps:
        if s.return_next is None:
            continue
        step_results.append({
            'step': s.step,
            'asof': s.asof,
            'price': s.price,
            'price_next': s.price_next,
            'return_next': round(s.return_next * 100, 2),
            'fish_direction': s.fish_forecast.direction,
            'fish_confidence': s.fish_forecast.confidence,
            'fish_pnl': round(s.fish_pnl * 100, 2) if s.fish_pnl is not None else None,
            'player_weight': s.player_decision.target_weight if s.player_decision else None,
            'player_pnl': round(s.player_pnl * 100, 2) if s.player_pnl is not None else None,
            'brier_score': s.brier_score,
        })

    # Calibration by confidence bucket
    calibration = _compute_calibration(ep)

    # Attribution
    attribution = _compute_attribution(ep)

    return {
        'episode_id': ep.id,
        'ticker': ep.ticker,
        'mode': ep.mode,
        'start_date': ep.start_date,
        'end_date': ep.end_date,
        'total_steps': len(ep.steps),
        'scores': {
            'player_return': ep.player_total_return,
            'fish_return': ep.fish_total_return,
            'bh_return': ep.bh_total_return,
            'residual_edge': ep.residual_edge,
            'calibration_brier': ep.calibration_score,
        },
        'calibration': calibration,
        'attribution': attribution,
        'steps': step_results,
    }


def _compute_calibration(ep: GameEpisode) -> list[dict]:
    """Bin Fish forecasts by confidence and check calibration."""
    buckets = {}
    for step in ep.steps:
        if step.return_next is None:
            continue
        conf = step.fish_forecast.confidence
        # Bin: 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0
        bucket = min(4, int(conf / 0.2))
        if bucket not in buckets:
            buckets[bucket] = {'forecasts': [], 'actuals': []}
        buckets[bucket]['forecasts'].append(conf)
        # Did Fish's direction match reality?
        fish_right = (step.fish_forecast.direction == 'LONG' and step.return_next > 0) or \
                     (step.fish_forecast.direction == 'SHORT' and step.return_next < 0)
        buckets[bucket]['actuals'].append(1.0 if fish_right else 0.0)

    result = []
    for bucket in sorted(buckets.keys()):
        b = buckets[bucket]
        avg_conf = sum(b['forecasts']) / len(b['forecasts'])
        hit_rate = sum(b['actuals']) / len(b['actuals'])
        result.append({
            'confidence_range': f'{bucket*0.2:.1f}-{(bucket+1)*0.2:.1f}',
            'avg_confidence': round(avg_conf, 3),
            'hit_rate': round(hit_rate, 3),
            'count': len(b['forecasts']),
            'calibration_gap': round(abs(avg_conf - hit_rate), 3),
        })
    return result


def _compute_attribution(ep: GameEpisode) -> dict:
    """Decompose player edge into timing/sizing/direction/exit components."""
    if not ep.steps or ep.steps[0].return_next is None:
        return {}

    # Simplified attribution
    total_player = 0
    total_fish = 0
    sizing_contribution = 0
    direction_contribution = 0

    for step in ep.steps:
        if step.return_next is None or step.player_decision is None:
            continue
        fish_w = 1.0 if step.fish_forecast.direction == 'LONG' else (-1.0 if step.fish_forecast.direction == 'SHORT' else 0.0)
        player_w = step.player_decision.target_weight
        ret = step.return_next

        total_fish += fish_w * ret
        total_player += player_w * ret
        # Sizing edge: player sized differently than Fish
        sizing_contribution += (player_w - fish_w) * ret
        # Direction alignment
        if fish_w != 0:
            direction_contribution += (1 if (player_w > 0 and fish_w > 0) or (player_w < 0 and fish_w < 0) else -1) * abs(ret) * 0.1

    total_edge = total_player - total_fish
    return {
        'total_edge': round(total_edge * 100, 2),
        'sizing_edge': round(sizing_contribution * 100, 2),
        'direction_alignment': round(direction_contribution * 100, 2),
        'player_total': round(total_player * 100, 2),
        'fish_total': round(total_fish * 100, 2),
    }
