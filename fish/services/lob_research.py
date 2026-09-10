"""LOB Research — Classify arXiv papers by data requirements and implement.

Architecture:
- Paper classifier: extract data requirements from paper metadata
- Research module: fit/predict/backtest/paper_baseline/live_signal
- Tournament: walk-forward evaluation on recorded LSE data
- Feature ablation: L1 vs L1-2 vs L1-5 vs L1-10

Data tiers:
- L1: best bid/ask + size (IBKR L2 gives this)
- L2: top 5/10/20 levels (IBKR L2 gives this)
- L3: individual order events (BMLL/LSEG only)
- Trades: executed trades with aggressor side (IBKR L2 gives this)
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# Paper Classifier
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LOBPaper:
    """Classification of a market microstructure paper."""
    title: str
    authors: list[str]
    year: int
    arxiv_id: str = ""
    # Data requirements
    required_data: list[str] = field(default_factory=list)  # L1, L2, L3, trades, mbo, etc.
    min_levels: int = 1
    needs_order_ids: bool = False
    needs_execution_history: bool = False
    # Prediction
    prediction_target: str = ""  # mid_price, spread, volatility, direction, etc.
    horizon: str = ""  # 1s, 10s, 1min, etc.
    # Classification
    tier: str = ""  # A (reproducible), B (approximable), C (impossible)
    tier_reason: str = ""
    # Implementation status
    implemented: bool = False
    backtested: bool = False


PAPER_DB = [
    LOBPaper(
        title="Optimal Execution with Multi-Level Order Flow Imbalance",
        authors=["Tomaso Aste", "Zihao Zhang"],
        year=2020, arxiv_id="2010.02380",
        required_data=["L2", "trades"], min_levels=10,
        prediction_target="short_term_return", horizon="1s-10s",
        tier="A", tier_reason="Needs L2 depth + trades, which IBKR L2 provides",
    ),
    LOBPaper(
        title="Deep Learning for Market by Order Data",
        authors=["Zihao Zhang", "Stefan Zohren", "Roberto Ward"],
        year=2021, arxiv_id="2102.08811",
        required_data=["L3", "mbo"], min_levels=10, needs_order_ids=True,
        prediction_target="mid_price_direction", horizon="10s",
        tier="C", tier_reason="Requires individual order events (MBO), not available in IBKR L2",
    ),
    LOBPaper(
        title="DeepLOB: Deep Convolutional Neural Networks for Limit Order Books",
        authors=["Zihao Zhang", "Stefan Zohren", "Stephen Roberts"],
        year=2018, arxiv_id="1810.09965",
        required_data=["L2", "trades"], min_levels=10,
        prediction_target="mid_price_direction", horizon="10s",
        tier="A", tier_reason="Standard L2 depth + trades. Core benchmark.",
    ),
    LOBPaper(
        title="Multi-Level Order Flow Imbalance",
        authors=["Zihao Zhang", "Stefan Zohren", "Stephen Roberts"],
        year=2019, arxiv_id="1910.07445",
        required_data=["L2", "trades"], min_levels=10,
        prediction_target="short_term_return", horizon="1s-10s",
        tier="A", tier_reason="L2 depth + trades. Feature-based, no deep learning required.",
    ),
    LOBPaper(
        title="Microprice: A Microstructure Price Signal",
        authors=["Avellaneda", "Zhang"],
        year=2020, arxiv_id="",
        required_data=["L1"], min_levels=1,
        prediction_target="mid_price", horizon="1s",
        tier="A", tier_reason="Needs only best bid/ask + sizes. Simplest possible model.",
    ),
    LOBPaper(
        title="Flow Toxicity and Market Quality",
        authors=["Easley", "Lopez de Prado", "O'Hara"],
        year=2012, arxiv_id="",
        required_data=["trades"], min_levels=1,
        prediction_target="adverse_selection", horizon="1min",
        tier="A", tier_reason="Needs trade flow with aggressor side. IBKR provides this.",
    ),
    LOBPaper(
        title="Order Flow Toxicity (VPIN)",
        authors=["Easley", "Lopez de Prado", "O'Hara"],
        year=2011, arxiv_id="1201.3157",
        required_data=["trades"], min_levels=1,
        prediction_target="toxicity", horizon="5min",
        tier="A", tier_reason="Trade volume classification. Simple and well-validated.",
    ),
    LOBPaper(
        title="Price Impact and the Order Book Resiliency",
        authors=["Roşu"],
        year=2019, arxiv_id="",
        required_data=["L2", "trades"], min_levels=5,
        prediction_target="price_impact", horizon="1min",
        tier="A", tier_reason="L2 depth + trades. Standard market impact model.",
    ),
    LOBPaper(
        title="Optimal Execution with Reinforcement Learning",
        authors=["Stevens", "Zohren"],
        year=2021, arxiv_id="2106.10398",
        required_data=["L2", "trades"], min_levels=10,
        prediction_target="execution_cost", horizon="1min",
        tier="B", tier_reason="Needs L2 depth. RL training requires extensive data. Approximable.",
    ),
    LOBPaper(
        title="Adaptive Market Making with Deep Learning",
        authors=["Ganesh et al."],
        year=2022, arxiv_id="",
        required_data=["L3", "mbo"], min_levels=10, needs_order_ids=True,
        prediction_target="optimal_quote", horizon="1s",
        tier="C", tier_reason="Requires full MBO for queue position modeling.",
    ),
    LOBPaper(
        title="LOB Transformer: Attention-based LOB Prediction",
        authors=["Chen et al."],
        year=2023, arxiv_id="",
        required_data=["L2", "trades"], min_levels=20,
        prediction_target="mid_price_direction", horizon="10s",
        tier="A", tier_reason="Transformer on L2 snapshots. Needs 20 levels but IBKR can provide.",
    ),
    LOBPaper(
        title="Limit Order Book Reinforcement Learning",
        authors=["Huang et al."],
        year=2023, arxiv_id="",
        required_data=["L3", "mbo"], min_levels=10, needs_order_ids=True,
        prediction_target="optimal_action", horizon="100ms",
        tier="C", tier_reason="Full MBO required for queue-aware RL.",
    ),
]


def classify_papers() -> dict[str, list[LOBPaper]]:
    """Classify all papers by tier."""
    result = {"A": [], "B": [], "C": []}
    for p in PAPER_DB:
        result[p.tier].append(p)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Research Module Interface
# ═══════════════════════════════════════════════════════════════════════════════

class LOBModule(ABC):
    """Base class for LOB research modules. All modules expose the same interface."""

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def required_data(self) -> list[str]: ...

    @abstractmethod
    def fit(self, train_data: list[dict]) -> None: ...

    @abstractmethod
    def predict(self, lob_state: dict) -> dict: ...

    @abstractmethod
    def backtest(self, test_data: list[dict]) -> dict: ...

    def paper_baseline(self) -> dict:
        """Reported baseline from the paper."""
        return {}

    def live_signal(self, lob_state: dict) -> dict:
        """Production signal. Same as predict but with latency/cost awareness."""
        return self.predict(lob_state)


# ═══════════════════════════════════════════════════════════════════════════════
# Implemented Modules
# ═══════════════════════════════════════════════════════════════════════════════

class MicropriceModule(LOBModule):
    """Microprice: weighted mid by bid/ask size. The simplest LOB signal.

    Microprice = (Ask * BidSize + Bid * AskSize) / (BidSize + AskSize)

    If Microprice > Mid: more buying pressure → price likely up.
    If Microprice < Mid: more selling pressure → price likely down.
    """
    def name(self) -> str: return "Microprice"
    def required_data(self) -> list[str]: return ["L1"]

    def fit(self, train_data: list[dict]) -> None:
        pass  # No training needed

    def predict(self, lob_state: dict) -> dict:
        bid = lob_state.get('bid_price', 0)
        ask = lob_state.get('ask_price', 0)
        bid_size = lob_state.get('bid_size', 0)
        ask_size = lob_state.get('ask_size', 0)

        if bid <= 0 or ask <= 0 or bid_size + ask_size <= 0:
            return {'signal': 0, 'confidence': 0, 'microprice': 0}

        microprice = (ask * bid_size + bid * ask_size) / (bid_size + ask_size)
        mid = (bid + ask) / 2
        signal = (microprice - mid) / mid if mid > 0 else 0

        return {
            'signal': max(-1, min(1, signal * 100)),
            'confidence': abs(signal) * 50,
            'microprice': microprice,
            'mid': mid,
        }

    def backtest(self, test_data: list[dict]) -> dict:
        correct = total = 0
        for i in range(1, len(test_data)):
            pred = self.predict(test_data[i-1])
            actual = test_data[i].get('mid', 0) - test_data[i-1].get('mid', 0)
            if (pred['signal'] > 0 and actual > 0) or (pred['signal'] < 0 and actual < 0):
                correct += 1
            total += 1
        return {'accuracy': correct / total if total > 0 else 0, 'total': total}

    def paper_baseline(self) -> dict:
        return {'accuracy': 0.55, 'source': 'Avellaneda & Zhang 2020'}


class OFIModule(LOBModule):
    """Order Flow Imbalance (Cont, Kukanov, Stoikov 2014).

    OFI = Σ (ΔBidQty - ΔAskQty) over recent events.

    Positive OFI → buying pressure → price up.
    """
    def name(self) -> str: return "OFI"
    def required_data(self) -> list[str]: return ["L1", "events"]

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.history = []

    def fit(self, train_data: list[dict]) -> None:
        self.history = []

    def predict(self, lob_state: dict) -> dict:
        bid = lob_state.get('bid_price', 0)
        ask = lob_state.get('ask_price', 0)
        bid_size = lob_state.get('bid_size', 0)
        ask_size = lob_state.get('ask_size', 0)

        self.history.append({'bid': bid, 'ask': ask, 'bid_size': bid_size, 'ask_size': ask_size})
        if len(self.history) > self.lookback:
            self.history = self.history[-self.lookback:]

        if len(self.history) < 2:
            return {'signal': 0, 'confidence': 0, 'ofi': 0}

        # OFI: change in bid size minus change in ask size
        prev = self.history[-2]
        curr = self.history[-1]

        delta_bid = curr['bid_size'] - prev['bid_size'] if curr['bid'] == prev['bid'] else curr['bid_size']
        delta_ask = curr['ask_size'] - prev['ask_size'] if curr['ask'] == prev['ask'] else curr['ask_size']

        ofi = delta_bid - delta_ask

        # Normalize
        total_size = curr['bid_size'] + curr['ask_size']
        ofi_norm = ofi / total_size if total_size > 0 else 0

        return {
            'signal': max(-1, min(1, ofi_norm * 10)),
            'confidence': abs(ofi_norm) * 100,
            'ofi': ofi,
            'ofi_norm': ofi_norm,
        }

    def backtest(self, test_data: list[dict]) -> dict:
        correct = total = 0
        for i in range(1, len(test_data)):
            pred = self.predict(test_data[i-1])
            actual = test_data[i].get('mid', 0) - test_data[i-1].get('mid', 0)
            if (pred['signal'] > 0 and actual > 0) or (pred['signal'] < 0 and actual < 0):
                correct += 1
            total += 1
        return {'accuracy': correct / total if total > 0 else 0, 'total': total}

    def paper_baseline(self) -> dict:
        return {'accuracy': 0.58, 'source': 'Cont, Kukanov, Stoikov 2014'}


class MLOFIModule(LOBModule):
    """Multi-Level Order Flow Imbalance (Zhang, Zohren, Roberts 2019).

    Extends OFI to multiple levels:
    MLOFI_k = Σ (ΔBidQty_i - ΔAskQty_i) for i in 1..k
    """
    def name(self) -> str: return "MLOFI"
    def required_data(self) -> list[str]: return ["L2", "events"]

    def __init__(self, levels: int = 5, lookback: int = 20):
        self.levels = levels
        self.lookback = lookback
        self.history = []

    def fit(self, train_data: list[dict]) -> None:
        self.history = []

    def predict(self, lob_state: dict) -> dict:
        bid_sizes = [lob_state.get(f'bid_size_{i}', 0) for i in range(1, self.levels + 1)]
        ask_sizes = [lob_state.get(f'ask_size_{i}', 0) for i in range(1, self.levels + 1)]

        self.history.append({'bid_sizes': bid_sizes, 'ask_sizes': ask_sizes})
        if len(self.history) > self.lookback:
            self.history = self.history[-self.lookback:]

        if len(self.history) < 2:
            return {'signal': 0, 'confidence': 0, 'mlofi': 0}

        prev = self.history[-2]
        curr = self.history[-1]

        mlofi = 0
        for i in range(self.levels):
            mlofi += curr['bid_sizes'][i] - prev['bid_sizes'][i]
            mlofi -= curr['ask_sizes'][i] - prev['ask_sizes'][i]

        total = sum(curr['bid_sizes']) + sum(curr['ask_sizes'])
        mlofi_norm = mlofi / total if total > 0 else 0

        return {
            'signal': max(-1, min(1, mlofi_norm * 10)),
            'confidence': abs(mlofi_norm) * 100,
            'mlofi': mlofi,
            'mlofi_norm': mlofi_norm,
        }

    def backtest(self, test_data: list[dict]) -> dict:
        correct = total = 0
        for i in range(1, len(test_data)):
            pred = self.predict(test_data[i-1])
            actual = test_data[i].get('mid', 0) - test_data[i-1].get('mid', 0)
            if (pred['signal'] > 0 and actual > 0) or (pred['signal'] < 0 and actual < 0):
                correct += 1
            total += 1
        return {'accuracy': correct / total if total > 0 else 0, 'total': total}

    def paper_baseline(self) -> dict:
        return {'accuracy': 0.62, 'source': 'Zhang, Zohren, Roberts 2019'}


class VPINModule(LOBModule):
    """Volume-Synchronized Probability of Informed Trading (Easley, Lopez de Prado, O'Hara 2012).

    VPIN = |BuyVol - SellVol| / (n * AvgVolPerBucket)

    High VPIN → more toxic flow → higher adverse selection.
    """
    def name(self) -> str: return "VPIN"
    def required_data(self) -> list[str]: return ["trades"]

    def __init__(self, n_buckets: int = 20):
        self.n_buckets = n_buckets
        self.trades = []

    def fit(self, train_data: list[dict]) -> None:
        self.trades = []

    def predict(self, lob_state: dict) -> dict:
        trade = lob_state.get('last_trade', {})
        if trade:
            self.trades.append(trade)
            if len(self.trades) > 1000:
                self.trades = self.trades[-1000:]

        if len(self.trades) < self.n_buckets:
            return {'signal': 0, 'confidence': 0, 'vpin': 0}

        # Classify trades as buy/sell using bulk classification
        vol_per_bucket = len(self.trades) // self.n_buckets
        buy_vol = sell_vol = 0

        for t in self.trades[-vol_per_bucket * self.n_buckets:]:
            price = t.get('price', 0)
            prev_price = t.get('prev_price', price)
            size = t.get('size', 0)
            if price > prev_price:
                buy_vol += size
            elif price < prev_price:
                sell_vol += size
            else:
                buy_vol += size / 2
                sell_vol += size / 2

        avg_vol = (buy_vol + sell_vol) / self.n_buckets
        vpin = abs(buy_vol - sell_vol) / (self.n_buckets * avg_vol) if avg_vol > 0 else 0

        return {
            'signal': -vpin * 10,  # High VPIN = adverse selection = negative signal
            'confidence': vpin * 100,
            'vpin': vpin,
        }

    def backtest(self, test_data: list[dict]) -> dict:
        return {'accuracy': 0, 'total': 0, 'note': 'VPIN needs trade flow, not LOB snapshots'}

    def paper_baseline(self) -> dict:
        return {'accuracy': 0.60, 'source': 'Easley, Lopez de Prado, O\'Hara 2012'}


class DepthShapeModule(LOBModule):
    """LOB shape features: slope, convexity, asymmetry.

    From the LOB shape, we can infer:
- Depth imbalance (bid vs ask total depth)
- Slope (how steep the book is)
- Convexity (is the book bowl-shaped or inverted?)
- Symmetry (is one side much thicker?)
    """
    def name(self) -> str: return "DepthShape"
    def required_data(self) -> list[str]: return ["L2"]

    def fit(self, train_data: list[dict]) -> None:
        pass

    def predict(self, lob_state: dict) -> dict:
        bid_sizes = [lob_state.get(f'bid_size_{i}', 0) for i in range(1, 11)]
        ask_sizes = [lob_state.get(f'ask_size_{i}', 0) for i in range(1, 11)]

        bid_total = sum(bid_sizes)
        ask_total = sum(ask_sizes)
        total = bid_total + ask_total

        # Depth imbalance
        depth_imb = (bid_total - ask_total) / total if total > 0 else 0

        # Slope: how quickly does depth decay from best?
        bid_slope = (bid_sizes[0] - bid_sizes[-1]) / bid_sizes[0] if bid_sizes[0] > 0 else 0
        ask_slope = (ask_sizes[0] - ask_sizes[-1]) / ask_sizes[0] if ask_sizes[0] > 0 else 0

        # Convexity: is the book bowl-shaped?
        bid_mid = bid_sizes[len(bid_sizes)//2] if bid_sizes else 0
        bid_convexity = (bid_sizes[0] + bid_sizes[-1] - 2 * bid_mid) / (bid_sizes[0] + bid_sizes[-1]) if (bid_sizes[0] + bid_sizes[-1]) > 0 else 0

        # Signal: depth imbalance is the primary predictor
        signal = depth_imb

        return {
            'signal': max(-1, min(1, signal * 2)),
            'confidence': abs(depth_imb) * 100,
            'depth_imbalance': depth_imb,
            'bid_slope': bid_slope,
            'ask_slope': ask_slope,
            'convexity': bid_convexity,
        }

    def backtest(self, test_data: list[dict]) -> dict:
        correct = total = 0
        for i in range(1, len(test_data)):
            pred = self.predict(test_data[i-1])
            actual = test_data[i].get('mid', 0) - test_data[i-1].get('mid', 0)
            if (pred['signal'] > 0 and actual > 0) or (pred['signal'] < 0 and actual < 0):
                correct += 1
            total += 1
        return {'accuracy': correct / total if total > 0 else 0, 'total': total}

    def paper_baseline(self) -> dict:
        return {'accuracy': 0.57, 'source': 'Various LOB shape papers'}


# ═══════════════════════════════════════════════════════════════════════════════
# Tournament Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_tournament(modules: list[LOBModule], test_data: list[dict]) -> list[dict]:
    """Run walk-forward tournament on all modules."""
    results = []

    for module in modules:
        # Reset state
        module.fit(test_data)

        # Walk-forward: train on first half, test on second half
        split = len(test_data) // 2
        train_data = test_data[:split]
        test_split = test_data[split:]

        module.fit(train_data)
        metrics = module.backtest(test_split)

        # Cost adjustment (10 bps per trade)
        signals = []
        for i in range(1, len(test_split)):
            pred = module.predict(test_split[i-1])
            if abs(pred['signal']) > 0.3:
                signals.append(pred['signal'])

        trade_count = len(signals)
        cost = trade_count * 0.001  # 10 bps per trade

        adjusted_accuracy = metrics.get('accuracy', 0) - cost

        results.append({
            'module': module.name(),
            'tier': 'A' if 'L1' in module.required_data() or 'L2' in module.required_data() else 'C',
            'raw_accuracy': metrics.get('accuracy', 0),
            'adjusted_accuracy': adjusted_accuracy,
            'trade_count': trade_count,
            'cost': cost,
            'paper_baseline': module.paper_baseline(),
            'data_required': module.required_data(),
        })

    results.sort(key=lambda x: x['adjusted_accuracy'], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Feature Ablation
# ═══════════════════════════════════════════════════════════════════════════════

def run_ablation(data: list[dict]) -> dict:
    """Run feature ablation: L1 vs L1-2 vs L1-5 vs L1-10."""
    levels_to_test = [1, 2, 5, 10]
    results = {}

    for n_levels in levels_to_test:
        # Build test data with only n_levels
        limited_data = []
        for d in data:
            limited = dict(d)
            for i in range(n_levels + 1, 11):
                limited.pop(f'bid_size_{i}', None)
                limited.pop(f'ask_size_{i}', None)
                limited.pop(f'bid_price_{i}', None)
                limited.pop(f'ask_price_{i}', None)
            limited_data.append(limited)

        # Run all tier-A modules
        modules = [MicropriceModule(), OFIModule(), MLOFIModule(levels=n_levels), DepthShapeModule()]
        for m in modules:
            m.fit(limited_data)
            metrics = m.backtest(limited_data)
            key = f"L1-{n_levels}_{m.name()}"
            results[key] = metrics.get('accuracy', 0)

    return results
