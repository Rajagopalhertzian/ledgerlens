"""RAG evaluation - Stub for M5."""

import argparse
from pathlib import Path


def run_rag(
    questions_file: Path,
    output_dir: Path,
) -> dict:
    """Run RAG evaluation (stub for M5)."""
    return {"status": "not_implemented"}


def main():
    parser = argparse.ArgumentParser(description="Run RAG evaluation (M5)")
    parser.add_argument("--questions", type=Path, default=Path("evals/questions.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/results"))

    args = parser.parse_args()
    run_rag(args.questions, args.output)


if __name__ == "__main__":
    main()
