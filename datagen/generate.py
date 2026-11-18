"""Main CLI for synthetic data generation.

Generates vendors, POs, GRNs, invoices with ground truth and manifest.
Deterministic with seeded random generation.
"""

import argparse
import json
import random
from pathlib import Path

from .gstin import generate_random_gstin
from .models import (
    DefectType,
    GroundTruth,
    Invoice,
    Manifest,
    PurchaseOrder,
    Split,
    Vendor,
)
from .render import WEASYPRINT_AVAILABLE, render_invoice
from .utils import (
    generate_goods_receipt,
    generate_invoice,
    generate_purchase_order,
    generate_vendor,
    get_template_for_invoice,
    select_defect_type,
)


class DataGenerator:
    """Main data generator orchestrator."""

    def __init__(self, seed: int, output_dir: Path):
        self.seed = seed
        self.output_dir = output_dir
        self.rng = random.Random(seed)

        # Output subdirectories
        self.invoices_dir = output_dir / "invoices"
        self.ground_truth_dir = output_dir / "ground_truth"

        # Data storage
        self.vendors: list[Vendor] = []
        self.purchase_orders: list[PurchaseOrder] = []
        self.goods_receipts: list = []
        self.invoices: list[Invoice] = []
        self.ground_truths: list[GroundTruth] = []

        # Manifest
        self.manifest = Manifest(seed=seed, generator_version="1.0.0")

        # Splits
        self.splits: dict[str, Split] = {
            "dev": Split(name="dev"),
            "test": Split(name="test"),
            "adversarial": Split(name="adversarial"),
            "policy_qa": Split(name="policy_qa"),
            "real_capture": Split(name="real_capture"),
        }

        # Template directory
        self.template_dir = Path(__file__).parent / "templates"

    def generate_vendors(self, count: int = 60) -> list[Vendor]:
        """Generate vendors with valid GSTINs."""
        # Distribute across states
        state_codes = ["29", "07", "27", "33", "36", "24", "08", "09", "19", "06"]
        vendors = []

        for i in range(count):
            state_code = state_codes[i % len(state_codes)]
            vendor = generate_vendor(self.rng)
            # Override GSTIN with specific state
            vendor.gstin = generate_random_gstin(self.rng, state_code)
            vendor.address.state = type(vendor.address.state)(state_code)
            vendors.append(vendor)

        self.vendors = vendors
        return vendors

    def generate_purchase_orders(self, count: int = 400) -> list[PurchaseOrder]:
        """Generate purchase orders linked to vendors."""
        pos = []
        for i in range(count):
            vendor = self.rng.choice(self.vendors)
            po = generate_purchase_order(self.rng, vendor, i + 1)
            pos.append(po)

        self.purchase_orders = pos
        return pos

    def generate_goods_receipts(self) -> list:
        """Generate GRNs for POs (partial deliveries)."""
        grns = []
        grn_num = 1

        for po in self.purchase_orders:
            # 85% of POs have GRNs
            if self.rng.random() < 0.85:
                # Some POs have multiple partial GRNs
                num_grns = self.rng.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]

                for _ in range(num_grns):
                    grn = generate_goods_receipt(self.rng, po, grn_num)
                    grns.append(grn)
                    grn_num += 1

        self.goods_receipts = grns
        return grns

    def generate_invoices(self, count: int = 660) -> list[Invoice]:
        """Generate invoices with defects."""
        invoices = []
        ground_truths = []

        # Defect distribution: 55% clean (D01), 45% spread across D02-D15
        # For test split: ensure at least 8 of each D02-D15
        defect_counts = dict.fromkeys(DefectType, 0)

        for i in range(count):
            # Select vendor
            vendor = self.rng.choice(self.vendors)

            # Select PO (80% have PO reference)
            po = self.rng.choice(self.purchase_orders) if self.rng.random() < 0.8 else None

            # Select GRN if PO exists
            grn = None
            if po:
                matching_grns = [g for g in self.goods_receipts if g.po_id == po.id]
                if matching_grns and self.rng.random() < 0.9:
                    grn = self.rng.choice(matching_grns)

            # Determine split (for defect distribution)
            if i < 300:
                split = "dev"
            elif i < 600:
                split = "test"
            elif i < 660:
                split = "adversarial"
            elif i < 720:
                split = "policy_qa"
            else:
                split = "real_capture"

            # Select defect type
            defect_type = select_defect_type(self.rng, split)
            defect_counts[defect_type] += 1

            # Select template
            template_name = get_template_for_invoice(self.rng, i)

            # Determine text layer (50% have it)
            has_text_layer = self.rng.random() < 0.5

            # Generate invoice
            invoice = generate_invoice(
                rng=self.rng,
                vendor=vendor,
                po=po,
                grn=grn,
                invoice_num=i + 1,
                template_name=template_name,
                defect_type=defect_type,
                has_text_layer=has_text_layer,
            )

            invoices.append(invoice)
            self.splits[split].add_invoice(invoice.id)

            # Create ground truth
            gt = GroundTruth.from_invoice(invoice, po, grn)
            ground_truths.append(gt)

        self.invoices = invoices
        self.ground_truths = ground_truths

        return invoices

    def render_invoices(self) -> None:
        """Render all invoices to PDF (or HTML if WeasyPrint unavailable)."""
        ext = ".pdf" if WEASYPRINT_AVAILABLE else ".html"

        self.invoices_dir.mkdir(parents=True, exist_ok=True)

        for i, invoice in enumerate(self.invoices):
            if i % 50 == 0:
                pass

            output_path = self.invoices_dir / f"{invoice.invoice_number}{ext}"

            # Find vendor
            vendor = next(v for v in self.vendors if v.id == invoice.vendor_id)

            # Render
            render_invoice(
                template_name=invoice.template_name,
                invoice=invoice,
                vendor=vendor,
                output_path=output_path,
                template_dir=self.template_dir,
                degrade=True,
                keep_text_layer=invoice.has_text_layer,
                rng=self.rng,
            )


    def write_ground_truth(self) -> None:
        """Write ground truth JSON files."""
        self.ground_truth_dir.mkdir(parents=True, exist_ok=True)

        for gt in self.ground_truths:
            output_path = self.ground_truth_dir / f"{gt.invoice_number}.json"

            # Convert to JSON-serializable dict
            data = gt.model_dump(mode="json")

            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)


    def write_manifest(self) -> None:
        """Write dataset manifest with SHA-256 hashes."""
        manifest_path = self.output_dir / "manifest.json"
        ext = ".pdf" if WEASYPRINT_AVAILABLE else ".html"

        # Add all generated files to manifest
        for file_path in self.invoices_dir.rglob(f"*{ext}"):
            self.manifest.add_file(file_path, self.output_dir)

        for file_path in self.ground_truth_dir.rglob("*.json"):
            self.manifest.add_file(file_path, self.output_dir)

        # Add stats
        self.manifest.stats = {
            "vendors": len(self.vendors),
            "purchase_orders": len(self.purchase_orders),
            "goods_receipts": len(self.goods_receipts),
            "invoices": len(self.invoices),
            "splits": {name: split.count for name, split in self.splits.items()},
            "defect_distribution": {},  # Would need to compute
        }

        with open(manifest_path, "w") as f:
            f.write(self.manifest.to_json())

        # Add manifest to itself
        self.manifest.add_file(manifest_path, self.output_dir)

        # Rewrite manifest with its own hash
        with open(manifest_path, "w") as f:
            f.write(self.manifest.to_json())


    def write_splits(self) -> None:
        """Write split index files."""
        splits_dir = self.output_dir / "splits"
        splits_dir.mkdir(parents=True, exist_ok=True)

        for name, split in self.splits.items():
            split_path = splits_dir / f"{name}.json"
            data = {
                "name": split.name,
                "count": split.count,
                "invoice_ids": [str(id) for id in split.invoice_ids],
            }
            with open(split_path, "w") as f:
                json.dump(data, f, indent=2)


    def run(self) -> Manifest:
        """Run the complete generation pipeline."""
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate all entities
        self.generate_vendors(60)
        self.generate_purchase_orders(400)
        self.generate_goods_receipts()
        self.generate_invoices(720)  # 300 dev + 300 test + 60 adv + 60 policy + 20 real

        # Render PDFs
        self.render_invoices()

        # Write ground truth
        self.write_ground_truth()

        # Write splits
        self.write_splits()

        # Write manifest
        self.write_manifest()


        return self.manifest


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic invoice data for LedgerLens")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--output", type=Path, default=Path("data"), help="Output directory")
    parser.add_argument("--vendors", type=int, default=60, help="Number of vendors")
    parser.add_argument("--pos", type=int, default=400, help="Number of purchase orders")
    parser.add_argument("--invoices", type=int, default=720, help="Number of invoices")

    args = parser.parse_args()

    generator = DataGenerator(args.seed, args.output)
    generator.run()


if __name__ == "__main__":
    main()
