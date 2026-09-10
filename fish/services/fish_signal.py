"""Fish Signal — Unified intelligence layer.

The real Fish is not a majority vote. It's:
1. Wolf detects regime → which strategies are allowed to vote
2. Ensemble votes within active strategies → direction + confidence
3. Sequence/MPC sizes the position → target weight with confidence intervals
4. Mantis provides execution timing → when to enter/exit

This module chains them into a single coherent signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# Regime Detection (Wolf)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RegimeState:
    """Current market regime detected by Wolf."""
    ma_regime: str = "neutral"      # bull, bear, neutral
    vol_regime: str = "mid"         # low, mid, high
    trend_regime: str = "choppy"    # trending, choppy
    combined: str = "neutral"       # bull_low_vol, bear_high_vol, etc.
    confidence: float = 0.5
    active_animals: list = field(default_factory=list)
    inactive_animals: list = field(default_factory=list)


# Which animals are active in each regime
REGIME_ANIMAL_MAP = {
    "bull_low_vol":  ["Turtle", "Bull", "Fox", "Hedgehog"],
    "bull_mid_vol":  ["Turtle", "Bull", "Fox"],
    "bull_high_vol": ["Turtle", "Bear"],  # Bull retreats in high vol
    "bear_low_vol":  ["Bear", "Fox", "Wolf"],
    "bear_mid_vol":  ["Bear", "Fox", "Wolf"],
    "bear_high_vol": ["Bear", "Wolf"],  # Only contrarians survive
    "neutral_low":   ["Turtle", "Fox", "Hedgehog"],
    "neutral_mid":   ["Fox", "Wolf"],
    "neutral_high":  ["Wolf"],  # Only regime detection survives
}

ALL_ANIMALS = ["Turtle", "Bull", "Bear", "Fox", "Shark", "Hedgehog", "Wolf"]


def detect_regime(prices: list[dict]) -> RegimeState:
    """Detect current market regime from price history."""
    if len(prices) < 100:
        return RegimeState(active_animals=ALL_ANIMALS, inactive_animals=[])

    closes = [p.get("close", p.get("price", 0)) for p in prices]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

    # MA regime (20 vs 100)
    ma20 = sum(closes[-20:]) / 20
    ma100 = sum(closes[-100:]) / 100
    ma_regime = "bull" if ma20 > ma100 else "bear"

    # Vol regime (20-day realized vol, annualized)
    vol_window = returns[-20:]
    vol_mean = sum(vol_window) / len(vol_window)
    vol_20d = math.sqrt(sum((r - vol_mean)**2 for r in vol_window) / len(vol_window)) * math.sqrt(252)

    if vol_20d < 0.15:
        vol_regime = "low"
    elif vol_20d > 0.30:
        vol_regime = "high"
    else:
        vol_regime = "mid"

    # Trend regime (20-day Sharpe)
    std = math.sqrt(sum((r - vol_mean)**2 for r in vol_window) / len(vol_window))
    sharpe_20d = (vol_mean / std * math.sqrt(252)) if std > 0 else 0
    trend_regime = "trending" if abs(sharpe_20d) > 1 else "choppy"

    # Combined regime
    if ma_regime == "bull":
        combined = f"bull_{vol_regime}_vol"
    elif ma_regime == "bear":
        combined = f"bear_{vol_regime}_vol"
    else:
        combined = f"neutral_{vol_regime}"

    # Confidence: how clearly regime is defined
    ma_strength = abs(ma20 - ma100) / ma100
    vol_clearity = abs(vol_20d - 0.225) / 0.225  # Distance from "uncertain" mid vol
    confidence = min(1.0, (ma_strength * 10 + vol_clearity) / 2)

    # Active animals
    active = REGIME_ANIMAL_MAP.get(combined, ["Fox", "Wolf"])
    inactive = [a for a in ALL_ANIMALS if a not in active]

    return RegimeState(
        ma_regime=ma_regime,
        vol_regime=vol_regime,
        trend_regime=trend_regime,
        combined=combined,
        confidence=round(confidence, 3),
        active_animals=active,
        inactive_animals=inactive,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Regime-Filtered Ensemble
# ═══════════════════════════════════════════════════════════════════════════════

ANIMAL_MAP = {}  # Populated at import time


def _init_animal_map():
    global ANIMAL_MAP
    from fish.services.baselines import STRATEGY_META
    from fish.services.fox import FOX_STRATEGIES
    from fish.services.shark import SHARK_STRATEGIES
    from fish.services.hedgehog import HEDGEHOG_STRATEGIES
    from fish.services.wolf import WOLF_STRATEGIES
    for n, m in STRATEGY_META.items():
        ANIMAL_MAP[n] = m.get('animal', 'Unknown')
    for n in FOX_STRATEGIES: ANIMAL_MAP[n] = 'Fox'
    for n in SHARK_STRATEGIES: ANIMAL_MAP[n] = 'Shark'
    for n in HEDGEHOG_STRATEGIES: ANIMAL_MAP[n] = 'Hedgehog'
    for n in WOLF_STRATEGIES: ANIMAL_MAP[n] = 'Wolf'


def regime_filtered_vote(prices: list[dict], regime: RegimeState) -> dict:
    """Run ensemble vote, but only active animals in current regime vote."""
    if not ANIMAL_MAP:
        _init_animal_map()

    from fish.services.baselines import BASELINE_STRATEGIES
    from fish.services.fox import FOX_STRATEGIES
    from fish.services.shark import SHARK_STRATEGIES
    from fish.services.hedgehog import HEDGEHOG_STRATEGIES
    from fish.services.wolf import WOLF_STRATEGIES
    all_strats = {**BASELINE_STRATEGIES, **FOX_STRATEGIES, **SHARK_STRATEGIES,
                  **HEDGEHOG_STRATEGIES, **WOLF_STRATEGIES}

    prices_fmt = [{'date': b.get('date', ''), 'price': b.get('close', b.get('price', 0)),
                    'close': b.get('close', b.get('price', 0)),
                    'open': b.get('open', b.get('price', 0)),
                    'high': b.get('high', b.get('price', 0)),
                    'low': b.get('low', b.get('price', 0)),
                    'volume': b.get('volume', 1_000_000)} for b in prices]

    animal_votes = {}
    long_count = short_count = total = 0
    active_long = active_short = active_total = 0
    failures = 0
    failure_names = []

    for name, fn in all_strats.items():
        animal = ANIMAL_MAP.get(name, 'Unknown')
        is_active = animal in regime.active_animals

        try:
            r = fn(prices=prices_fmt)
            if r and r.trades:
                last = r.trades[-1].get('action', '')
                vote = 'LONG' if last == 'BUY' else ('SHORT' if last == 'SELL' else 'FLAT')
            else:
                vote = 'FLAT'
        except Exception as e:
            vote = 'FLAT'
            failures += 1
            failure_names.append(name)

        animal_votes.setdefault(animal, {'long': 0, 'short': 0, 'flat': 0, 'total': 0, 'active': is_active})
        animal_votes[animal][vote.lower()] += 1
        animal_votes[animal]['total'] += 1
        total += 1
        if vote == 'LONG': long_count += 1
        elif vote == 'SHORT': short_count += 1

        if is_active:
            active_total += 1
            if vote == 'LONG': active_long += 1
            elif vote == 'SHORT': active_short += 1

    # Active consensus (what matters)
    active_consensus = active_long / active_total if active_total > 0 else 0.5
    active_direction = 'LONG' if active_consensus > 0.6 else ('SHORT' if active_consensus < 0.4 else 'FLAT')
    active_confidence = abs(active_consensus - 0.5) * 2

    # Animal summary with active/inactive labels
    animal_summary = {}
    for animal, counts in animal_votes.items():
        net = counts['long'] - counts['short']
        animal_summary[animal] = {
            'direction': 'LONG' if net > 0 else ('SHORT' if net < 0 else 'FLAT'),
            'net': net,
            'long': counts['long'],
            'short': counts['short'],
            'total': counts['total'],
            'active': counts['active'],
        }

    return {
        'direction': active_direction,
        'consensus': round(active_consensus, 3),
        'confidence': round(active_confidence, 3),
        'active_long': active_long,
        'active_short': active_short,
        'active_total': active_total,
        'total_long': long_count,
        'total_short': short_count,
        'total_strategies': total,
        'failures': failures,
        'failure_names': failure_names,
        'animal_votes': animal_votes,
        'animal_summary': animal_summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Sequence Sizing (MPC)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SequenceSizing:
    """Position sizing from Sequence/MPC."""
    target_weight: float       # 0.0 to 1.0
    confidence: float          # 0.0 to 1.0
    expected_return_20d: float # Annualized expected return
    quantile_10: float         # 10th percentile return
    quantile_90: float         # 90th percentile return
    sizing_rationale: str      # Human-readable explanation


def sequence_sizing(prices: list[dict], direction: str, ensemble_confidence: float) -> SequenceSizing:
    """Compute position sizing using MPC-style logic."""
    if len(prices) < 60:
        return SequenceSizing(target_weight=0, confidence=0, expected_return_20d=0,
                              quantile_10=0, quantile_90=0, sizing_rationale="Insufficient data")

    closes = [p.get("close", p.get("price", 0)) for p in prices]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

    # Recent returns for forecast
    ret_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) > 21 else 0
    ret_60d = (closes[-1] - closes[-61]) / closes[-61] if len(closes) > 61 else 0

    # Volatility for quantiles
    vol_window = returns[-60:]
    vol_mean = sum(vol_window) / len(vol_window)
    vol = math.sqrt(sum((r - vol_mean)**2 for r in vol_window) / len(vol_window))

    # Expected return: blend of trend + mean reversion + regime signal
    expected_ret = ret_20d * 0.4 + ret_60d * 0.2
    if direction == 'LONG':
        expected_ret += vol * 0.5  # Trend following boost
    elif direction == 'SHORT':
        expected_ret -= vol * 0.5

    # Quantiles
    q10 = expected_ret - 1.28 * vol * math.sqrt(20)
    q90 = expected_ret + 1.28 * vol * math.sqrt(20)

    # Position sizing: Kelly-like with confidence scaling
    # Base: expected return / variance (simplified Kelly)
    if vol > 0:
        kelly_fraction = expected_ret / (vol ** 2 * 20)
        kelly_fraction = max(-1, min(1, kelly_fraction))  # Clip
    else:
        kelly_fraction = 0

    # Scale by ensemble confidence
    scaled_weight = abs(kelly_fraction) * ensemble_confidence

    # Apply direction
    if direction == 'LONG':
        target_weight = min(1.0, scaled_weight)
    elif direction == 'SHORT':
        target_weight = min(1.0, scaled_weight)  # For game, treat as magnitude
    else:
        target_weight = 0.0

    # Confidence from forecast quality
    confidence = ensemble_confidence * min(1.0, len(closes) / 252)  # Decay with data length

    # Rationale
    if direction == 'FLAT':
        rationale = f"No clear direction. Ensemble consensus={ensemble_confidence:.0%}. Staying flat."
    elif target_weight < 0.25:
        rationale = f"Weak signal. Kelly={kelly_fraction:.2f}, conf={ensemble_confidence:.0%}. Small position."
    elif target_weight < 0.6:
        rationale = f"Moderate signal. Kelly={kelly_fraction:.2f}, conf={ensemble_confidence:.0%}. Half position."
    elif target_weight < 0.85:
        rationale = f"Strong signal. Kelly={kelly_fraction:.2f}, conf={ensemble_confidence:.0%}. Large position."
    else:
        rationale = f"Very strong signal. Kelly={kelly_fraction:.2f}, conf={ensemble_confidence:.0%}. Full position."

    return SequenceSizing(
        target_weight=round(target_weight, 3),
        confidence=round(confidence, 3),
        expected_return_20d=round(expected_ret * 100, 2),
        quantile_10=round(q10 * 100, 2),
        quantile_90=round(q90 * 100, 2),
        sizing_rationale=rationale,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Fish Signal
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FishSignal:
    """Complete Fish intelligence output."""
    # Regime
    regime: RegimeState
    # Ensemble
    direction: str
    ensemble_confidence: float
    active_consensus: float
    # Sizing
    sizing: SequenceSizing
    # Animal breakdown
    animal_summary: dict
    # Forecast distribution
    forecast: dict
    # Raw data
    vol_20d: float
    returns: dict


def compute_fish_signal(prices: list[dict]) -> FishSignal:
    """The full Fish intelligence pipeline.

    1. Wolf detects regime
    2. Only active animals vote
    3. Ensemble produces direction + confidence
    4. Sequence sizes the position
    5. Returns unified signal
    """
    if len(prices) < 60:
        return FishSignal(
            regime=RegimeState(),
            direction='FLAT', ensemble_confidence=0, active_consensus=0.5,
            sizing=SequenceSizing(0, 0, 0, 0, 0, "Insufficient data"),
            animal_summary={}, forecast={}, vol_20d=0, returns={},
        )

    closes = [p.get("close", p.get("price", 0)) for p in prices]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

    # Step 1: Wolf detects regime
    regime = detect_regime(prices)

    # Step 2-3: Regime-filtered ensemble vote
    vote = regime_filtered_vote(prices, regime)

    # Step 4: Sequence sizing
    sizing = sequence_sizing(prices, vote['direction'], vote['confidence'])

    # Forecast distribution — clearly labeled as model output, not trailing data
    vol_window = returns[-60:]
    vol_mean = sum(vol_window) / len(vol_window)
    vol = math.sqrt(sum((r - vol_mean)**2 for r in vol_window) / len(vol_window))

    ret_20d = (closes[-1] - closes[-21]) / closes[-21] if len(closes) > 21 else 0
    expected_20d = ret_20d * 0.3 + (0.01 if vote['direction'] == 'LONG' else -0.01 if vote['direction'] == 'SHORT' else 0)
    p_up = 0.5 + expected_20d / (2 * vol * math.sqrt(20)) if vol > 0 else 0.5
    p_up = max(0.1, min(0.9, p_up))

    forecast = {
        'model': 'ensemble_regime_filtered',
        '20d': {
            'p_up': round(p_up, 3),
            'expected': round(expected_20d * 100, 2),
            'q10': round((expected_20d - 1.28 * vol * math.sqrt(20)) * 100, 2),
            'q50': round(expected_20d * 100, 2),
            'q90': round((expected_20d + 1.28 * vol * math.sqrt(20)) * 100, 2),
        },
        'trailing': {
            '1d': round(returns[-1] * 100, 2) if returns else 0,
            '5d': round(((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) > 6 else 0, 2),
            '20d': round(ret_20d * 100, 2),
        },
        'strategies_expected': vote.get('total_strategies', 0),
        'strategies_successful': vote.get('total_strategies', 0) - vote.get('failures', 0),
        'strategies_failed': vote.get('failures', 0),
    }

    # Returns summary
    ret_1d = returns[-1] if returns else 0
    ret_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) > 6 else 0

    return FishSignal(
        regime=regime,
        direction=vote['direction'],
        ensemble_confidence=vote['confidence'],
        active_consensus=vote['consensus'],
        sizing=sizing,
        animal_summary=vote['animal_summary'],
        forecast=forecast,
        vol_20d=round(vol * math.sqrt(252) * 100, 1),
        returns={'1d': round(ret_1d * 100, 2), '5d': round(ret_5d * 100, 2), '20d': round(ret_20d * 100, 2)},
    )
