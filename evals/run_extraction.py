"""Extraction evaluation script (make eval-extraction).

Runs ablation configs E0-E4 on dev/test splits and computes metrics.
"""

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PIL import Image

from evals.harness import (
    bootstrap_ci,
    normalize_date,
    normalize_number,
    write_results,
)
from ledgerlens.extraction import (
    EXTRACTION_CONFIGS,
    ExtractionConfig,
    Extractor,
    FieldType,
)
from ledgerlens.extraction.calibration import (
    compute_field_ece,
)


def load_ground_truth(gt_dir: Path) -> dict[str, dict[FieldType, str]]:
    """Load ground truth JSON files."""
    gt_data = {}

    for gt_file in gt_dir.glob("*.json"):
        with open(gt_file) as f:
            data = json.load(f)

        invoice_number = data.get("invoice_number", gt_file.stem)
        gt_data[invoice_number] = {}

        # Header fields
        header = data.get("header", {})
        field_mapping = {
            FieldType.VENDOR_NAME: "vendor_name",
            FieldType.VENDOR_GSTIN: "vendor_gstin",
            FieldType.INVOICE_NUMBER: "invoice_number",
            FieldType.INVOICE_DATE: "invoice_date",
            FieldType.BUYER_GSTIN: "buyer_gstin",
            FieldType.BUYER_NAME: "buyer_name",
            FieldType.PO_REFERENCE: "po_reference",
            FieldType.GRN_REFERENCE: "grn_reference",
            FieldType.SUBTOTAL: "subtotal",
            FieldType.TOTAL_TAX: "total_tax",
            FieldType.GRAND_TOTAL: "grand_total",
            FieldType.CURRENCY: "currency",
            FieldType.PLACE_OF_SUPPLY: "place_of_supply",
            FieldType.PLACE_OF_DELIVERY: "place_of_delivery",
            FieldType.IRN: "irn",
            FieldType.EWAY_BILL_NUMBER: "eway_bill_number",
            FieldType.PAYMENT_TERMS: "payment_terms",
        }

        for field_type, key in field_mapping.items():
            if key in header:
                gt_data[invoice_number][field_type] = str(header[key])

        # Tax breakdown
        taxes = data.get("taxes", {})
        if taxes:
            tax_sum = taxes.get("cgst", 0) + taxes.get("sgst", 0) + taxes.get("igst", 0) + taxes.get("cess", 0)
            gt_data[invoice_number][FieldType.SUBTOTAL] = str(taxes.get("subtotal", tax_sum))
            gt_data[invoice_number][FieldType.TOTAL_TAX] = str(taxes.get("total_tax", tax_sum))
            gt_data[invoice_number][FieldType.GRAND_TOTAL] = str(taxes.get("grand_total", 0))

    return gt_data


def _create_dummy_image() -> Image.Image:
    """Create a simple dummy image for mock backends."""
    return Image.new("RGB", (100, 100), color="white")


def evaluate_config(
    config_name: str,
    invoice_paths: list[Path],
    ground_truth: dict[str, dict[FieldType, str]],
    use_mock: bool = True,
) -> dict[str, Any]:
    """Evaluate a single extraction config."""
    # Use mock backends for testing
    if use_mock:
        config = ExtractionConfig(
            name=config_name,
            ocr_backend="mock",
            vlm_backend="mock",
            text_parser_backend="mock",
        )
    else:
        config = EXTRACTION_CONFIGS[config_name]

    extractor = Extractor(config)

    results = []
    total_cost = 0.0
    total_time = 0.0

    for invoice_path in invoice_paths:
        try:
            # Use dummy image for mock backends since they don't process real images
            if use_mock:
                document: Image.Image | Path = _create_dummy_image()
            else:
                document = invoice_path
            result = extractor.extract(document)
            results.append(result)
            total_cost += result.cost_usd
            total_time += result.extraction_time_ms
        except Exception:
            continue

    # Compute metrics
    metrics = compute_metrics(results, ground_truth, config_name)

    metrics["total_documents"] = len(results)
    metrics["total_cost_usd"] = total_cost
    metrics["avg_cost_usd"] = total_cost / len(results) if results else 0
    metrics["avg_latency_ms"] = total_time / len(results) if results else 0
    metrics["p50_latency_ms"] = float(np.percentile([r.extraction_time_ms for r in results], 50)) if results else 0
    metrics["p95_latency_ms"] = float(np.percentile([r.extraction_time_ms for r in results], 95)) if results else 0

    return metrics


def compute_metrics(
    results: list,
    ground_truth: dict[str, dict[FieldType, str]],
    config_name: str,
) -> dict[str, Any]:
    """Compute evaluation metrics for extraction results."""
    # Field types to evaluate
    field_types = [
        FieldType.VENDOR_NAME,
        FieldType.VENDOR_GSTIN,
        FieldType.INVOICE_NUMBER,
        FieldType.INVOICE_DATE,
        FieldType.BUYER_GSTIN,
        FieldType.BUYER_NAME,
        FieldType.SUBTOTAL,
        FieldType.TOTAL_TAX,
        FieldType.GRAND_TOTAL,
        FieldType.PLACE_OF_SUPPLY,
        FieldType.PLACE_OF_DELIVERY,
    ]

    metrics = {
        "config": config_name,
        "field_metrics": {},
        "overall": {},
    }

    # Per-field metrics
    for field_type in field_types:
        field_metrics = evaluate_field(field_type, results, ground_truth)
        metrics["field_metrics"][field_type.value] = field_metrics

    # Overall metrics
    all_accuracies = []

    for field_type in field_types:
        fm = metrics["field_metrics"][field_type.value]
        if "accuracy" in fm:
            all_accuracies.append(fm["accuracy"])

    if all_accuracies:
        metrics["overall"]["mean_accuracy"] = float(np.mean(all_accuracies))
        metrics["overall"]["std_accuracy"] = float(np.std(all_accuracies))

    # ECE
    ece_values = []
    for field_type in field_types:
        gt_list = []
        for r in results:
            name = r.document_path.split("/")[-1].replace(".html", "").replace(".pdf", "")
            gt_list.append(ground_truth.get(name, {}))
        ece = compute_field_ece(results, gt_list, field_type)
        if ece > 0:
            ece_values.append(ece)
            metrics["field_metrics"][field_type.value]["ece"] = ece

    if ece_values:
        metrics["overall"]["mean_ece"] = float(np.mean(ece_values))

    # Bootstrap CIs for overall accuracy
    if all_accuracies:
        ci_low, ci_high = bootstrap_ci(all_accuracies, n_bootstrap=1000)
        metrics["overall"]["accuracy_ci"] = [ci_low, ci_high]

    # Straight-through rate at fixed precision
    # Choose threshold on dev (here using 0.8)
    stp_threshold = 0.8
    high_conf_results = [r for r in results if r.cost_usd >= 0]  # All for now
    if high_conf_results:
        correct = 0
        total = 0
        for r in high_conf_results:
            for ft in field_types:
                field = r.get_header_fields().get(ft)
                if field and field.calibrated_confidence and field.calibrated_confidence >= stp_threshold:
                    total += 1
                    gt = ground_truth.get(r.document_path.split("/")[-1].replace(".html", "").replace(".pdf", ""), {})
                    gt_val = gt.get(ft)
                    if gt_val:
                        pred_val = field.normalized_value or field.value
                        if pred_val == gt_val:
                            correct += 1

        metrics["overall"]["stp_at_precision"] = {
            "threshold": stp_threshold,
            "rate": correct / total if total > 0 else 0,
            "n_predictions": total,
        }

    return metrics


def evaluate_field(
    field_type: FieldType,
    results: list,
    ground_truth: dict[str, dict[FieldType, str]],
) -> dict[str, Any]:
    """Evaluate a single field type."""
    predictions = []
    targets = []
    confidences = []

    for result in results:
        invoice_name = result.document_path.split("/")[-1].replace(".html", "").replace(".pdf", "")
        gt = ground_truth.get(invoice_name, {})
        gt_val = gt.get(field_type)

        field = result.get_header_fields().get(field_type)
        if field and gt_val is not None:
            pred_val = field.normalized_value or field.value

            # Normalize for comparison
            if field_type in (FieldType.SUBTOTAL, FieldType.TOTAL_TAX, FieldType.GRAND_TOTAL,
                             FieldType.VENDOR_GSTIN, FieldType.BUYER_GSTIN):
                # Numeric comparison
                try:
                    pred_num = normalize_number(pred_val)
                    gt_num = normalize_number(gt_val)
                    correct = abs(pred_num - gt_num) < 0.01
                except ValueError:
                    correct = pred_val.strip().lower() == gt_val.strip().lower()
            elif field_type == FieldType.INVOICE_DATE:
                # Date comparison
                try:
                    pred_date = normalize_date(pred_val)
                    gt_date = normalize_date(gt_val)
                    correct = pred_date == gt_date
                except ValueError:
                    correct = pred_val.strip().lower() == gt_val.strip().lower()
            else:
                # String comparison
                correct = pred_val.strip().lower() == gt_val.strip().lower()

            predictions.append(1 if correct else 0)
            targets.append(1)
            confidences.append(field.calibrated_confidence or field.confidence)

    if not predictions:
        return {"accuracy": 0.0, "n_samples": 0}

    accuracy = sum(predictions) / len(predictions)
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0

    # Bootstrap CI
    ci_low, ci_high = bootstrap_ci(predictions, n_bootstrap=1000)

    return {
        "accuracy": accuracy,
        "mean_confidence": mean_confidence,
        "ci": [ci_low, ci_high],
        "n_samples": len(predictions),
    }


def evaluate_line_items(
    results: list,
    ground_truth: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate line item extraction."""
    # Simplified for now
    return {"line_item_f1": 0.0, "n_samples": 0}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run extraction evaluation")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Data directory")
    parser.add_argument("--output-dir", type=Path, default=Path("evals/results"), help="Output directory")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev", help="Split to evaluate")
    parser.add_argument("--configs", nargs="+", default=["E0", "E1", "E2", "E3", "E4"], help="Configs to evaluate")
    parser.add_argument("--use-mock", action="store_true", default=True, help="Use mock backends")
    parser.add_argument("--max-docs", type=int, default=50, help="Max documents to evaluate")
    args = parser.parse_args()

    # Load ground truth
    gt_dir = args.data_dir / "ground_truth"
    ground_truth = load_ground_truth(gt_dir)

    # Get invoice paths
    invoice_dir = args.data_dir / "invoices"
    invoice_paths = sorted(invoice_dir.glob("*"))[:args.max_docs]

    # Filter by split if needed
    if args.split != "all":
        split_file = args.data_dir / "splits" / f"{args.split}.json"
        if split_file.exists():
            with open(split_file) as f:
                split_data = json.load(f)
            split_ids = set(split_data.get("invoice_ids", []))
            # Filter invoice paths by IDs in ground truth
            filtered_paths = []
            for p in invoice_paths:
                # Load GT to get invoice_id
                gt_file = gt_dir / f"{p.stem}.json"
                if gt_file.exists():
                    with open(gt_file) as f:
                        gt = json.load(f)
                    if gt.get("invoice_id") in split_ids:
                        filtered_paths.append(p)
            invoice_paths = filtered_paths


    # Dry-run cost estimate
    if not args.use_mock and len(invoice_paths) > 50:
        pass
        # Could add actual cost estimation here

    # Run evaluation for each config
    all_results = {}
    for config_name in args.configs:
        metrics = evaluate_config(config_name, invoice_paths, ground_truth, args.use_mock)
        all_results[config_name] = metrics

    # Write results
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _json_path, _md_path = write_results(
        {"extraction_ablation": all_results},
        args.output_dir,
        prefix=f"extraction_{args.split}",
    )


    # Print comparison table
    for config_name in args.configs:
        m = all_results[config_name]
        _ = m['overall'].get('mean_accuracy', 0)
        _ = m['overall'].get('mean_ece', 0)
        _ = m['avg_cost_usd']
        _ = m['avg_latency_ms']


if __name__ == "__main__":
    main()
