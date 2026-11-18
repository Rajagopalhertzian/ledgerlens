"""Gate: Compare latest results with baseline for regression detection."""

import argparse
import json
from pathlib import Path

from .harness import compare_baseline


def main():
    parser = argparse.ArgumentParser(description="Compare results with baseline (make gate)")
    parser.add_argument("--results", type=Path, default=Path("evals/results"), help="Results directory")
    parser.add_argument("--baseline", type=Path, default=Path("evals/baseline.json"), help="Baseline file")
    parser.add_argument("--tolerance", type=float, default=0.01, help="Relative tolerance")

    args = parser.parse_args()

    # Find latest results
    result_files = list(args.results.glob("*_results.json"))
    if not result_files:
        return 1

    latest = max(result_files, key=lambda f: f.stat().st_mtime)

    with open(latest) as f:
        current = json.load(f)

    report = compare_baseline(current, args.baseline, args.tolerance)

    if report["regressions"]:
        for _r in report["regressions"]:
            pass

    if report["improvements"]:
        for _r in report["improvements"]:
            pass

    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
