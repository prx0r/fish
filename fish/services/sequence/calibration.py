"""Calibration Engine — Conformal prediction + recalibration.

Track: did 80% intervals actually contain reality 80% of the time?
If not, recalibrate downward automatically.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CalibrationMetrics:
    """Calibration metrics for prediction intervals."""
    coverage_50: float  # Actual coverage of 50% intervals
    coverage_80: float  # Actual coverage of 80% intervals
    coverage_95: float  # Actual coverage of 95% intervals
    expected_calibration_error: float
    interval_width_avg: float
    recalibration_factor: float


def compute_calibration(
    predictions: list[float],
    actuals: list[float],
    quantiles: list[float] = None,
) -> CalibrationMetrics:
    """Compute calibration metrics for prediction intervals.
    
    Args:
        predictions: Predicted medians
        actuals: Actual values
        quantiles: Confidence levels to check (default: [0.5, 0.8, 0.95])
    """
    if quantiles is None:
        quantiles = [0.5, 0.8, 0.95]
    
    if len(predictions) < 10:
        return CalibrationMetrics(
            coverage_50=0, coverage_80=0, coverage_95=0,
            expected_calibration_error=1.0,
            interval_width_avg=0, recalibration_factor=1.0,
        )
    
    # Compute residuals
    residuals = [actuals[i] - predictions[i] for i in range(len(predictions))]
    
    # For each quantile, compute actual coverage
    # Using empirical quantiles of residuals
    abs_residuals = [abs(r) for r in residuals]
    abs_residuals.sort()
    
    n = len(abs_residuals)
    
    # Coverage at each quantile
    coverage = {}
    for q in quantiles:
        # Width needed for q% coverage
        idx = int(n * q)
        if idx >= n:
            idx = n - 1
        width = abs_residuals[idx]
        
        # Actual coverage with this width
        covered = sum(1 for r in residuals if abs(r) <= width)
        coverage[q] = covered / n
    
    # Expected calibration error
    ece = sum(abs(coverage.get(q, 0) - q) for q in quantiles) / len(quantiles)
    
    # Average interval width
    avg_width = sum(abs_residuals) / len(abs_residuals) if abs_residuals else 0
    
    # Recalibration factor
    # If coverage is too low, increase intervals
    target_coverage = 0.8
    actual_coverage = coverage.get(0.8, 0.5)
    
    if actual_coverage < target_coverage:
        # Need wider intervals
        recalibration_factor = target_coverage / max(actual_coverage, 0.1)
    else:
        # Intervals are too wide
        recalibration_factor = target_coverage / actual_coverage
    
    # Clamp to reasonable range
    recalibration_factor = max(0.5, min(2.0, recalibration_factor))
    
    return CalibrationMetrics(
        coverage_50=coverage.get(0.5, 0),
        coverage_80=coverage.get(0.8, 0),
        coverage_95=coverage.get(0.95, 0),
        expected_calibration_error=ece,
        interval_width_avg=avg_width,
        recalibration_factor=recalibration_factor,
    )


def recalibrate_intervals(
    lower: float,
    upper: float,
    recalibration_factor: float,
) -> tuple[float, float]:
    """Recalibrate prediction intervals."""
    mid = (lower + upper) / 2
    half_width = (upper - lower) / 2
    
    new_half_width = half_width * recalibration_factor
    
    return mid - new_half_width, mid + new_half_width


def compute_confidence_from_calibration(
    calibration: CalibrationMetrics,
    model_agreement: float = 0.8,
    in_distribution: float = 0.9,
) -> float:
    """Compute overall confidence from calibration metrics."""
    # Calibration score (higher coverage = better)
    cal_score = (calibration.coverage_80 + calibration.coverage_50) / 2
    
    # ECE penalty (lower ECE = better)
    ece_penalty = calibration.expected_calibration_error
    
    # Recalibration factor (closer to 1 = better)
    recali_penalty = abs(calibration.recalibration_factor - 1.0)
    
    # Overall confidence
    confidence = (
        0.4 * cal_score +
        0.3 * model_agreement +
        0.2 * in_distribution +
        0.1 * (1 - ece_penalty) -
        0.1 * recali_penalty
    )
    
    return max(0.0, min(1.0, confidence))
