"""Evaluation harness with metric functions.

All functions are unit-tested and designed for deterministic evaluation.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment


def normalize_number(s: str) -> float:
    """Normalize a number string to float.

    Handles:
    - Indian digit grouping: 12,34,567.00 -> 1234567.00
    - Currency symbols: ₹1,234.56, $1,234.56, INR 1,234.56
    - European format: 1.234,56 -> 1234.56
    - Parentheses for negatives: (1,234.56) -> -1234.56
    - Comma as decimal separator: 1234,56 -> 1234.56

    Args:
        s: Input string

    Returns:
        Normalized float value

    Raises:
        ValueError: If string cannot be parsed as number

    """
    if not s or not isinstance(s, str):
        raise ValueError(f"Cannot normalize empty or non-string: {s}")

    original = s.strip()

    # Handle parentheses for negative
    is_negative = False
    if original.startswith("(") and original.endswith(")"):
        is_negative = True
        original = original[1:-1].strip()

    # Remove currency symbols and common prefixes (longer prefixes first)
    for prefix in ["₹", "$", "€", "£", "INR ", "INR", "USD", "EUR", "Rs.", "Rs"]:
        if original.startswith(prefix):
            original = original[len(prefix):].strip()

    # Handle Lakh/Crore multipliers (with or without leading space)
    multiplier = 1.0
    for suffix, mult in [(" Cr", 1e7), (" Crore", 1e7), (" Lakh", 1e5), (" Lac", 1e5), ("Lakh", 1e5), ("Cr", 1e7)]:
        if original.endswith(suffix):
            multiplier = mult
            original = original[:-len(suffix)].strip()
            break

    # Remove other trailing currency indicators
    for suffix in [" INR", " USD", " EUR"]:
        if original.endswith(suffix):
            original = original[:-len(suffix)].strip()

    # Handle Indian numbering: 12,34,567.00 or 12,34,567
    # Check if it has Indian grouping (groups of 2 after first 3)
    parts = original.split(".")
    int_part = parts[0]

    # Count commas in integer part
    comma_count = int_part.count(",")

    if comma_count >= 2:
        # Likely Indian format: check if groups of 2 after first group
        groups = int_part.split(",")
        if len(groups[-1]) == 3 and all(len(g) == 2 for g in groups[:-1]):
            # Indian format: 12,34,567
            int_part = "".join(groups)
        elif len(groups[-1]) <= 3 and all(len(g) <= 3 for g in groups):
            # Standard format: 1,234,567
            int_part = "".join(groups)
        else:
            # Ambiguous - try both
            int_part = "".join(groups)
    elif comma_count == 1:
        # Single comma - could be thousands separator or decimal
        groups = int_part.split(",")
        if len(groups[1]) == 3:
            # Likely thousands separator: 1,234
            int_part = "".join(groups)
        else:
            # Likely decimal separator: 1,23 -> 1.23
            int_part = groups[0] + "." + groups[1]

    # Reconstruct
    normalized = int_part + "." + parts[1] if len(parts) > 1 else int_part

    # Handle European format: 1.234,56 -> replace last . with nothing, last , with .
    if "," in normalized and "." in normalized:
        last_comma = normalized.rfind(",")
        last_dot = normalized.rfind(".")
        if last_comma > last_dot:
            # Comma is decimal separator
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            # Dot is decimal separator, remove commas
            normalized = normalized.replace(",", "")

    try:
        result = float(normalized)
        result = result * multiplier
        return -result if is_negative else result
    except ValueError as err:
        raise ValueError(f"Cannot parse number from: {s}") from err


def normalize_date(s: str) -> date:
    """Normalize a date string to date object.

    Handles multiple formats:
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - MM/DD/YYYY, MM-DD-YYYY, MM.DD.YYYY
    - YYYY-MM-DD, YYYY/MM/DD
    - DD-MMM-YYYY, DD MMM YYYY
    - DD MMMM YYYY
    - ISO format with time: YYYY-MM-DDTHH:MM:SS

    Args:
        s: Input date string

    Returns:
        Normalized date object

    Raises:
        ValueError: If string cannot be parsed as date

    """
    if not s or not isinstance(s, str):
        raise ValueError(f"Cannot normalize empty or non-string: {s}")

    original = s.strip()

    # Try ISO format first (with or without time)
    iso_formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in iso_formats:
        try:
            return datetime.strptime(original, fmt).date()
        except ValueError:
            continue

    # List of formats to try (most specific first)
    formats = [
        # DD-MMM-YYYY
        "%d-%b-%Y", "%d-%B-%Y",
        # DD MMM YYYY
        "%d %b %Y", "%d %B %Y",
        # DD/MM/YYYY variants
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        # MM/DD/YYYY variants
        "%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y",
        # YYYY/MM/DD
        "%Y/%m/%d",
        # With 2-digit year
        "%d/%m/%y", "%d-%m-%y", "%m/%d/%y", "%m-%d-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(original, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Cannot parse date from: {s}")


def normalize_currency(s: str) -> Decimal:
    """Normalize a currency string to Decimal for precise arithmetic.

    Args:
        s: Input currency string

    Returns:
        Normalized Decimal value

    Raises:
        ValueError: If string cannot be parsed

    """
    num = normalize_number(s)
    return Decimal(str(num)).quantize(Decimal("0.01"))


def match_line_items(
    pred_lines: list[dict[str, Any]],
    gt_lines: list[dict[str, Any]],
    key_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Match predicted line items to ground truth using Hungarian algorithm.

    Args:
        pred_lines: List of predicted line item dicts
        gt_lines: List of ground truth line item dicts
        key_fields: Fields to use for matching (default: item_description, hsn_code, quantity, unit_price)

    Returns:
        Dict with matches, precision, recall, F1, and unmatched items

    """
    if key_fields is None:
        key_fields = ["item_description", "hsn_code", "quantity", "unit_price"]

    n_pred = len(pred_lines)
    n_gt = len(gt_lines)

    if n_pred == 0 and n_gt == 0:
        return {
            "matches": [],
            "unmatched_pred": [],
            "unmatched_gt": [],
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        }

    if n_pred == 0:
        return {
            "matches": [],
            "unmatched_pred": [],
            "unmatched_gt": list(range(n_gt)),
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    if n_gt == 0:
        return {
            "matches": [],
            "unmatched_pred": list(range(n_pred)),
            "unmatched_gt": [],
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    # Build cost matrix (negative similarity for minimization)
    cost_matrix = np.zeros((n_pred, n_gt))

    for i, pred in enumerate(pred_lines):
        for j, gt in enumerate(gt_lines):
            similarity = 0.0
            for field in key_fields:
                pred_val = str(pred.get(field, "")).lower().strip()
                gt_val = str(gt.get(field, "")).lower().strip()

                if not pred_val or not gt_val:
                    continue

                if field in ["quantity", "unit_price", "taxable_value", "tax_amount", "line_total"]:
                    # Numeric comparison
                    try:
                        pred_num = normalize_number(pred_val)
                        gt_num = normalize_number(gt_val)
                        if gt_num != 0:
                            diff = abs(pred_num - gt_num) / abs(gt_num)
                            similarity += max(0, 1 - diff)
                        else:
                            similarity += 1.0 if pred_num == 0 else 0.0
                    except ValueError:
                        # Fall back to string similarity
                        similarity += fuzz.ratio(pred_val, gt_val) / 100.0
                else:
                    # String comparison
                    similarity += fuzz.ratio(pred_val, gt_val) / 100.0

            # Average similarity across fields
            avg_similarity = similarity / len(key_fields) if key_fields else 0
            cost_matrix[i, j] = 1.0 - avg_similarity  # Cost = 1 - similarity

    # Hungarian algorithm
    pred_indices, gt_indices = linear_sum_assignment(cost_matrix)

    # Build matches
    matches = []
    matched_pred = set()
    matched_gt = set()

    for pi, gi in zip(pred_indices, gt_indices, strict=False):
        cost = cost_matrix[pi, gi]
        similarity = 1.0 - cost
        if similarity > 0.5:  # Threshold for considering a match
            matches.append({
                "pred_index": int(pi),
                "gt_index": int(gi),
                "similarity": float(similarity),
            })
            matched_pred.add(pi)
            matched_gt.add(gi)

    unmatched_pred = [i for i in range(n_pred) if i not in matched_pred]
    unmatched_gt = [j for j in range(n_gt) if j not in matched_gt]

    tp = len(matches)
    fp = len(unmatched_pred)
    fn = len(unmatched_gt)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "matches": matches,
        "unmatched_pred": unmatched_pred,
        "unmatched_gt": unmatched_gt,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def bootstrap_ci(
    data: list[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    statistic: str = "mean",
) -> tuple[float, float]:
    """Compute bootstrap confidence interval.

    Args:
        data: List of values
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level (e.g., 0.95 for 95% CI)
        statistic: Statistic to compute ('mean', 'median', 'std')

    Returns:
        Tuple of (lower_bound, upper_bound)

    """
    if not data:
        return (0.0, 0.0)

    data_arr = np.array(data)
    n = len(data_arr)
    stats: list[float] = []

    rng = np.random.default_rng(42)  # Fixed seed for reproducibility

    for _ in range(n_bootstrap):
        sample = rng.choice(data_arr, size=n, replace=True)
        if statistic == "mean":
            stats.append(float(np.mean(sample)))
        elif statistic == "median":
            stats.append(float(np.median(sample)))
        elif statistic == "std":
            stats.append(float(np.std(sample)))
        else:
            stats.append(float(np.mean(sample)))

    stats_arr = np.array(stats)
    alpha = (1 - confidence) / 2
    lower = np.percentile(stats_arr, alpha * 100)
    upper = np.percentile(stats_arr, (1 - alpha) * 100)

    return (float(lower), float(upper))


def expected_calibration_error(
    confidences: list[float],
    accuracies: list[float],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE).

    ECE measures the difference between predicted confidence and actual accuracy.

    Args:
        confidences: List of confidence scores [0, 1]
        accuracies: List of binary accuracies (0 or 1)
        n_bins: Number of bins for calibration

    Returns:
        ECE value (lower is better calibrated)

    """
    if len(confidences) != len(accuracies):
        raise ValueError("Confidences and accuracies must have same length")

    if not confidences:
        return 0.0

    confidences_arr = np.array(confidences)
    accuracies_arr = np.array(accuracies)

    # Bin boundaries
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    ece = 0.0

    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers, strict=False):
        # Find samples in this bin
        in_bin = (confidences_arr >= bin_lower) & (confidences_arr < bin_upper)
        if bin_upper == 1.0:
            in_bin = (confidences_arr >= bin_lower) & (confidences_arr <= bin_upper)

        prop_in_bin = in_bin.mean()

        if prop_in_bin > 0:
            accuracy_in_bin = float(accuracies_arr[in_bin].mean())
            avg_confidence_in_bin = float(confidences_arr[in_bin].mean())
            ece += prop_in_bin * abs(avg_confidence_in_bin - accuracy_in_bin)

    return float(ece)


def selective_prediction_curve(
    confidences: list[float],
    accuracies: list[float],
    n_points: int = 100,
) -> list[tuple[float, float]]:
    """Compute selective prediction curve (coverage vs precision).

    Args:
        confidences: List of confidence scores [0, 1]
        accuracies: List of binary accuracies (0 or 1)
        n_points: Number of points on the curve

    Returns:
        List of (coverage, precision) tuples

    """
    if len(confidences) != len(accuracies):
        raise ValueError("Confidences and accuracies must have same length")

    if not confidences:
        return []

    # Sort by confidence descending
    pairs = sorted(zip(confidences, accuracies, strict=False), key=lambda x: x[0], reverse=True)
    [p[0] for p in pairs]
    accuracies_sorted = [p[1] for p in pairs]

    curve = []
    total = len(pairs)

    for i in range(1, n_points + 1):
        k = max(1, int(total * i / n_points))
        coverage = k / total
        precision = sum(accuracies_sorted[:k]) / k
        curve.append((coverage, precision))

    return curve


def write_results(
    results: dict[str, Any],
    output_dir: Path,
    prefix: str = "eval",
) -> tuple[Path, Path]:
    """Write evaluation results to JSON and Markdown.

    Args:
        results: Results dictionary
        output_dir: Output directory
        prefix: Prefix for output files

    Returns:
        Tuple of (json_path, md_path)

    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Add timestamp
    results["timestamp"] = datetime.now().isoformat()

    # JSON output
    json_path = output_dir / f"{prefix}_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Markdown output
    md_path = output_dir / f"{prefix}_results.md"
    with open(md_path, "w") as f:
        f.write(f"# Evaluation Results: {prefix}\n\n")
        f.write(f"Generated: {results['timestamp']}\n\n")

        for key, value in results.items():
            if key == "timestamp":
                continue
            f.write(f"## {key.replace('_', ' ').title()}\n\n")
            if isinstance(value, (dict, list)):
                f.write("```json\n")
                f.write(json.dumps(value, indent=2, default=str))
                f.write("\n```\n\n")
            else:
                f.write(f"{value}\n\n")

    return json_path, md_path


def compare_baseline(
    current: dict[str, Any],
    baseline_path: Path,
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Compare current results with baseline for regression detection.

    Args:
        current: Current results dictionary
        baseline_path: Path to baseline JSON
        tolerance: Relative tolerance for numeric comparisons

    Returns:
        Comparison report with pass/fail status

    """
    if not baseline_path.exists():
        return {
            "status": "no_baseline",
            "message": f"Baseline not found at {baseline_path}",
            "regressions": [],
            "improvements": [],
        }

    with open(baseline_path) as f:
        baseline = json.load(f)

    regressions = []
    improvements = []

    def compare_values(path: str, curr: Any, base: Any):
        if isinstance(curr, (int, float)) and isinstance(base, (int, float)):
            if base != 0:
                rel_diff = (curr - base) / abs(base)
            else:
                rel_diff = float('inf') if curr != 0 else 0.0

            if rel_diff < -tolerance:
                regressions.append({
                    "metric": path,
                    "baseline": base,
                    "current": curr,
                    "diff": curr - base,
                    "rel_diff": rel_diff,
                })
            elif rel_diff > tolerance:
                improvements.append({
                    "metric": path,
                    "baseline": base,
                    "current": curr,
                    "diff": curr - base,
                    "rel_diff": rel_diff,
                })
        elif isinstance(curr, dict) and isinstance(base, dict):
            all_keys = set(curr.keys()) | set(base.keys())
            for k in all_keys:
                compare_values(f"{path}.{k}", curr.get(k), base.get(k))
        elif isinstance(curr, list) and isinstance(base, list):
            for i, (c, b) in enumerate(zip(curr, base, strict=False)):
                compare_values(f"{path}[{i}]", c, b)

    compare_values("", current, baseline)

    status = "pass" if not regressions else "fail"

    return {
        "status": status,
        "regressions": regressions,
        "improvements": improvements,
        "tolerance": tolerance,
    }


# Convenience function for field-level accuracy
def field_accuracy(
    pred: dict[str, Any],
    gt: dict[str, Any],
    fields: list[str] | None = None,
) -> dict[str, float]:
    """Compute field-level accuracy between prediction and ground truth.

    Args:
        pred: Predicted fields
        gt: Ground truth fields
        fields: Specific fields to compare (default: all common fields)

    Returns:
        Dict of field -> accuracy (1.0 for match, 0.0 for mismatch)

    """
    if fields is None:
        fields = list(set(pred.keys()) & set(gt.keys()))

    accuracies = {}
    for field in fields:
        pred_val = pred.get(field)
        gt_val = gt.get(field)

        if pred_val is None and gt_val is None:
            accuracies[field] = 1.0
        elif pred_val is None or gt_val is None:
            accuracies[field] = 0.0
        else:
            # Try numeric comparison first
            try:
                pred_num = normalize_number(str(pred_val))
                gt_num = normalize_number(str(gt_val))
                accuracies[field] = 1.0 if abs(pred_num - gt_num) < 0.01 else 0.0
            except ValueError:
                # String comparison
                pred_str = str(pred_val).strip().lower()
                gt_str = str(gt_val).strip().lower()
                accuracies[field] = 1.0 if pred_str == gt_str else 0.0

    return accuracies
