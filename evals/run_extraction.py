"""Extraction evaluation (E0-E4) - Stub for M2."""

import argparse
from pathlib import Path


def run_extraction(
    ground_truth_dir: Path,
    output_dir: Path,
    configs: list[str] | None = None,
) -> dict:
    """Run extraction evaluation (stub for M2)."""
    return {
        "status": "not_implemented",
        "message": "Run after M2 extraction module is complete",
    }


def main():
    parser = argparse.ArgumentParser(description="Run extraction evaluation (M2)")
    parser.add_argument("--ground-truth", type=Path, default=Path("data/ground_truth"))
    parser.add_argument("--output", type=Path, default=Path("evals/results"))
    parser.add_argument("--configs", nargs="+", default=["E0", "E1", "E2", "E3", "E4"])

    args = parser.parse_args()
    run_extraction(args.ground_truth, args.output, args.configs)


if __name__ == "__main__":
    main()
