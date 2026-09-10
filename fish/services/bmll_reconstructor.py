"""BMLL L3 Book Reconstructor — Reconstruct order book from L3 events.

Input: BMLL L3 CSV (VOD, AAPL, etc.)
Output: Order book snapshots + Mantis features

Schema:
- LobAction: 2=add, 3=modify/execute, 4=cancel
- Side: 1=bid, 2=ask
- Price, Size, OrderId
- MarketState: CLOSED, OPENING_AUCTION, CONTINUOUS_TRADING
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Order:
    """Single order in the book."""
    order_id: str
    side: str  # BID or ASK
    price: float
    size: int
    timestamp: str
    event_no: int


@dataclass
class BookSnapshot:
    """Point-in-time book state."""
    timestamp: str
    market_state: str
    bids: dict  # price -> total size
    asks: dict  # price -> total size
    bid_levels: list = field(default_factory=list)  # [(price, size), ...] sorted
    ask_levels: list = field(default_factory=list)
    spread: float = 0.0
    mid: float = 0.0
    obi_1: float = 0.0
    obi_5: float = 0.0
    microprice: float = 0.0
    n_orders_bid: int = 0
    n_orders_ask: int = 0


def parse_bmll_csv(path: str, target_ticker: str = None) -> list[dict]:
    """Parse BMLL L3 CSV into events."""
    events = []
    with open(path, newline='') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        for row in reader:
            if len(row) < 30:
                continue
            ticker = row[1]
            if target_ticker and ticker != target_ticker:
                continue
            events.append({
                'ticker': ticker,
                'timestamp': row[5],
                'side': 'BID' if row[8] == '1' else 'ASK',
                'action': int(row[9]),
                'order_id': row[13],
                'price': float(row[11]) if row[11] else 0,
                'size': int(row[12]) if row[12] else 0,
                'old_price': float(row[14]) if row[14] else 0,
                'old_size': int(row[15]) if row[15] else 0,
                'executed': row[17] == 'True',
                'exec_price': float(row[18]) if row[18] else 0,
                'exec_size': int(row[19]) if row[19] else 0,
                'market_state': row[27],
            })
    return events


def reconstruct_books(events: list[dict], max_levels: int = 10) -> list[BookSnapshot]:
    """Reconstruct book snapshots from L3 events."""
    book = {}  # order_id -> Order
    snapshots = []
    last_state = None
    event_count = 0

    for ev in events:
        oid = ev['order_id']
        action = ev['action']

        if action == 2:  # ADD
            book[oid] = Order(
                order_id=oid,
                side=ev['side'],
                price=ev['price'],
                size=ev['size'],
                timestamp=ev['timestamp'],
                event_no=event_count,
            )
        elif action == 3:  # MODIFY/EXECUTE
            if oid in book:
                if ev['executed']:
                    # Partial or full execution
                    remaining = book[oid].size - ev['exec_size']
                    if remaining <= 0:
                        del book[oid]
                    else:
                        book[oid].size = remaining
                else:
                    # Modify
                    book[oid].price = ev['price']
                    book[oid].size = ev['size']
        elif action == 4:  # CANCEL
            book.pop(oid, None)

        event_count += 1

        # Take snapshot every 100 events
        if event_count % 100 == 0:
            ms = ev['market_state']
            if ms != last_state or event_count % 1000 == 0:
                snap = _book_to_snapshot(book, ev['timestamp'], ms, max_levels)
                if snap:
                    snapshots.append(snap)
                last_state = ms

    # Final snapshot
    if events:
        snap = _book_to_snapshot(book, events[-1]['timestamp'], events[-1]['market_state'], max_levels)
        if snap:
            snapshots.append(snap)

    return snapshots


def _book_to_snapshot(book: dict, timestamp: str, market_state: str, max_levels: int) -> BookSnapshot:
    """Convert order dict to book snapshot."""
    bids = defaultdict(int)
    asks = defaultdict(int)
    n_bid = n_ask = 0

    for oid, order in book.items():
        if order.side == 'BID':
            bids[order.price] += order.size
            n_bid += 1
        else:
            asks[order.price] += order.size
            n_ask += 1

    bid_levels = sorted(bids.items(), reverse=True)[:max_levels]
    ask_levels = sorted(asks.items())[:max_levels]

    best_bid = bid_levels[0][0] if bid_levels else 0
    best_ask = ask_levels[0][0] if ask_levels else 0
    spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0
    mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0

    # OBI
    bid_size_1 = bid_levels[0][1] if bid_levels else 0
    ask_size_1 = ask_levels[0][1] if ask_levels else 0
    obi_1 = (bid_size_1 - ask_size_1) / (bid_size_1 + ask_size_1) if (bid_size_1 + ask_size_1) > 0 else 0

    bid_size_5 = sum(s for _, s in bid_levels[:5])
    ask_size_5 = sum(s for _, s in ask_levels[:5])
    obi_5 = (bid_size_5 - ask_size_5) / (bid_size_5 + ask_size_5) if (bid_size_5 + ask_size_5) > 0 else 0

    # Microprice
    if bid_size_1 + ask_size_1 > 0:
        microprice = (best_ask * bid_size_1 + best_bid * ask_size_1) / (bid_size_1 + ask_size_1)
    else:
        microprice = mid

    return BookSnapshot(
        timestamp=timestamp,
        market_state=market_state,
        bids=dict(bids),
        asks=dict(asks),
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        spread=spread,
        mid=mid,
        obi_1=obi_1,
        obi_5=obi_5,
        microprice=microprice,
        n_orders_bid=n_bid,
        n_orders_ask=n_ask,
    )


def compute_book_features(snapshots: list[BookSnapshot]) -> dict:
    """Compute aggregate features from book snapshots."""
    if not snapshots:
        return {}

    spreads = [s.spread for s in snapshots if s.spread > 0]
    obis = [s.obi_1 for s in snapshots]
    depths = [s.n_orders_bid + s.n_orders_ask for s in snapshots]

    # Cancel pressure: how often does the book thin out?
    thin_events = sum(1 for i in range(1, len(snapshots)) if depths[i] < depths[i-1] * 0.9)

    # Wall persistence: how long do large resting orders stay?
    # (Proxy: how stable is the top level size?)
    top_sizes = [s.bid_levels[0][1] if s.bid_levels else 0 for s in snapshots]
    wall_stability = 0
    if len(top_sizes) > 1:
        changes = sum(1 for i in range(1, len(top_sizes)) if abs(top_sizes[i] - top_sizes[i-1]) > top_sizes[i-1] * 0.3)
        wall_stability = 1 - changes / (len(top_sizes) - 1)

    return {
        'total_snapshots': len(snapshots),
        'avg_spread': sum(spreads) / len(spreads) if spreads else 0,
        'avg_obi': sum(obis) / len(obis) if obis else 0,
        'avg_depth': sum(depths) / len(depths) if depths else 0,
        'cancel_pressure': thin_events / len(snapshots) if snapshots else 0,
        'wall_persistence': wall_stability,
        'market_states': list(set(s.market_state for s in snapshots)),
    }


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else '/root/fish/data/lob/bmll/data/L3_EMEA_Sample_20250910.csv'

    print(f'Parsing {path}...')
    events = parse_bmll_csv(path, target_ticker='VOD')
    print(f'VOD events: {len(events)}')

    print('Reconstructing books...')
    snapshots = reconstruct_books(events)
    print(f'Book snapshots: {len(snapshots)}')

    if snapshots:
        print(f'\nFirst snapshot: {snapshots[0].timestamp}')
        print(f'  Bids: {snapshots[0].bid_levels[:3]}')
        print(f'  Asks: {snapshots[0].ask_levels[:3]}')
        print(f'  Spread: {snapshots[0].spread}')
        print(f'  OBI_1: {snapshots[0].obi_1:.3f}')
        print(f'  Microprice: {snapshots[0].microprice:.2f}')

    features = compute_book_features(snapshots)
    print(f'\nFeatures:')
    for k, v in features.items():
        print(f'  {k}: {v}')
