"""Agent evaluation (B0-B3) - Stub for M4."""

import argparse
from pathlib import Path


def run_agent(
    ground_truth_dir: Path,
    output_dir: Path,
    baselines: list[str] | None = None,
) -> dict:
    """Run agent evaluation (stub for M4)."""
    return {"status": "not_implemented"}


def main():
    parser = argparse.ArgumentParser(description="Run agent evaluation (M4)")
    parser.add_argument("--ground-truth", type=Path, default=Path("data/ground_truth"))
    parser.add_argument("--output", type=Path, default=Path("evals/results"))
    parser.add_argument("--baselines", nargs="+", default=["B0", "B1", "B2", "B3"])

    args = parser.parse_args()
    run_agent(args.ground_truth, args.output, args.baselines)


if __name__ == "__main__":
    main()
