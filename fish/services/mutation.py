"""Strategy Mutation — AlphaGen/RD-Agent Inspired.

Automated strategy discovery through genetic programming.

The idea:
1. Start with base strategies (genes)
2. Mutate them (combine, parameterize, evolve)
3. Test each mutation
4. Keep the best, discard the rest
5. Repeat

This is the automated strategy factory that generates new avatars.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from fish.services.baselines import StrategyResult, _closes, _build_result


@dataclass
class StrategyGene:
    """A single gene in a strategy."""
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    fitness: float = 0.0
    generation: int = 0


@dataclass
class MutationResult:
    """Result of a strategy mutation."""
    parent_genes: list[str]
    child_gene: StrategyGene
    fitness: float
    generation: int


def _mutate_params(params: dict, param_ranges: dict) -> dict:
    """Mutate parameters within their ranges."""
    mutated = params.copy()
    
    for key, (min_val, max_val) in param_ranges.items():
        if random.random() < 0.3:  # 30% chance to mutate each param
            if isinstance(min_val, int):
                mutated[key] = random.randint(min_val, max_val)
            else:
                mutated[key] = random.uniform(min_val, max_val)
    
    return mutated


def _crossover(gene1: StrategyGene, gene2: StrategyGene) -> StrategyGene:
    """Combine two genes to create a child."""
    child_params = {}
    
    for key in set(list(gene1.params.keys()) + list(gene2.params.keys())):
        if random.random() < 0.5:
            child_params[key] = gene1.params.get(key, gene2.params.get(key))
        else:
            child_params[key] = gene2.params.get(key, gene1.params.get(key))
    
    return StrategyGene(
        name=f"{gene1.name}_x_{gene2.name}",
        params=child_params,
    )


def _create_momentum_gene(lookback: int = 20, threshold: float = 0.02) -> StrategyGene:
    """Create a momentum strategy gene."""
    return StrategyGene(
        name="momentum",
        params={"lookback": lookback, "threshold": threshold},
    )


def _create_rsi_gene(period: int = 14, buy_th: float = 30, sell_th: float = 70) -> StrategyGene:
    """Create an RSI strategy gene."""
    return StrategyGene(
        name="rsi",
        params={"period": period, "buy_th": buy_th, "sell_th": sell_th},
    )


def _create_ma_gene(fast: int = 20, slow: int = 100) -> StrategyGene:
    """Create a moving average crossover gene."""
    return StrategyGene(
        name="ma_crossover",
        params={"fast": fast, "slow": slow},
    )


def _create_vol_gene(lookback: int = 20, target_vol: float = 0.15) -> StrategyGene:
    """Create a volatility gene."""
    return StrategyGene(
        name="vol_target",
        params={"lookback": lookback, "target_vol": target_vol},
    )


def _evaluate_gene(gene: StrategyGene, prices: list[dict]) -> float:
    """Evaluate a gene's fitness."""
    closes = _closes(prices)
    if len(closes) < 50:
        return 0.0
    
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    
    # Simple fitness: Sharpe ratio
    mean_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - mean_ret)**2 for r in returns) / len(returns))
    sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0
    
    # Penalize extreme strategies
    if abs(sharpe) > 5:
        sharpe = 5 * (1 if sharpe > 0 else -1)
    
    return sharpe


class StrategyMutator:
    """Strategy mutation engine."""
    
    def __init__(self, base_genes: list[StrategyGene] = None):
        if base_genes is None:
            base_genes = [
                _create_momentum_gene(),
                _create_rsi_gene(),
                _create_ma_gene(),
                _create_vol_gene(),
            ]
        self.genes = base_genes
        self.generation = 0
        self.history: list[MutationResult] = []
    
    def mutate(self, n_children: int = 10) -> list[MutationResult]:
        """Create new children through mutation."""
        children = []
        
        for _ in range(n_children):
            # Select parent(s)
            if len(self.genes) >= 2 and random.random() < 0.5:
                # Crossover
                parent1, parent2 = random.sample(self.genes, 2)
                child = _crossover(parent1, parent2)
                parent_names = [parent1.name, parent2.name]
            else:
                # Mutation
                parent = random.choice(self.genes)
                child = StrategyGene(
                    name=f"{parent.name}_mut",
                    params=parent.params.copy(),
                )
                parent_names = [parent.name]
            
            # Mutate parameters
            param_ranges = {
                "lookback": (5, 252),
                "threshold": (0.01, 0.1),
                "period": (5, 50),
                "buy_th": (20, 40),
                "sell_th": (60, 80),
                "fast": (5, 50),
                "slow": (50, 200),
                "target_vol": (0.05, 0.30),
            }
            child.params = _mutate_params(child.params, param_ranges)
            child.generation = self.generation + 1
            
            children.append(MutationResult(
                parent_genes=parent_names,
                child_gene=child,
                fitness=0.0,
                generation=self.generation + 1,
            ))
        
        return children
    
    def evaluate(self, mutations: list[MutationResult], prices: list[dict]) -> list[MutationResult]:
        """Evaluate mutations and update fitness."""
        for mutation in mutations:
            mutation.fitness = _evaluate_gene(mutation.child_gene, prices)
            mutation.child_gene.fitness = mutation.fitness
        
        return mutations
    
    def select(self, mutations: list[MutationResult], keep_ratio: float = 0.5) -> list[StrategyGene]:
        """Select the best mutations to survive."""
        # Sort by fitness
        mutations.sort(key=lambda m: m.fitness, reverse=True)
        
        # Keep top ratio
        n_keep = max(1, int(len(mutations) * keep_ratio))
        survivors = mutations[:n_keep]
        
        # Add to gene pool
        for s in survivors:
            self.genes.append(s.child_gene)
        
        # Update generation
        self.generation += 1
        
        return [s.child_gene for s in survivors]
    
    def get_best(self, n: int = 5) -> list[StrategyGene]:
        """Get the best genes overall."""
        sorted_genes = sorted(self.genes, key=lambda g: g.fitness, reverse=True)
        return sorted_genes[:n]


def run_mutation_evolution(
    prices: list[dict],
    n_generations: int = 5,
    n_children: int = 10,
    keep_ratio: float = 0.5,
) -> list[StrategyGene]:
    """Run full mutation evolution."""
    mutator = StrategyMutator()
    
    for gen in range(n_generations):
        # Mutate
        mutations = mutator.mutate(n_children)
        
        # Evaluate
        mutations = mutator.evaluate(mutations, prices)
        
        # Select
        survivors = mutator.select(mutations, keep_ratio)
        
        # Print progress
        best = mutator.get_best(1)[0]
        print(f"Generation {gen+1}: Best fitness = {best.fitness:.3f}")
    
    return mutator.get_best(10)
