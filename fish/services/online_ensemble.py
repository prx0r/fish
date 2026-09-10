"""Online Learning Ensemble — Adaptive Strategy Weighting.

You have exactly the classic expert-advice problem:
At every time step, several experts give predictions. Which expert should receive weight?

That is almost literally what online-learning theory was built for.

Candidate algorithms:
- Exponentially Weighted Average
- Hedge algorithm
- Online gradient descent
- Bayesian model averaging
- Thompson sampling
- Contextual bandits

The ensemble objective:
Utility = E[R] - λσ - γDD - ηTurnover - κCosts - ρCorrelationWithExisting
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class ExpertWeight:
    """Weight for a single expert/strategy."""
    name: str
    weight: float = 1.0
    cumulative_reward: float = 0.0
    predictions: int = 0
    correct: int = 0


@dataclass
class OnlineEnsemble:
    """Online learning ensemble that adapts weights over time."""
    experts: dict[str, ExpertWeight] = field(default_factory=dict)
    learning_rate: float = 0.1
    discount_factor: float = 0.95
    algorithm: str = "ewa"  # ewa, hedge, thompson
    
    def update(self, expert_name: str, reward: float) -> None:
        """Update expert weight based on reward."""
        if expert_name not in self.experts:
            self.experts[expert_name] = ExpertWeight(name=expert_name)
        
        expert = self.experts[expert_name]
        expert.predictions += 1
        expert.cumulative_reward += reward
        
        if reward > 0:
            expert.correct += 1
        
        # Update weight based on algorithm
        if self.algorithm == "ewa":
            # Exponentially Weighted Average
            expert.weight *= math.exp(self.learning_rate * reward)
        elif self.algorithm == "hedge":
            # Hedge algorithm
            expert.weight *= (1 + self.learning_rate * reward)
        elif self.algorithm == "thompson":
            # Thompson sampling (simplified)
            # Use beta distribution approximation
            alpha = expert.correct + 1
            beta = expert.predictions - expert.correct + 1
            # Sample from beta distribution
            expert.weight = random.betavariate(alpha, beta)
        
        # Normalize weights
        self._normalize()
    
    def _normalize(self) -> None:
        """Normalize weights to sum to 1."""
        total = sum(e.weight for e in self.experts.values())
        if total > 0:
            for expert in self.experts.values():
                expert.weight /= total
    
    def get_weights(self) -> dict[str, float]:
        """Get current weights for all experts."""
        return {name: expert.weight for name, expert in self.experts.items()}
    
    def get_top_experts(self, n: int = 5) -> list[ExpertWeight]:
        """Get top N experts by weight."""
        sorted_experts = sorted(self.experts.values(), key=lambda e: e.weight, reverse=True)
        return sorted_experts[:n]
    
    def get_confidence(self) -> float:
        """Get ensemble confidence (0-1)."""
        if not self.experts:
            return 0.0
        
        weights = [e.weight for e in self.experts.values()]
        max_weight = max(weights)
        
        # Confidence = how concentrated the weights are
        return max_weight
    
    def get_regret(self) -> float:
        """Get cumulative regret (how much we've lost by not picking the best expert)."""
        if not self.experts:
            return 0.0
        
        best_expert = max(self.experts.values(), key=lambda e: e.cumulative_reward)
        our_reward = sum(e.cumulative_reward * e.weight for e in self.experts.values())
        
        return best_expert.cumulative_reward - our_reward


def create_portfolio_ensemble(
    strategies: list[str],
    algorithm: str = "ewa",
    learning_rate: float = 0.1,
) -> OnlineEnsemble:
    """Create an ensemble for portfolio strategies."""
    ensemble = OnlineEnsemble(algorithm=algorithm, learning_rate=learning_rate)
    
    for strategy in strategies:
        ensemble.experts[strategy] = ExpertWeight(name=strategy)
    
    return ensemble


def backtest_ensemble(
    prices: list[dict],
    strategies: dict[str, callable],
    ticker: str,
    algorithm: str = "ewa",
    lookback: int = 20,
) -> dict:
    """Backtest the online learning ensemble."""
    from fish.services.baselines import _closes
    
    closes = _closes(prices)
    if len(closes) < lookback + 10:
        return {"error": "Not enough data"}
    
    # Create ensemble
    ensemble = create_portfolio_ensemble(
        list(strategies.keys()),
        algorithm=algorithm,
    )
    
    # Track performance
    portfolio_returns = []
    strategy_returns = {name: [] for name in strategies}
    
    for i in range(lookback, len(closes) - 1):
        # Get current weights
        weights = ensemble.get_weights()
        
        # Calculate each strategy's return
        day_return = (closes[i + 1] - closes[i]) / closes[i]
        
        for name, fn in strategies.items():
            # Simplified: use buy-and-hold return for each strategy
            # In reality, would run each strategy's logic
            strategy_returns[name].append(day_return)
        
        # Update ensemble based on recent performance
        for name, fn in strategies.items():
            # Calculate strategy's recent return
            recent_returns = [(closes[j] - closes[j-1]) / closes[j-1] 
                            for j in range(max(1, i-lookback), i+1)]
            strategy_return = sum(recent_returns)
            
            # Reward = strategy return (simplified)
            reward = strategy_return
            ensemble.update(name, reward)
        
        # Calculate portfolio return
        portfolio_return = sum(weights.get(name, 0) * day_return 
                              for name in strategies)
        portfolio_returns.append(portfolio_return)
    
    # Calculate metrics
    if portfolio_returns:
        avg_return = sum(portfolio_returns) / len(portfolio_returns)
        std_return = math.sqrt(sum((r - avg_return)**2 for r in portfolio_returns) / len(portfolio_returns))
        sharpe = (avg_return / std_return) * math.sqrt(252) if std_return > 0 else 0
        
        # Buy and hold comparison
        bh_return = (closes[-1] - closes[lookback]) / closes[lookback]
        
        return {
            "ticker": ticker,
            "algorithm": algorithm,
            "ensemble_sharpe": sharpe,
            "ensemble_return": avg_return * 252,
            "buy_hold_return": bh_return,
            "regret": ensemble.get_regret(),
            "confidence": ensemble.get_confidence(),
            "final_weights": ensemble.get_weights(),
            "top_experts": [e.name for e in ensemble.get_top_experts(3)],
        }
    
    return {"error": "No returns calculated"}
