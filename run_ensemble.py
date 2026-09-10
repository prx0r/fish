#!/usr/bin/env python3
"""Run ensemble on Chris Prior's basket using pre-loaded prices.json."""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fish.services.baselines import BASELINE_STRATEGIES, _closes
from fish.services.fox import FOX_STRATEGIES
from fish.services.shark import SHARK_STRATEGIES
from fish.services.hedgehog import HEDGEHOG_STRATEGIES
from fish.services.wolf import WOLF_STRATEGIES

ALL_STRATEGIES = {**BASELINE_STRATEGIES, **FOX_STRATEGIES, **SHARK_STRATEGIES, **HEDGEHOG_STRATEGIES, **WOLF_STRATEGIES}


def run_ticker(ticker: str, prices: list[dict]) -> dict:
    results = []
    for name, fn in ALL_STRATEGIES.items():
        try:
            r = fn(prices=prices)
            if r and r.trades:
                results.append(r)
        except Exception:
            pass

    results.sort(key=lambda r: r.sharpe if math.isfinite(r.sharpe) else -999, reverse=True)

    p = prices[-1]['close']
    r1d = (prices[-1]['close'] - prices[-2]['close']) / prices[-2]['close'] * 100 if len(prices) > 1 else 0
    r20 = (prices[-1]['close'] - prices[-21]['close']) / prices[-21]['close'] * 100 if len(prices) > 21 else 0
    r60 = (prices[-1]['close'] - prices[-61]['close']) / prices[-61]['close'] * 100 if len(prices) > 61 else 0

    lc = sc = 0
    for r in results:
        if r.trades:
            last = r.trades[-1].get('action', '')
            if last == 'BUY': lc += 1
            elif last == 'SELL': sc += 1
    tot = lc + sc
    con = lc / tot if tot > 0 else 0.5
    d = 'LONG' if con > 0.6 else ('SHORT' if con < 0.4 else 'FLAT')

    top5 = []
    for r in results[:5]:
        if math.isfinite(r.sharpe):
            top5.append({'name': r.name, 'sharpe': round(r.sharpe, 2), 'return': round(r.total_return * 100, 1),
                         'max_dd': round(r.max_drawdown * 100, 1), 'win_rate': round(r.win_rate, 1), 'trades': r.trades_count})

    return {'ticker': ticker, 'price': p, 'days': len(prices), 'ret_1d': round(r1d, 2),
            'ret_20d': round(r20, 2), 'ret_60d': round(r60, 2), 'direction': d, 'consensus': round(con, 2),
            'long_votes': lc, 'short_votes': sc, 'total_strategies': len(results), 'top5': top5}


def main():
    data = json.loads(Path('/root/fish/data/prices.json').read_text())
    
    print("FISH ENSEMBLE — Chris Prior's Basket")
    print(f"Strategies: {len(ALL_STRATEGIES)} total ({len(BASELINE_STRATEGIES)} baseline + {len(FOX_STRATEGIES)} fox + {len(SHARK_STRATEGIES)} shark + {len(HEDGEHOG_STRATEGIES)} hedgehog + {len(WOLF_STRATEGIES)} wolf)")
    print("=" * 95)
    print(f"{'TICKER':6s}  {'PRICE':>8s}  {'SIG':5s}  {'CON':>4s}  {'1D':>6s}  {'20D':>7s}  {'60D':>7s}  {'VOTE(L/S/T)'}")
    print("-" * 95)

    all_results = []
    for ticker, prices_raw in data.items():
        if len(prices_raw) < 60:
            print(f"{ticker:6s}  SKIP (only {len(prices_raw)} days)")
            continue
        # Ensure all keys strategies expect
        prices = []
        for p in prices_raw:
            prices.append({
                'date': p.get('date', ''),
                'price': p.get('price', 0),
                'close': p.get('close', p.get('price', 0)),
                'open': p.get('open', p.get('price', 0)),
                'high': p.get('high', p.get('price', 0)),
                'low': p.get('low', p.get('price', 0)),
                'volume': p.get('volume', 1_000_000),
            })
        r = run_ticker(ticker, prices)
        all_results.append(r)
        arrow = {'LONG': '\033[92m▲\033[0m', 'SHORT': '\033[91m▼\033[0m', 'FLAT': '\033[90m—\033[0m'}[r['direction']]
        print(f"{r['ticker']:6s}  ${r['price']:>8.2f}  {arrow} {r['direction']:5s}  {r['consensus']:>3.0%}  "
              f"{r['ret_1d']:+5.1f}%  {r['ret_20d']:+6.1f}%  {r['ret_60d']:+6.1f}%  "
              f"{r['long_votes']}/{r['short_votes']}/{r['total_strategies']}")

    print("\n" + "=" * 95)
    print("TOP 5 STRATEGIES PER TICKER")
    print("=" * 95)
    for r in all_results:
        if r['top5']:
            print(f"\n{r['ticker']} — {r['direction']} (consensus {r['consensus']:.0%}, ${r['price']:.2f})")
            for s in r['top5']:
                print(f"  {s['name']:25s}  Sharpe={s['sharpe']:+.2f}  Ret={s['return']:+.1f}%  MaxDD={s['max_dd']:.1f}%  Win={s['win_rate']:.0f}%  Trades={s['trades']}")

    # Summary
    longs = [r for r in all_results if r['direction'] == 'LONG']
    shorts = [r for r in all_results if r['direction'] == 'SHORT']
    flats = [r for r in all_results if r['direction'] == 'FLAT']
    print(f"\n{'=' * 95}")
    print(f"SUMMARY: {len(longs)} LONG  |  {len(flats)} FLAT  |  {len(shorts)} SHORT")
    if longs:
        print(f"  LONG:  {', '.join(r['ticker'] for r in longs)}")
    if flats:
        print(f"  FLAT:  {', '.join(r['ticker'] for r in flats)}")
    if shorts:
        print(f"  SHORT: {', '.join(r['ticker'] for r in shorts)}")

    out = Path('/root/fish/data/ensemble_results.json')
    out.write_text(json.dumps(all_results, indent=2))
    print(f"\nSaved to {out}")


if __name__ == '__main__':
    main()
