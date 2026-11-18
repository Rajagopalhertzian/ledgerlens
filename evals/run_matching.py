"""Matching evaluation - Stub for M3."""

import argparse
from pathlib import Path


def run_matching(
    ground_truth_dir: Path,
    extraction_results_dir: Path,
    output_dir: Path,
) -> dict:
    """Run matching evaluation (stub for M3)."""
    return {"status": "not_implemented"}


def main():
    parser = argparse.ArgumentParser(description="Run matching evaluation (M3)")
    parser.add_argument("--ground-truth", type=Path, default=Path("data/ground_truth"))
    parser.add_argument("--extraction-results", type=Path, default=Path("evals/results"))
    parser.add_argument("--output", type=Path, default=Path("evals/results"))

    args = parser.parse_args()
    run_matching(args.ground_truth, args.extraction_results, args.output)


if __name__ == "__main__":
    main()
