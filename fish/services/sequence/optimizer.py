"""Policy Optimizer — Find optimal allocation sequence across scenarios.

Objective:
max E[PnL] - λ*Var(PnL) - γ*CVaR - η*Turnover - κ*Costs

Output:
[
  {"day": 0, "weight": 0.14, "confidence": 0.73},
  {"day": 20, "weight": 0.18, "confidence": 0.66},
  {"day": 60, "weight": 0.23, "confidence": 0.54},
  {"day": 120, "weight": 0.17, "confidence": 0.39},
  {"day": 252, "weight": 0.09, "confidence": 0.19},
]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from fish.services.sequence.scenarios import Scenario, compute_scenario_statistics


@dataclass
class PolicyStep:
    """A single step in the policy sequence."""
    day: int
    weight: float
    confidence: float
    action: str = "HOLD"
    delta_weight: float = 0.0


@dataclass
class Policy:
    """Optimal allocation sequence."""
    steps: list[PolicyStep]
    expected_return: float
    expected_risk: float
    sharpe: float
    cvaR_5pct: float
    turnover: float


def optimize_policy(
    scenarios: list[Scenario],
    current_weight: float,
    risk_aversion: float = 1.0,
    turnover_penalty: float = 0.001,
    cvaR_penalty: float = 0.5,
    max_weight: float = 0.30,
    min_weight: float = 0.0,
    checkpoints: list[int] = None,
) -> Policy:
    """Find optimal allocation sequence using grid search.
    
    For each checkpoint day, find the weight that maximizes
    expected utility across all scenarios.
    """
    if checkpoints is None:
        checkpoints = [0, 20, 60, 120, 252]
    
    if not scenarios:
        return Policy(steps=[], expected_return=0, expected_risk=0, sharpe=0, cvaR_5pct=0, turnover=0)
    
    # Grid search over possible weights
    weight_grid = [i / 100 for i in range(int(min_weight * 100), int(max_weight * 100) + 1, 2)]
    
    steps = []
    
    for checkpoint in checkpoints:
        best_weight = current_weight
        best_utility = -float('inf')
        
        for target_weight in weight_grid:
            # Compute utility across all scenarios
            utilities = []
            
            for scenario in scenarios:
                if checkpoint >= len(scenario.returns):
                    continue
                
                # Compute portfolio return at this checkpoint
                portfolio_return = 0
                for day in range(min(checkpoint, len(scenario.returns))):
                    # Simplified: use average return for the period
                    day_return = scenario.returns[day]
                    portfolio_return += target_weight * day_return
                
                # Risk penalty
                risk_penalty = risk_aversion * scenario.max_drawdown ** 2
                
                # CVaR penalty (simplified: penalize worst 5% scenarios)
                # Will be computed after all scenarios
                
                # Turnover penalty
                turnover_cost = turnover_penalty * abs(target_weight - current_weight)
                
                utility = portfolio_return - risk_penalty - turnover_cost
                utilities.append(utility)
            
            if not utilities:
                continue
            
            # Expected utility
            expected_utility = sum(utilities) / len(utilities)
            
            # CVaR penalty (worst 5% of scenarios)
            utilities.sort()
            cvar_idx = max(1, int(len(utilities) * 0.05))
            cvar = sum(utilities[:cvar_idx]) / cvar_idx
            cvar_penalty = cvaR_penalty * abs(cvar)
            
            total_utility = expected_utility - cvar_penalty
            
            if total_utility > best_utility:
                best_utility = total_utility
                best_weight = target_weight
        
        # Compute confidence based on scenario agreement
        weight_returns = []
        for scenario in scenarios:
            if checkpoint < len(scenario.returns):
                port_ret = sum(scenario.returns[:checkpoint]) * best_weight
                weight_returns.append(port_ret)
        
        if weight_returns:
            mean_ret = sum(weight_returns) / len(weight_returns)
            std_ret = math.sqrt(sum((r - mean_ret)**2 for r in weight_returns) / len(weight_returns))
            confidence = min(1.0, max(0.0, 0.5 + mean_ret / (std_ret + 0.01)))
        else:
            confidence = 0.5
        
        # Action
        delta = best_weight - current_weight
        if delta > 0.02:
            action = "BUY"
        elif delta < -0.02:
            action = "SELL"
        else:
            action = "HOLD"
        
        steps.append(PolicyStep(
            day=checkpoint,
            weight=best_weight,
            confidence=confidence,
            action=action,
            delta_weight=delta,
        ))
        
        current_weight = best_weight
    
    # Compute aggregate metrics
    all_returns = []
    all_drawdowns = []
    for scenario in scenarios:
        all_returns.append(scenario.total_return)
        all_drawdowns.append(scenario.max_drawdown)
    
    expected_return = sum(all_returns) / len(all_returns) if all_returns else 0
    expected_risk = math.sqrt(sum((r - expected_return)**2 for r in all_returns) / len(all_returns)) if all_returns else 0
    
    mean_ret = sum(all_returns) / len(all_returns) if all_returns else 0
    std_ret = math.sqrt(sum((r - mean_ret)**2 for r in all_returns) / len(all_returns)) if all_returns else 0
    sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
    
    all_returns.sort()
    cvar_idx = max(1, int(len(all_returns) * 0.05))
    cvar_5pct = sum(all_returns[:cvar_idx]) / cvar_idx if all_returns else 0
    
    total_turnover = sum(abs(steps[i].delta_weight) for i in range(len(steps)))
    
    return Policy(
        steps=steps,
        expected_return=expected_return,
        expected_risk=expected_risk,
        sharpe=sharpe,
        cvaR_5pct=cvar_5pct,
        turnover=total_turnover,
    )


def policy_to_sequence(policy: Policy, ticker: str, as_of: str, current_weight: float) -> dict:
    """Convert policy to API response format."""
    return {
        "ticker": ticker,
        "as_of": as_of,
        "current_weight": current_weight,
        "optimal_weight": policy.steps[0].weight if policy.steps else current_weight,
        "confidence": policy.steps[0].confidence if policy.steps else 0,
        "sequence": [
            {
                "horizon_days": step.day,
                "target_weight": step.weight,
                "action": step.action,
                "delta_weight": step.delta_weight,
                "confidence": step.confidence,
            }
            for step in policy.steps
        ],
        "metrics": {
            "expected_return": policy.expected_return,
            "expected_risk": policy.expected_risk,
            "sharpe": policy.sharpe,
            "cvar_5pct": policy.cvaR_5pct,
            "turnover": policy.turnover,
        },
    }
