"""Mantis Trainer — Train microstructure models on LSE GSK lifecycle data.

Learns:
- Order persistence (how long do orders live?)
- Cancellation probability (what predicts a cancel?)
- Execution probability (what predicts a fill?)
- Wall behavior (when do large orders persist vs cancel?)

Input: LSE GSK 2007 CSVs (OrderDetail + OrderHistory + TradeReport)
Output: Trained feature weights for Mantis signal
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class OrderLifecycle:
    """One order's lifecycle."""
    order_id: str
    side: str
    price: float
    initial_size: int
    events: list  # list of (timestamp, event_type, size_change)
    final_status: str  # cancelled, executed, still_live
    lifetime_seconds: float = 0
    total_fills: int = 0
    total_cancelled: int = 0
    modifications: int = 0


def load_lse_data(detail_path: str, history_path: str) -> list[OrderLifecycle]:
    """Load LSE data and reconstruct order lifecycles."""
    # Load detail (adds)
    orders = {}
    with open(detail_path, newline='') as f:
        for row in csv.reader(f):
            if len(row) < 17:
                continue
            order_id = row[0].strip()
            price_str = row[10].strip()
            size_str = row[11].strip()
            side = row[7].strip()
            date = row[14].strip()
            time = row[15].strip()
            try:
                price = float(price_str)
                size = int(size_str)
            except ValueError:
                continue
            orders[order_id] = {
                'order_id': order_id,
                'side': side,
                'price': price,
                'initial_size': size,
                'add_time': f'{date}T{time}',
                'events': [],
            }

    # Load history (lifecycle)
    with open(history_path, newline='') as f:
        for row in csv.reader(f):
            if len(row) < 15:
                continue
            order_id = row[0].strip()
            action = row[1].strip()
            trade_size_str = row[3].strip() if row[3].strip() else '0'
            date = row[13].strip()
            time = row[14].strip()
            seq = row[12].strip()

            ts = f'{date}T{time}#{seq}'
            event_type = {'M': 'modify', 'D': 'cancel', 'P': 'execute', 'E': 'execute'}.get(action, f'other:{action}')

            try:
                trade_size = int(trade_size_str)
            except ValueError:
                trade_size = 0

            if order_id in orders:
                orders[order_id]['events'].append((ts, event_type, trade_size))

    # Build lifecycles
    lifecycles = []
    for oid, data in orders.items():
        events = data['events']
        if not events:
            status = 'still_live'
        else:
            last_event = events[-1][1]
            status = 'executed' if last_event == 'execute' else 'cancelled' if last_event == 'cancel' else 'modified'

        # Compute lifetime
        fills = sum(1 for _, e, _ in events if e == 'execute')
        cancels = sum(1 for _, e, _ in events if e == 'cancel')
        mods = sum(1 for _, e, _ in events if e == 'modify')

        lc = OrderLifecycle(
            order_id=oid,
            side=data['side'],
            price=data['price'],
            initial_size=data['initial_size'],
            events=events,
            final_status=status,
            total_fills=fills,
            total_cancelled=cancels,
            modifications=mods,
        )
        lifecycles.append(lc)

    return lifecycles


def compute_features(lifecycles: list[OrderLifecycle]) -> dict:
    """Compute Mantis features from lifecycle data."""
    total = len(lifecycles)
    if total == 0:
        return {}

    # Cancel rate
    cancelled = sum(1 for lc in lifecycles if lc.final_status == 'cancelled')
    executed = sum(1 for lc in lifecycles if lc.final_status == 'executed')
    still_live = sum(1 for lc in lifecycles if lc.final_status == 'still_live')

    # Modification rate
    total_mods = sum(lc.modifications for lc in lifecycles)
    avg_mods = total_mods / total

    # Execution rate
    exec_rate = executed / total

    # Cancel probability by side
    buy_cancels = sum(1 for lc in lifecycles if lc.side == 'B' and lc.final_status == 'cancelled')
    sell_cancels = sum(1 for lc in lifecycles if lc.side == 'S' and lc.final_status == 'cancelled')
    buy_total = sum(1 for lc in lifecycles if lc.side == 'B')
    sell_total = sum(1 for lc in lifecycles if lc.side == 'S')

    # Size distribution
    sizes = [lc.initial_size for lc in lifecycles]
    avg_size = sum(sizes) / len(sizes)

    # Price distribution
    prices = [lc.price for lc in lifecycles]
    avg_price = sum(prices) / len(prices)

    # Event sequence patterns
    # How many events per order?
    event_counts = [len(lc.events) for lc in lifecycles]
    avg_events = sum(event_counts) / len(event_counts)

    # What fraction of orders have modify before cancel?
    modify_then_cancel = 0
    for lc in lifecycles:
        event_types = [e[1] for e in lc.events]
        if 'modify' in event_types and 'cancel' in event_types:
            first_mod = event_types.index('modify')
            first_cancel = event_types.index('cancel')
            if first_mod < first_cancel:
                modify_then_cancel += 1

    modify_then_cancel_rate = modify_then_cancel / total if total > 0 else 0

    return {
        'total_orders': total,
        'cancel_rate': round(cancelled / total, 4),
        'execution_rate': round(exec_rate, 4),
        'still_live_rate': round(still_live / total, 4),
        'avg_modifications': round(avg_mods, 2),
        'avg_events_per_order': round(avg_events, 2),
        'modify_then_cancel_rate': round(modify_then_cancel_rate, 4),
        'buy_cancel_rate': round(buy_cancels / buy_total, 4) if buy_total > 0 else 0,
        'sell_cancel_rate': round(sell_cancels / sell_total, 4) if sell_total > 0 else 0,
        'avg_size': round(avg_size, 0),
        'avg_price': round(avg_price, 2),
        'executed': executed,
        'cancelled': cancelled,
        'still_live': still_live,
    }


def train_mantis_weights(lifecycles: list[OrderLifecycle]) -> dict:
    """Train Mantis feature weights from lifecycle data.

    Returns weights for:
    - wall_persistence: how likely a large order stays live
    - cancel_pressure: how likely nearby orders get cancelled
    - execution_flow: how likely an order gets executed
    - modification_rate: how actively orders are being modified
    """
    features = compute_features(lifecycles)

    # Wall persistence: fraction of large orders that stay live
    large_orders = [lc for lc in lifecycles if lc.initial_size > 1000]
    wall_persistence = sum(1 for lc in large_orders if lc.final_status == 'still_live') / len(large_orders) if large_orders else 0

    # Cancel pressure: cancel rate for orders near the best bid/ask
    # (proxy: orders with size > median are more likely to be "real")
    median_size = sorted(lc.initial_size for lc in lifecycles)[len(lifecycles) // 2]
    large_cancel_rate = sum(1 for lc in lifecycles if lc.initial_size > median_size and lc.final_status == 'cancelled') / sum(1 for lc in lifecycles if lc.initial_size > median_size)

    # Execution flow: what fraction of small orders get executed quickly?
    small_orders = [lc for lc in lifecycles if lc.initial_size < median_size]
    small_exec_rate = sum(1 for lc in small_orders if lc.final_status == 'executed') / len(small_orders) if small_orders else 0

    return {
        'wall_persistence': round(wall_persistence, 4),
        'cancel_pressure': round(features['cancel_rate'], 4),
        'execution_flow': round(features['execution_rate'], 4),
        'modification_rate': round(features['avg_modifications'], 2),
        'modify_then_cancel_rate': round(features['modify_then_cancel_rate'], 4),
        'large_order_cancel_rate': round(large_cancel_rate, 4),
        'small_order_exec_rate': round(small_exec_rate, 4),
        'features': features,
    }


if __name__ == '__main__':
    import sys
    detail_path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/data-hunt/lse-gsk/Reconstructing/data/Data/allGlaxoOrderDetail.CSV'
    history_path = sys.argv[2] if len(sys.argv) > 2 else '/tmp/data-hunt/lse-gsk/Reconstructing/data/Data/allGlaxoOrderHistory.CSV'

    print('Loading LSE GSK data...')
    lifecycles = load_lse_data(detail_path, history_path)
    print(f'Loaded {len(lifecycles)} order lifecycles')

    print('\nComputing features...')
    features = compute_features(lifecycles)
    for k, v in features.items():
        print(f'  {k}: {v}')

    print('\nTraining Mantis weights...')
    weights = train_mantis_weights(lifecycles)
    for k, v in weights.items():
        if k != 'features':
            print(f'  {k}: {v}')
