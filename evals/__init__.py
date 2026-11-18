"""LedgerLens Evaluation Harness.

Provides metric functions for evaluating extraction, matching, agent workflows,
and other components.
"""

from .harness import (
    bootstrap_ci,
    compare_baseline,
    expected_calibration_error,
    match_line_items,
    normalize_currency,
    normalize_date,
    normalize_number,
    selective_prediction_curve,
    write_results,
)

__all__ = [
    "bootstrap_ci",
    "compare_baseline",
    "expected_calibration_error",
    "match_line_items",
    "normalize_currency",
    "normalize_date",
    "normalize_number",
    "selective_prediction_curve",
    "write_results",
]

__version__ = "1.0.0"
