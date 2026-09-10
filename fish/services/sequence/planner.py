"""MPC Planner — Receding-horizon stochastic control.

The main loop:
1. Observe world state
2. Generate scenarios
3. Optimize policy
4. Return sequence with confidence decay
5. Execute first action
6. Reobserve and replan
"""
from __future__ import annotations

from dataclasses import dataclass

from fish.services.sequence.state import WorldState, compute_world_state
from fish.services.sequence.scenarios import (
    block_bootstrap,
    regime_conditioned_bootstrap,
    compute_scenario_statistics,
)
from fish.services.sequence.optimizer import (
    optimize_policy,
    policy_to_sequence,
    Policy,
)


@dataclass
class MPCResult:
    """Result of MPC planning."""
    ticker: str
    as_of: str
    current_weight: float
    optimal_weight: float
    confidence: float
    sequence: list[dict]
    distribution: dict
    policy: Policy
    scenario_stats: dict


class MPCPlanner:
    """Model Predictive Control planner for portfolio allocation."""
    
    def __init__(
        self,
        n_scenarios: int = 1000,
        horizon: int = 252,
        risk_aversion: float = 1.0,
        turnover_penalty: float = 0.001,
        cvaR_penalty: float = 0.5,
        method: str = "regime",
    ):
        self.n_scenarios = n_scenarios
        self.horizon = horizon
        self.risk_aversion = risk_aversion
        self.turnover_penalty = turnover_penalty
        self.cvaR_penalty = cvaR_penalty
        self.method = method
    
    def plan(
        self,
        prices: list[dict],
        ticker: str,
        current_weight: float,
        current_index: int = None,
        spy_prices: list[dict] = None,
    ) -> MPCResult:
        """Generate optimal allocation sequence."""
        if current_index is None:
            current_index = len(prices) - 1
        
        # 1. Compute current world state
        state = compute_world_state(prices, ticker, current_index, spy_prices)
        
        # 2. Generate scenarios
        if self.method == "regime":
            scenarios = regime_conditioned_bootstrap(
                prices, ticker,
                n_scenarios=self.n_scenarios,
                horizon=self.horizon,
                current_index=current_index,
            )
        else:
            scenarios = block_bootstrap(
                prices, ticker,
                n_scenarios=self.n_scenarios,
                horizon=self.horizon,
                current_index=current_index,
            )
        
        # 3. Compute scenario statistics
        scenario_stats = compute_scenario_statistics(scenarios)
        
        # 4. Optimize policy
        policy = optimize_policy(
            scenarios=scenarios,
            current_weight=current_weight,
            risk_aversion=self.risk_aversion,
            turnover_penalty=self.turnover_penalty,
            cvaR_penalty=self.cvaR_penalty,
        )
        
        # 5. Convert to sequence
        sequence = policy_to_sequence(policy, ticker, state.date, current_weight)
        
        return MPCResult(
            ticker=ticker,
            as_of=state.date,
            current_weight=current_weight,
            optimal_weight=policy.steps[0].weight if policy.steps else current_weight,
            confidence=policy.steps[0].confidence if policy.steps else 0,
            sequence=sequence["sequence"],
            distribution=scenario_stats,
            policy=policy,
            scenario_stats=scenario_stats,
        )
    
    def plan_all(
        self,
        all_prices: dict[str, list[dict]],
        positions: dict[str, float],
    ) -> dict[str, MPCResult]:
        """Plan for all positions in portfolio."""
        results = {}
        
        for ticker, weight in positions.items():
            prices = all_prices.get(ticker, [])
            if not prices or len(prices) < 100:
                continue
            
            results[ticker] = self.plan(prices, ticker, weight)
        
        return results
