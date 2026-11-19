"""Seed database with synthetic data from M1 datagen."""

import json
import logging
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import (
    GoodsReceipt,
    GRNLine,
    GRNStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    POLine,
    POStatus,
    PurchaseOrder,
    TaxType,
    Vendor,
)

logger = logging.getLogger(__name__)

INDIAN_STATES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman & Diu",
    "26": "Dadra & Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar",
    "36": "Telangana",
    "37": "Andhra Pradesh (new)",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

STATE_CODES = list(INDIAN_STATES.keys())


def load_ground_truth(gt_dir: Path) -> list[dict]:
    """Load ground truth JSON files."""
    invoices_data = []
    for gt_file in gt_dir.glob("*.json"):
        with open(gt_file) as f:
            data = json.load(f)
        invoices_data.append(data)
    return invoices_data


def generate_gstin(state_code: str, pan: str) -> str:
    """Generate a valid GSTIN with checksum."""
    # GSTIN format: 2-digit state + 10-char PAN + 1-char entity + 1-char Z + 1-char checksum
    # Using simplified approach - just return a valid-looking GSTIN
    base = f"{state_code}{pan}1Z"
    # Calculate checksum
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    weights = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    total = 0
    for i, ch in enumerate(base):
        val = chars.index(ch)
        total += val * weights[i]
    check_val = (36 - (total % 36)) % 36
    checksum = chars[check_val]
    return base + checksum


async def create_vendors(session: AsyncSession, invoices_data: list[dict]) -> dict[str, Vendor]:
    """Create vendors from invoice data."""
    vendors = {}
    vendor_gstins = set()

    for inv_data in invoices_data:
        header = inv_data.get("header", {})
        vendor_gstin = header.get("vendor_gstin")
        if vendor_gstin and vendor_gstin not in vendor_gstins:
            vendor_gstins.add(vendor_gstin)
            vendor = Vendor(
                gstin=vendor_gstin,
                legal_name=header.get("vendor_name", "Unknown Vendor"),
                trade_name=header.get("vendor_name"),
                address_line1=header.get("vendor_address", "123 Vendor Street"),
                city=header.get("vendor_city", "Bangalore"),
                state_code=vendor_gstin[:2],
                pincode=header.get("vendor_pincode", "560001"),
                bank_account_name=header.get("vendor_bank_name", header.get("vendor_name")),
                bank_account_number=header.get("vendor_bank_account", "1234567890"),
                bank_ifsc=header.get("vendor_ifsc", "HDFC0001234"),
                bank_name=header.get("vendor_bank_name", "HDFC Bank"),
                contact_person=header.get("vendor_contact", "John Doe"),
                contact_email=header.get("vendor_email", "vendor@example.com"),
                contact_phone=header.get("vendor_phone", "9876543210"),
                is_active=True,
                created_at=datetime(2023, 1, 1),  # Fixed date well over 90 days ago
            )
            session.add(vendor)
            vendors[vendor_gstin] = vendor

    # Flush to get IDs
    await session.flush()
    return vendors


async def create_purchase_orders(
    session: AsyncSession, vendors: dict[str, Vendor], invoices_data: list[dict]
) -> dict[str, PurchaseOrder]:
    """Create purchase orders from invoice data."""
    pos = {}

    for inv_data in invoices_data:
        header = inv_data.get("header", {})
        po_ref = header.get("po_reference")
        if po_ref and po_ref not in pos:
            vendor_gstin = header.get("vendor_gstin")
            vendor = vendors.get(vendor_gstin)
            if not vendor:
                continue

            po = PurchaseOrder(
                po_number=po_ref,
                vendor_id=vendor.id,
                po_date=date.today() - timedelta(days=random.randint(30, 90)),
                delivery_date=date.today() + timedelta(days=random.randint(7, 30)),
                buyer_gstin=header.get("buyer_gstin", "29ABCDE1234F1Z5"),
                buyer_name=header.get("buyer_name", "Test Buyer"),
                buyer_address=header.get("buyer_address", "456 Buyer Street, Bangalore"),
                buyer_state_code=header.get("buyer_state_code", "29"),
                place_of_supply=header.get("place_of_supply", "29"),
                status=POStatus.OPEN,
                currency="INR",
            )
            session.add(po)
            pos[po_ref] = po

    await session.flush()
    return pos


async def create_po_lines(session: AsyncSession, pos: dict[str, PurchaseOrder], invoices_data: list[dict]) -> None:
    """Create PO lines from invoice line items."""
    for inv_data in invoices_data:
        header = inv_data.get("header", {})
        po_ref = header.get("po_reference")
        po = pos.get(po_ref)
        if not po:
            continue

        lines = inv_data.get("lines", [])
        for idx, line_data in enumerate(lines):
            qty = Decimal(str(line_data.get("quantity", 1)))
            price = Decimal(str(line_data.get("unit_price", 1000)))
            discount = Decimal(str(line_data.get("discount_percent", 0)))
            tax_rate = Decimal(str(line_data.get("tax_rate", 18)))
            tax_type_str = line_data.get("tax_type", "IGST")
            tax_type = TaxType(tax_type_str) if tax_type_str in TaxType.__members__ else TaxType.IGST

            taxable = qty * price * (Decimal("1") - discount / Decimal("100"))
            tax = taxable * tax_rate / Decimal("100")
            line_total = taxable + tax

            po_line = POLine(
                po_id=po.id,
                line_number=idx + 1,
                item_code=line_data.get("item_code", f"ITEM{idx + 1:03d}"),
                item_description=line_data.get("item_description", "Test Item"),
                hsn_code=line_data.get("hsn_code", "998713"),
                uom=line_data.get("uom", "PCS"),
                quantity=qty,
                unit_price=price,
                discount_percent=discount,
                tax_rate=tax_rate,
                tax_type=tax_type,
                taxable_value=taxable.quantize(Decimal("0.01")),
                tax_amount=tax.quantize(Decimal("0.01")),
                line_total=line_total.quantize(Decimal("0.01")),
            )
            session.add(po_line)

    await session.flush()


async def create_goods_receipts(
    session: AsyncSession, pos: dict[str, PurchaseOrder], vendors: dict[str, Vendor]
) -> dict[str, GoodsReceipt]:
    """Create goods receipts for POs."""
    grns = {}

    for po_ref, po in pos.items():
        # Create GRN for each PO
        grn_number = f"GRN-{po_ref}"
        vendor = None
        for v in vendors.values():
            if v.id == po.vendor_id:
                vendor = v
                break

        if not vendor:
            continue

        grn = GoodsReceipt(
            grn_number=grn_number,
            po_id=po.id,
            vendor_id=vendor.id,
            grn_date=date.today() - timedelta(days=random.randint(1, 15)),
            status=GRNStatus.COMPLETE,
            received_by="Warehouse Staff",
        )
        session.add(grn)
        grns[grn_number] = grn

    await session.flush()
    return grns


async def create_grn_lines(session: AsyncSession, grns: dict[str, GoodsReceipt], pos: dict[str, PurchaseOrder]) -> None:
    """Create GRN lines matching PO lines."""
    for _, grn in grns.items():
        po = None
        for p in pos.values():
            if p.id == grn.po_id:
                po = p
                break

        if not po:
            continue

        # Get PO lines
        result = await session.execute(select(POLine).where(POLine.po_id == po.id))
        po_lines = result.scalars().all()

        for idx, po_line in enumerate(po_lines):
            # Receive full quantity
            qty_received = po_line.quantity
            qty_accepted = po_line.quantity

            grn_line = GRNLine(
                grn_id=grn.id,
                po_line_id=po_line.id,
                line_number=idx + 1,
                quantity_received=qty_received,
                quantity_accepted=qty_accepted,
                quantity_rejected=Decimal("0"),
            )
            session.add(grn_line)

    await session.flush()


async def create_invoices(
    session: AsyncSession, vendors: dict[str, Vendor], invoices_data: list[dict]
) -> dict[str, Invoice]:
    """Create invoices from ground truth data."""
    invoices = {}

    for inv_data in invoices_data:
        header = inv_data.get("header", {})
        vendor_gstin = header.get("vendor_gstin")
        vendor = vendors.get(vendor_gstin)
        if not vendor:
            continue

        invoice_number = header.get("invoice_number", f"INV-{random.randint(10000, 99999)}")
        inv_date_str = header.get("invoice_date", date.today().isoformat())
        try:
            inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()
        except ValueError:
            inv_date = date.today()

        invoice = Invoice(
            invoice_number=invoice_number,
            vendor_id=vendor.id,
            invoice_date=inv_date,
            due_date=inv_date + timedelta(days=30),
            buyer_gstin=header.get("buyer_gstin", "29ABCDE1234F1Z5"),
            buyer_name=header.get("buyer_name", "Test Buyer"),
            buyer_address=header.get("buyer_address", "456 Buyer Street, Bangalore"),
            buyer_state_code=header.get("buyer_state_code", "29"),
            place_of_supply=header.get("place_of_supply", "29"),
            place_of_delivery=header.get("place_of_delivery", "29"),
            po_reference=header.get("po_reference"),
            grn_reference=header.get("grn_reference"),
            irn=header.get("irn"),
            eway_bill_number=header.get("eway_bill_number"),
            currency="INR",
            subtotal=Decimal(str(header.get("subtotal", 0))),
            total_tax=Decimal(str(header.get("total_tax", 0))),
            grand_total=Decimal(str(header.get("grand_total", 0))),
            cgst_amount=Decimal(str(header.get("cgst_amount", 0))),
            sgst_amount=Decimal(str(header.get("sgst_amount", 0))),
            igst_amount=Decimal(str(header.get("igst_amount", 0))),
            cess_amount=Decimal(str(header.get("cess_amount", 0))),
            status=InvoiceStatus.DRAFT,
            payment_terms=header.get("payment_terms", "Net 30"),
            bank_account_name=header.get("vendor_bank_name", vendor.bank_account_name),
            bank_account_number=header.get("vendor_bank_account", vendor.bank_account_number),
            bank_ifsc=header.get("vendor_ifsc", vendor.bank_ifsc),
            bank_name=header.get("vendor_bank_name", vendor.bank_name),
            defect_flags={},
            extraction_confidence=Decimal("0.95"),
        )
        session.add(invoice)
        invoices[invoice_number] = invoice

    await session.flush()
    return invoices


async def create_invoice_lines(session: AsyncSession, invoices: dict[str, Invoice], invoices_data: list[dict]) -> None:
    """Create invoice lines from ground truth data."""
    for inv_data in invoices_data:
        header = inv_data.get("header", {})
        invoice_number = header.get("invoice_number", f"INV-{random.randint(10000, 99999)}")
        invoice = invoices.get(invoice_number)
        if not invoice:
            continue

        lines = inv_data.get("lines", [])
        for idx, line_data in enumerate(lines):
            qty = Decimal(str(line_data.get("quantity", 1)))
            price = Decimal(str(line_data.get("unit_price", 1000)))
            discount = Decimal(str(line_data.get("discount_percent", 0)))
            tax_rate = Decimal(str(line_data.get("tax_rate", 18)))
            tax_type_str = line_data.get("tax_type", "IGST")
            tax_type = TaxType(tax_type_str) if tax_type_str in TaxType.__members__ else TaxType.IGST

            taxable = qty * price * (Decimal("1") - discount / Decimal("100"))
            tax = taxable * tax_rate / Decimal("100")
            line_total = taxable + tax

            # Calculate individual tax components
            if tax_type in (TaxType.CGST, TaxType.SGST):
                cgst = tax / 2 if tax_type == TaxType.CGST else Decimal("0")
                sgst = tax / 2 if tax_type == TaxType.SGST else Decimal("0")
                igst = Decimal("0")
            else:
                cgst = Decimal("0")
                sgst = Decimal("0")
                igst = tax
            cess = Decimal("0")

            inv_line = InvoiceLine(
                invoice_id=invoice.id,
                line_number=idx + 1,
                item_code=line_data.get("item_code", f"ITEM{idx + 1:03d}"),
                item_description=line_data.get("item_description", "Test Item"),
                hsn_code=line_data.get("hsn_code", "998713"),
                uom=line_data.get("uom", "PCS"),
                quantity=qty,
                unit_price=price,
                discount_percent=discount,
                tax_rate=tax_rate,
                tax_type=tax_type,
                taxable_value=taxable.quantize(Decimal("0.01")),
                cgst_amount=cgst.quantize(Decimal("0.01")),
                sgst_amount=sgst.quantize(Decimal("0.01")),
                igst_amount=igst.quantize(Decimal("0.01")),
                cess_amount=cess.quantize(Decimal("0.01")),
                tax_amount=tax.quantize(Decimal("0.01")),
                line_total=line_total.quantize(Decimal("0.01")),
            )
            session.add(inv_line)

    await session.flush()


async def seed_database(data_dir: Path | None = None) -> None:
    """Seed the database with synthetic data."""
    if data_dir is None:
        data_dir = Path("data")

    gt_dir = data_dir / "ground_truth"
    if not gt_dir.exists():
        logger.warning("Ground truth directory not found: %s", gt_dir)
        return

    logger.info("Loading ground truth data...")
    invoices_data = load_ground_truth(gt_dir)
    logger.info("Loaded %d invoices", len(invoices_data))

    async with get_session() as session:
        logger.info("Creating vendors...")
        vendors = await create_vendors(session, invoices_data)
        logger.info("Created %d vendors", len(vendors))

        logger.info("Creating purchase orders...")
        pos = await create_purchase_orders(session, vendors, invoices_data)
        logger.info("Created %d purchase orders", len(pos))

        logger.info("Creating PO lines...")
        await create_po_lines(session, pos, invoices_data)

        logger.info("Creating goods receipts...")
        grns = await create_goods_receipts(session, pos, vendors)
        logger.info("Created %d goods receipts", len(grns))

        logger.info("Creating GRN lines...")
        await create_grn_lines(session, grns, pos)

        logger.info("Creating invoices...")
        invoices = await create_invoices(session, vendors, invoices_data)
        logger.info("Created %d invoices", len(invoices))

        logger.info("Creating invoice lines...")
        await create_invoice_lines(session, invoices, invoices_data)

        logger.info("Seeding complete!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed_database())
