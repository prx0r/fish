"""Experiment Ledger — immutable record of every strategy mutation.

Every strategy attempt is recorded. Never delete experiments.
This is the scientific governance of the search process.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any

from sqlalchemy import Column, String, Float, Integer, Text, DateTime, JSON
from sqlalchemy.orm import Session

from fish.db import Base


class ExperimentRecord(Base):
    """Immutable experiment record in the database."""
    __tablename__ = "experiments"
    
    experiment_id = Column(String, primary_key=True)
    parent_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # What was tested
    hypothesis = Column(Text, nullable=False)
    ticker = Column(String, nullable=False)
    strategy_name = Column(String, nullable=False)
    parameters = Column(JSON, default=dict)
    features = Column(JSON, default=list)
    
    # When was it tested
    training_start = Column(String)
    training_end = Column(String)
    validation_start = Column(String)
    validation_end = Column(String)
    
    # Results
    sharpe = Column(Float, default=0)
    sortino = Column(Float, default=0)
    calmar = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    total_return = Column(Float, default=0)
    win_rate = Column(Float, default=0)
    trades_count = Column(Integer, default=0)
    turnover = Column(Float, default=0)
    
    # Judge metrics
    psr = Column(Float, default=0)
    dsr = Column(Float, default=0)
    pbo = Column(Float, default=0)
    bootstrap_ci_lower = Column(Float, default=-1)
    bootstrap_ci_upper = Column(Float, default=1)
    permutation_p = Column(Float, default=1)
    cost_sensitivity = Column(Float, default=0)
    regime_stability = Column(Float, default=0)
    
    # Verdict
    verdict = Column(String, default="PENDING")  # PASS, WARN, FAIL, PENDING
    score = Column(Integer, default=0)
    reasons = Column(JSON, default=list)
    
    # Metadata
    n_trials_at_time = Column(Integer, default=0)
    notes = Column(Text, default="")
    tags = Column(JSON, default=list)


@dataclass
class Experiment:
    """In-memory experiment representation."""
    experiment_id: str
    parent_id: str | None
    created_at: datetime
    hypothesis: str
    ticker: str
    strategy_name: str
    parameters: dict
    features: list[str]
    training_start: str
    training_end: str
    validation_start: str
    validation_end: str
    sharpe: float = 0
    sortino: float = 0
    calmar: float = 0
    max_drawdown: float = 0
    total_return: float = 0
    win_rate: float = 0
    trades_count: int = 0
    turnover: float = 0
    psr: float = 0
    dsr: float = 0
    pbo: float = 0
    bootstrap_ci_lower: float = -1
    bootstrap_ci_upper: float = 1
    permutation_p: float = 1
    cost_sensitivity: float = 0
    regime_stability: float = 0
    verdict: str = "PENDING"
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    n_trials_at_time: int = 0
    notes: str = ""
    tags: list[str] = field(default_factory=list)


class ExperimentLedger:
    """Immutable experiment ledger. Never deletes, only appends."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def record_experiment(
        self,
        hypothesis: str,
        ticker: str,
        strategy_name: str,
        parameters: dict = None,
        features: list[str] = None,
        parent_id: str = None,
        training_start: str = "",
        training_end: str = "",
        validation_start: str = "",
        validation_end: str = "",
        tags: list[str] = None,
        notes: str = "",
    ) -> Experiment:
        """Record a new experiment. Returns the experiment with generated ID."""
        experiment_id = f"exp-{uuid.uuid4().hex[:12]}"
        
        exp = ExperimentRecord(
            experiment_id=experiment_id,
            parent_id=parent_id,
            hypothesis=hypothesis,
            ticker=ticker,
            strategy_name=strategy_name,
            parameters=parameters or {},
            features=features or [],
            training_start=training_start,
            training_end=training_end,
            validation_start=validation_start,
            validation_end=validation_end,
            n_trials_at_time=self.session.query(ExperimentRecord).count(),
            notes=notes,
            tags=tags or [],
        )
        
        self.session.add(exp)
        self.session.commit()
        
        return self._to_experiment(exp)
    
    def record_result(
        self,
        experiment_id: str,
        sharpe: float,
        sortino: float,
        calmar: float,
        max_drawdown: float,
        total_return: float,
        win_rate: float,
        trades_count: int,
        turnover: float,
        psr: float = 0,
        dsr: float = 0,
        pbo: float = 0,
        bootstrap_ci_lower: float = -1,
        bootstrap_ci_upper: float = 1,
        permutation_p: float = 1,
        cost_sensitivity: float = 0,
        regime_stability: float = 0,
        verdict: str = "PENDING",
        score: int = 0,
        reasons: list[str] = None,
    ) -> Experiment:
        """Record results for an experiment."""
        exp = self.session.query(ExperimentRecord).filter_by(experiment_id=experiment_id).first()
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Update fields
        exp.sharpe = sharpe
        exp.sortino = sortino
        exp.calmar = calmar
        exp.max_drawdown = max_drawdown
        exp.total_return = total_return
        exp.win_rate = win_rate
        exp.trades_count = trades_count
        exp.turnover = turnover
        exp.psr = psr
        exp.dsr = dsr
        exp.pbo = pbo
        exp.bootstrap_ci_lower = bootstrap_ci_lower
        exp.bootstrap_ci_upper = bootstrap_ci_upper
        exp.permutation_p = permutation_p
        exp.cost_sensitivity = cost_sensitivity
        exp.regime_stability = regime_stability
        exp.verdict = verdict
        exp.score = score
        exp.reasons = reasons or []
        
        self.session.commit()
        return self._to_experiment(exp)
    
    def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Get experiment by ID."""
        exp = self.session.query(ExperimentRecord).filter_by(experiment_id=experiment_id).first()
        return self._to_experiment(exp) if exp else None
    
    def get_all_experiments(self, ticker: str = None, verdict: str = None, limit: int = 100) -> list[Experiment]:
        """Get all experiments with optional filters."""
        query = self.session.query(ExperimentRecord)
        if ticker:
            query = query.filter_by(ticker=ticker)
        if verdict:
            query = query.filter_by(verdict=verdict)
        query = query.order_by(ExperimentRecord.created_at.desc()).limit(limit)
        return [self._to_experiment(e) for e in query.all()]
    
    def get_experiment_count(self) -> int:
        """Get total number of experiments."""
        return self.session.query(ExperimentRecord).count()
    
    def get_pass_rate(self, ticker: str = None) -> float:
        """Get pass rate across all experiments."""
        query = self.session.query(ExperimentRecord)
        if ticker:
            query = query.filter_by(ticker=ticker)
        total = query.count()
        if total == 0:
            return 0.0
        passed = query.filter_by(verdict="PASS").count()
        return passed / total
    
    def get_best_strategies(self, ticker: str = None, top_n: int = 10) -> list[Experiment]:
        """Get top N strategies by score."""
        query = self.session.query(ExperimentRecord).filter(ExperimentRecord.verdict != "PENDING")
        if ticker:
            query = query.filter_by(ticker=ticker)
        query = query.order_by(ExperimentRecord.score.desc()).limit(top_n)
        return [self._to_experiment(e) for e in query.all()]
    
    def get_strategy_lineage(self, experiment_id: str) -> list[Experiment]:
        """Get the full lineage of an experiment (parent chain)."""
        lineage = []
        current_id = experiment_id
        while current_id:
            exp = self.get_experiment(current_id)
            if not exp:
                break
            lineage.append(exp)
            current_id = exp.parent_id
        return list(reversed(lineage))
    
    def get_statistics(self) -> dict:
        """Get aggregate statistics."""
        total = self.session.query(ExperimentRecord).count()
        passed = self.session.query(ExperimentRecord).filter_by(verdict="PASS").count()
        warned = self.session.query(ExperimentRecord).filter_by(verdict="WARN").count()
        failed = self.session.query(ExperimentRecord).filter_by(verdict="FAIL").count()
        
        # Average metrics
        from sqlalchemy import func
        avg_sharpe = self.session.query(func.avg(ExperimentRecord.sharpe)).scalar() or 0
        avg_dsr = self.session.query(func.avg(ExperimentRecord.dsr)).scalar() or 0
        avg_pbo = self.session.query(func.avg(ExperimentRecord.pbo)).scalar() or 0
        
        return {
            "total_experiments": total,
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_sharpe": round(avg_sharpe, 3),
            "avg_dsr": round(avg_dsr, 3),
            "avg_pbo": round(avg_pbo, 3),
        }
    
    def _to_experiment(self, record: ExperimentRecord) -> Experiment:
        """Convert database record to Experiment dataclass."""
        return Experiment(
            experiment_id=record.experiment_id,
            parent_id=record.parent_id,
            created_at=record.created_at,
            hypothesis=record.hypothesis,
            ticker=record.ticker,
            strategy_name=record.strategy_name,
            parameters=record.parameters or {},
            features=record.features or [],
            training_start=record.training_start or "",
            training_end=record.training_end or "",
            validation_start=record.validation_start or "",
            validation_end=record.validation_end or "",
            sharpe=record.sharpe,
            sortino=record.sortino,
            calmar=record.calmar,
            max_drawdown=record.max_drawdown,
            total_return=record.total_return,
            win_rate=record.win_rate,
            trades_count=record.trades_count,
            turnover=record.turnover,
            psr=record.psr,
            dsr=record.dsr,
            pbo=record.pbo,
            bootstrap_ci_lower=record.bootstrap_ci_lower,
            bootstrap_ci_upper=record.bootstrap_ci_upper,
            permutation_p=record.permutation_p,
            cost_sensitivity=record.cost_sensitivity,
            regime_stability=record.regime_stability,
            verdict=record.verdict,
            score=record.score,
            reasons=record.reasons or [],
            n_trials_at_time=record.n_trials_at_time,
            notes=record.notes or "",
            tags=record.tags or [],
        )
