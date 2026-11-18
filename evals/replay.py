"""Replay: Re-run invoice from cached responses - Stub for M7."""

import argparse
from pathlib import Path


def replay_invoice(
    invoice_id: str,
    cache_dir: Path,
    output_dir: Path,
) -> dict:
    """Replay invoice evaluation (stub for M7)."""
    return {"status": "not_implemented"}


def main():
    parser = argparse.ArgumentParser(description="Replay invoice from cached responses (M7)")
    parser.add_argument("--invoice", required=True, help="Invoice ID to replay")
    parser.add_argument("--cache", type=Path, default=Path("cache"), help="Cache directory")
    parser.add_argument("--output", type=Path, default=Path("evals/results"), help="Output directory")

    args = parser.parse_args()
    replay_invoice(args.invoice, args.cache, args.output)


if __name__ == "__main__":
    main()
