#!/usr/bin/env python3
"""Walk-Forward Ensemble Backtest — Chris Prior's Basket.

Architecture:
- Train on 252 days (1 year)
- Test on 63 days (3 months)
- Step forward 63 days
- At each test window: run all strategies on train data, vote on direction,
  apply that direction to test period
- Track equity curve vs buy-and-hold
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fish.services.baselines import BASELINE_STRATEGIES, _closes, _sharpe, _sortino, _max_drawdown
from fish.services.fox import FOX_STRATEGIES
from fish.services.shark import SHARK_STRATEGIES
from fish.services.hedgehog import HEDGEHOG_STRATEGIES
from fish.services.wolf import WOLF_STRATEGIES

ALL_STRATEGIES = {**BASELINE_STRATEGIES, **FOX_STRATEGIES, **SHARK_STRATEGIES, **HEDGEHOG_STRATEGIES, **WOLF_STRATEGIES}


def _cached_ensemble_vote(prices: list[dict], cache: dict, day_idx: int) -> float:
    """Run ensemble vote, caching results every 5 days."""
    # Round to nearest 5-day boundary
    bucket = (day_idx // 5) * 5
    if bucket in cache:
        return cache[bucket]

    if day_idx < 252:
        cache[bucket] = 0.0
        return 0.0

    train_prices = prices[:day_idx]
    long_count = short_count = total = 0

    for name, fn in ALL_STRATEGIES.items():
        try:
            r = fn(prices=train_prices)
            if r and r.trades:
                last = r.trades[-1].get('action', '')
                if last == 'BUY':
                    long_count += 1; total += 1
                elif last == 'SELL':
                    short_count += 1; total += 1
        except Exception:
            pass

    consensus = long_count / total if total > 0 else 0.5
    vote = 1.0 if consensus > 0.6 else (-1.0 if consensus < 0.4 else 0.0)
    cache[bucket] = vote
    return vote


def ensemble_signal(prices: list[dict], i: int, current_position: float) -> float:
    """Ensemble signal: cached vote every 5 days."""
    vote = _cached_ensemble_vote(prices, ensemble_signal._cache, i)
    if vote == -1.0 and current_position <= 0:
        return 0.0  # Can't short, just go flat
    return vote

ensemble_signal._cache = {}


def buyhold_signal(prices: list[dict], i: int, current_position: float) -> float:
    """Buy-and-hold benchmark."""
    return 1.0


def compute_equity(name: str, prices: list[dict], signal_fn, cost_bps: float = 10, capital: float = 10000) -> dict:
    """Compute strategy equity curve."""
    closes = [p.get('close', p.get('price', 0)) for p in prices]
    dates = [p.get('date', '') for p in prices]

    equity = [capital]
    positions = [0.0]
    strat_returns = [0.0]
    asset_returns = [0.0]
    trades = []
    position = 0.0
    n_trades = 0

    for i in range(1, len(prices)):
        new_pos = signal_fn(prices, i, position)

        # Cost on position change
        turnover = abs(new_pos - position)
        cost = turnover * (cost_bps / 10000) * capital

        if turnover > 0:
            n_trades += 1
            trades.append({
                'day': i,
                'date': dates[i],
                'action': 'BUY' if new_pos > position else 'SELL',
                'price': closes[i],
                'pnl': 0,  # Will fill below
            })

        # Asset return
        asset_ret = (closes[i] - closes[i-1]) / closes[i-1] if closes[i-1] != 0 else 0

        # Strategy return = previous position * asset return - costs
        strat_ret = position * asset_ret - (cost / capital)

        new_eq = equity[-1] * (1 + strat_ret)
        equity.append(new_eq)
        positions.append(new_pos)
        strat_returns.append(strat_ret)
        asset_returns.append(asset_ret)
        position = new_pos

    # Fill PnL on trades
    for j in range(len(trades)):
        d = trades[j]['day']
        if j + 1 < len(trades):
            exit_day = trades[j+1]['day']
        else:
            exit_day = len(prices) - 1
        trades[j]['pnl'] = (closes[exit_day] - trades[j]['price']) * 1000

    # Metrics
    total_ret = (equity[-1] - equity[0]) / equity[0]
    bh_ret = (closes[-1] - closes[0]) / closes[0]
    bh_equity = [capital]
    for i in range(1, len(closes)):
        bh_equity.append(bh_equity[-1] * (1 + asset_returns[i-1]))

    sharpe = _sharpe(strat_returns)
    sortino = _sortino(strat_returns)
    max_dd = _max_drawdown(equity)
    bh_sharpe = _sharpe(asset_returns)
    bh_max_dd = _max_drawdown(bh_equity)

    wins = sum(1 for t in trades if t['action'] == 'SELL' and t['pnl'] > 0)
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    win_rate = wins / len(sell_trades) * 100 if sell_trades else 0

    return {
        'name': name,
        'ticker': prices[0].get('ticker', 'unknown'),
        'days': len(prices),
        'total_return': round(total_ret * 100, 2),
        'bh_return': round(bh_ret * 100, 2),
        'alpha': round((total_ret - bh_ret) * 100, 2),
        'sharpe': round(sharpe, 2),
        'bh_sharpe': round(bh_sharpe, 2),
        'sortino': round(sortino, 2),
        'max_drawdown': round(max_dd * 100, 2),
        'bh_max_drawdown': round(bh_max_dd * 100, 2),
        'trades': len(trades),
        'win_rate': round(win_rate, 1),
        'equity_final': round(equity[-1], 2),
        'bh_equity_final': round(bh_equity[-1], 2),
        'equity_curve': [round(e, 2) for e in equity[::21]],  # Weekly samples
        'bh_equity_curve': [round(e, 2) for e in bh_equity[::21]],
        'dates_sampled': dates[::21],
    }


def main():
    data = json.loads(Path('/root/fish/data/prices.json').read_text())

    print("FISH WALK-FORWARD ENSEMBLE BACKTEST")
    print("=" * 100)
    print(f"{'TICKER':6s}  {'ENSEMBLE':>10s}  {'B&H':>10s}  {'ALPHA':>8s}  {'SHARPE':>7s}  {'B&H SH':>7s}  "
          f"{'MAXDD':>7s}  {'B&H DD':>7s}  {'TRADES':>6s}  {'WIN%':>5s}")
    print("-" * 100)

    all_results = []

    for ticker, raw_prices in data.items():
        if len(raw_prices) < 315:  # Need at least 1.25 years
            print(f"{ticker:6s}  SKIP ({len(raw_prices)} days)")
            continue

        # Add close key
        prices = [{
            'date': p.get('date', ''),
            'price': p.get('price', 0),
            'close': p.get('close', p.get('price', 0)),
            'open': p.get('open', p.get('price', 0)),
            'high': p.get('high', p.get('price', 0)),
            'low': p.get('low', p.get('price', 0)),
            'volume': p.get('volume', 1_000_000),
        } for p in raw_prices]

        # Reset ensemble cache per ticker
        ensemble_signal._cache = {}

        # Ensemble backtest
        ens = compute_equity('Ensemble', prices, ensemble_signal)
        ens['ticker'] = ticker

        # Buy-and-hold backtest
        bh = compute_equity('Buy & Hold', prices, buyhold_signal, cost_bps=0)
        bh['ticker'] = ticker

        all_results.append(ens)

        print(f"{ticker:6s}  ${ens['total_return']:>+8.1f}%  ${bh['total_return']:>+8.1f}%  {ens['alpha']:>+7.1f}%  "
              f"{ens['sharpe']:>6.2f}  {bh['sharpe']:>6.2f}  "
              f"{ens['max_drawdown']:>6.1f}%  {bh['max_drawdown']:>6.1f}%  "
              f"{ens['trades']:>5d}  {ens['win_rate']:>4.0f}%")

    # Summary
    print("\n" + "=" * 100)
    alphas = [r['alpha'] for r in all_results]
    sharpes = [r['sharpe'] for r in all_results]
    winners = sum(1 for a in alphas if a > 0)
    avg_alpha = sum(alphas) / len(alphas) if alphas else 0
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0

    print(f"WINNERS: {winners}/{len(all_results)} beat buy-and-hold")
    print(f"AVG ALPHA: {avg_alpha:+.1f}%")
    print(f"AVG SHARPE: {avg_sharpe:.2f}")

    # Rank by alpha
    all_results.sort(key=lambda r: r['alpha'], reverse=True)
    print(f"\nTOP 5 BY ALPHA:")
    for r in all_results[:5]:
        print(f"  {r['ticker']:6s}  alpha={r['alpha']:+.1f}%  sharpe={r['sharpe']:.2f}  maxdd={r['max_drawdown']:.1f}%  trades={r['trades']}")
    print(f"\nBOTTOM 5:")
    for r in all_results[-5:]:
        print(f"  {r['ticker']:6s}  alpha={r['alpha']:+.1f}%  sharpe={r['sharpe']:.2f}  maxdd={r['max_drawdown']:.1f}%  trades={r['trades']}")

    out = Path('/root/fish/data/backtest_results.json')
    out.write_text(json.dumps(all_results, indent=2))
    print(f"\nSaved to {out}")


if __name__ == '__main__':
    main()
