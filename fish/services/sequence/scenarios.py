"""Scenario Engine — Generate plausible future world trajectories.

Methods:
1. Block bootstrap (simplest, v0.1)
2. Regime-conditioned bootstrap (v0.2)
3. VAR/factor state-space (v0.3)
4. Gaussian process (v0.4)
5. Diffusion world model (v0.5)

Start with block bootstrap. Keep the same interface for all methods.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from fish.services.sequence.state import WorldState, compute_world_state, state_to_features


@dataclass
class Scenario:
    """A single simulated future trajectory."""
    states: list[WorldState]
    returns: list[float]
    total_return: float
    max_drawdown: float
    sharpe: float


def block_bootstrap(
    prices: list[dict],
    ticker: str,
    n_scenarios: int = 1000,
    horizon: int = 252,
    block_size: int = 20,
    current_index: int = None,
) -> list[Scenario]:
    """Generate scenarios using block bootstrap.
    
    Resamples blocks of historical returns to create synthetic futures.
    Simple but effective baseline.
    """
    if current_index is None:
        current_index = len(prices) - 1
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    
    # Compute historical returns
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    # Use returns up to current_index
    historical_returns = returns[:current_index]
    
    if len(historical_returns) < block_size * 2:
        return []
    
    # Clip extreme returns
    clipped_returns = [max(-0.20, min(0.20, r)) for r in historical_returns]
    
    # Normalize returns to have realistic statistics
    # Use last 252 days for recent regime
    recent_returns = clipped_returns[-252:] if len(clipped_returns) > 252 else clipped_returns
    mean_ret = sum(recent_returns) / len(recent_returns)
    std_ret = math.sqrt(sum((r - mean_ret)**2 for r in recent_returns) / len(recent_returns))
    
    # Scale to realistic daily returns (mean ~0, std ~0.02)
    if std_ret > 0:
        normalized_returns = [(r - mean_ret) / std_ret * 0.02 for r in clipped_returns]
    else:
        normalized_returns = clipped_returns
    
    scenarios = []
    
    for _ in range(n_scenarios):
        # Generate synthetic returns by resampling blocks
        synthetic_returns = []
        while len(synthetic_returns) < horizon:
            # Random block start
            start = random.randint(0, len(normalized_returns) - block_size)
            block = normalized_returns[start:start + block_size]
            synthetic_returns.extend(block)
        
        synthetic_returns = synthetic_returns[:horizon]
        
        # Compute scenario metrics
        equity = [1.0]
        for r in synthetic_returns:
            equity.append(equity[-1] * (1 + r))
        
        total_return = equity[-1] - 1.0
        
        # Max drawdown
        peak = equity[0]
        max_dd = 0
        for e in equity:
            peak = max(peak, e)
            dd = (e - peak) / peak
            max_dd = min(max_dd, dd)
        
        # Sharpe
        mean_ret = sum(synthetic_returns) / len(synthetic_returns)
        std_ret = math.sqrt(sum((r - mean_ret)**2 for r in synthetic_returns) / len(synthetic_returns))
        sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
        
        scenarios.append(Scenario(
            states=[],  # Would need to reconstruct full states
            returns=synthetic_returns,
            total_return=total_return,
            max_drawdown=max_dd,
            sharpe=sharpe,
        ))
    
    return scenarios


def regime_conditioned_bootstrap(
    prices: list[dict],
    ticker: str,
    n_scenarios: int = 1000,
    horizon: int = 252,
    block_size: int = 20,
    current_index: int = None,
) -> list[Scenario]:
    """Generate scenarios using regime-conditioned bootstrap.
    
    Separate bull/bear/neutral regimes and resample within regime.
    """
    if current_index is None:
        current_index = len(prices) - 1
    
    closes = [p.get("close", p.get("price", 0)) for p in prices]
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    historical_returns = returns[:current_index]
    
    if len(historical_returns) < block_size * 2:
        return []
    
    # Clip extreme returns
    clipped_returns = [max(-0.20, min(0.20, r)) for r in historical_returns]
    
    # Classify regime for each day
    regimes = []
    for i in range(len(historical_returns)):
        if i < 20:
            regimes.append("neutral")
        else:
            # Simple regime: 20-day return
            ret_20d = (closes[min(i+1, len(closes)-1)] - closes[max(0, i-19)]) / closes[max(0, i-19)]
            if ret_20d > 0.05:
                regimes.append("bull")
            elif ret_20d < -0.05:
                regimes.append("bear")
            else:
                regimes.append("neutral")
    
    # Group returns by regime
    regime_returns = {"bull": [], "bear": [], "neutral": []}
    for r, reg in zip(clipped_returns, regimes):
        regime_returns[reg].append(r)
    
    # Determine current regime
    current_regime = regimes[-1] if regimes else "neutral"
    
    # Normalize returns to have realistic statistics
    recent_returns = clipped_returns[-252:] if len(clipped_returns) > 252 else clipped_returns
    mean_ret = sum(recent_returns) / len(recent_returns)
    std_ret = math.sqrt(sum((r - mean_ret)**2 for r in recent_returns) / len(recent_returns))
    
    # Scale to realistic daily returns (mean ~0, std ~0.02)
    if std_ret > 0:
        normalized_regime_returns = {
            reg: [(r - mean_ret) / std_ret * 0.02 for r in rets]
            for reg, rets in regime_returns.items()
        }
    else:
        normalized_regime_returns = regime_returns
    
    scenarios = []
    for _ in range(n_scenarios):
        synthetic_returns = []
        current_reg = current_regime
        
        while len(synthetic_returns) < horizon:
            # Get returns for current regime
            available = normalized_regime_returns.get(current_reg, normalized_regime_returns.get("neutral", []))
            
            if len(available) < block_size:
                available = list(normalized_regime_returns.values())[0] if normalized_regime_returns else [0]
            
            # Random block
            start = random.randint(0, len(available) - block_size)
            block = available[start:start + block_size]
            synthetic_returns.extend(block)
            
            # Regime transition (10% chance)
            if random.random() < 0.1:
                if current_reg == "bull":
                    current_reg = random.choice(["bull", "neutral", "bear"])
                elif current_reg == "bear":
                    current_reg = random.choice(["bear", "neutral", "bull"])
                else:
                    current_reg = random.choice(["bull", "neutral", "bear"])
        
        synthetic_returns = synthetic_returns[:horizon]
        
        # Compute metrics
        equity = [1.0]
        for r in synthetic_returns:
            equity.append(equity[-1] * (1 + r))
        
        total_return = equity[-1] - 1.0
        peak = equity[0]
        max_dd = 0
        for e in equity:
            peak = max(peak, e)
            dd = (e - peak) / peak
            max_dd = min(max_dd, dd)
        
        mean_ret = sum(synthetic_returns) / len(synthetic_returns)
        std_ret = math.sqrt(sum((r - mean_ret)**2 for r in synthetic_returns) / len(synthetic_returns))
        sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
        
        scenarios.append(Scenario(
            states=[],
            returns=synthetic_returns,
            total_return=total_return,
            max_drawdown=max_dd,
            sharpe=sharpe,
        ))
    
    return scenarios


def compute_scenario_statistics(scenarios: list[Scenario]) -> dict:
    """Compute aggregate statistics across scenarios."""
    if not scenarios:
        return {}
    
    returns = [s.total_return for s in scenarios]
    sharpes = [s.sharpe for s in scenarios]
    drawdowns = [s.max_drawdown for s in scenarios]
    
    # Sort for percentiles
    returns.sort()
    sharpes.sort()
    drawdowns.sort()
    
    n = len(scenarios)
    
    return {
        "n_scenarios": n,
        "p_profit": sum(1 for r in returns if r > 0) / n,
        "expected_return": sum(returns) / n,
        "median_return": returns[n // 2],
        "p05": returns[int(n * 0.05)],
        "p95": returns[int(n * 0.95)],
        "expected_sharpe": sum(sharpes) / n,
        "expected_drawdown": sum(drawdowns) / n,
        "worst_drawdown": drawdowns[0],
        "best_return": returns[-1],
        "worst_return": returns[0],
    }
