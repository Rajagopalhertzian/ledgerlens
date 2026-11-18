"""Utility functions for synthetic data generation."""

import random
import string
from datetime import date, timedelta
from decimal import Decimal

from .gstin import generate_random_gstin
from .models import (
    Address,
    BankAccount,
    Defect,
    DefectType,
    GoodsReceipt,
    GRNLine,
    Invoice,
    InvoiceLine,
    POLine,
    PurchaseOrder,
    StateCode,
    TaxType,
    UoM,
    Vendor,
)

# Indian names for vendors
INDIAN_COMPANY_PREFIXES = [
    "Shree", "Sri", "M/s", "Om", "Jai", "Bharat", "Hindustan", "Indian",
    "National", "Universal", "Global", "Prime", "Supreme", "Royal", "Imperial",
    "Modern", "Classic", "Elite", "Premium", "Standard", "Quality", "Superior",
    "Best", "Top", "First", "Choice", "Select", "Fine", "Grand", "Major",
]

INDIAN_COMPANY_SUFFIXES = [
    "Enterprises", "Industries", "Trading Co.", "Corporation", "Group",
    "Associates", "Partners", "Solutions", "Systems", "Technologies",
    "Products", "Manufacturers", "Suppliers", "Distributors", "Agencies",
    "Services", "Consultants", "Engineering", "Construction", "Electronics",
    "Textiles", "Chemicals", "Pharmaceuticals", "Foods", "Beverages",
    "Automobiles", "Plastics", "Metals", "Steel", "Cement", "Power",
    "Energy", "Logistics", "Warehousing", "Packaging", "Printing",
]

INDIAN_FIRST_NAMES = [
    "Rajesh", "Amit", "Priya", "Sanjay", "Sunita", "Vikram", "Anjali", "Rahul",
    "Pooja", "Arun", "Kavita", "Manoj", "Neha", "Deepak", "Shweta", "Ravi",
    "Meera", "Suresh", "Divya", "Ajay", "Sonia", "Prakash", "Ritu", "Vinod",
    "Geeta", "Naveen", "Seema", "Rajesh", "Anita", "Mahesh", "Rekha", "Satish",
]

INDIAN_LAST_NAMES = [
    "Sharma", "Gupta", "Singh", "Kumar", "Agarwal", "Verma", "Patel", "Reddy",
    "Nair", "Iyer", "Rao", "Joshi", "Desai", "Shah", "Mehta", "Bansal",
    "Mittal", "Jain", "Goyal", "Arora", "Chopra", "Malhotra", "Khanna", "Kapoor",
    "Saxena", "Srivastava", "Tiwari", "Mishra", "Dubey", "Pandey", "Chaturvedi", "Trivedi",
]

INDIAN_CITIES = [
    ("Bengaluru", "29", "560001"),
    ("Mumbai", "27", "400001"),
    ("Delhi", "07", "110001"),
    ("Chennai", "33", "600001"),
    ("Hyderabad", "36", "500001"),
    ("Pune", "27", "411001"),
    ("Ahmedabad", "24", "380001"),
    ("Kolkata", "19", "700001"),
    ("Jaipur", "08", "302001"),
    ("Lucknow", "09", "226001"),
    ("Kanpur", "09", "208001"),
    ("Nagpur", "27", "440001"),
    ("Indore", "23", "452001"),
    ("Thane", "27", "400601"),
    ("Bhopal", "23", "462001"),
    ("Visakhapatnam", "37", "530001"),
    ("Pimpri-Chinchwad", "27", "411018"),
    ("Patna", "10", "800001"),
    ("Vadodara", "24", "390001"),
    ("Ghaziabad", "09", "201001"),
]

HSN_CODES = {
    "Electronics": ["8471", "8517", "8528", "8544", "8536"],
    "Machinery": ["8413", "8414", "8415", "8418", "8421", "8422"],
    "Textiles": ["5208", "5209", "5407", "5512", "5513", "6109"],
    "Chemicals": ["2801", "2802", "2901", "2902", "3801", "3802"],
    "Plastics": ["3901", "3902", "3903", "3904", "3917", "3926"],
    "Metals": ["7201", "7202", "7208", "7210", "7301", "7302"],
    "Food": ["1001", "1006", "1101", "1701", "1901", "2106"],
    "Paper": ["4801", "4802", "4803", "4810", "4811", "4819"],
    "Rubber": ["4001", "4002", "4009", "4011", "4016"],
    "Furniture": ["9401", "9402", "9403", "9404", "9405"],
}

ITEM_DESCRIPTIONS = {
    "Electronics": [
        "Laptop Computer", "Desktop PC", "Monitor 24 inch", "Keyboard USB",
        "Mouse Optical", "Printer LaserJet", "Scanner Flatbed", "Router WiFi",
        "Switch 24 Port", "Server Rack", "UPS 1KVA", "Hard Drive 1TB",
        "RAM 16GB DDR4", "Graphics Card", "Motherboard ATX",
    ],
    "Machinery": [
        "Water Pump 1HP", "Air Compressor", "Refrigeration Unit", "Centrifugal Fan",
        "Hydraulic Press", "Conveyor Belt", "Industrial Mixer", "Packing Machine",
        "CNC Lathe", "Milling Machine", "Welding Set", "Generator 10KVA",
    ],
    "Textiles": [
        "Cotton Fabric Roll", "Polyester Yarn", "Denim Jeans", "T-Shirts Bulk",
        "Bedsheets Set", "Towels Bath", "Curtains Window", "Uniform Fabric",
        "Safety Vest", "Protective Clothing", "Socks Cotton", "Gloves Industrial",
    ],
    "Chemicals": [
        "Sulfuric Acid", "Hydrochloric Acid", "Sodium Hydroxide", "Calcium Carbonate",
        "Industrial Solvent", "Cleaning Agent", "Adhesive Industrial", "Lubricant Oil",
        "Coolant Fluid", "Rust Remover", "Degreaser", "pH Buffer Solution",
    ],
    "Plastics": [
        "PVC Pipes 2 inch", "HDPE Containers", "PP Bags", "PET Bottles",
        "Plastic Pallets", "Cable Ties", "Plastic Crates", "Stretch Film",
        "Bubble Wrap", "Poly Bags", "Plastic Sheets", "Injection Molded Parts",
    ],
    "Metals": [
        "Steel Bars 12mm", "MS Plate 10mm", "GI Sheets", "SS 304 Pipe",
        "Aluminum Angles", "Copper Wire", "Brass Fittings", "Iron Castings",
        "Steel Channels", "Angle Iron", "Flat Bars", "Round Bars",
    ],
    "Food": [
        "Basmati Rice 25kg", "Wheat Flour 50kg", "Sugar Refined", "Edible Oil 15L",
        "Tea Powder 1kg", "Coffee Beans", "Spices Mixed", "Dal Toor 30kg",
        "Salt Iodized", "Biscuits Carton", "Noodles Pack", "Sauce Bottles",
    ],
    "Paper": [
        "A4 Paper Rim", "Notebooks 200pg", "Printing Paper", "Cardboard Boxes",
        "Corrugated Sheets", "Paper Bags", "Tissue Rolls", "Label Stickers",
        "Envelopes Pack", "File Folders", "Register Books", "Carbon Paper",
    ],
    "Rubber": [
        "Industrial Hose", "Rubber Gaskets", "Conveyor Belt Rubber", "O-Rings Set",
        "Rubber Mats", "Tyre Retread", "Rubber Sheets", "Seals Kit",
        "Vibration Mounts", "Expansion Joints", "Rubber Gloves", "Hose Clamps",
    ],
    "Furniture": [
        "Office Chair", "Executive Desk", "Filing Cabinet", "Conference Table",
        "Storage Rack", "Workstation", "Reception Counter", "Bookshelf",
        "Cafeteria Table", "Locker Steel", "Partition Screen", "Whiteboard",
    ],
}

UOM_BY_CATEGORY = {
    "Electronics": [UoM.PCS, UoM.SET],
    "Machinery": [UoM.PCS, UoM.SET],
    "Textiles": [UoM.MTR, UoM.ROL, UoM.PCS, UoM.SET],
    "Chemicals": [UoM.KG, UoM.LTR, UoM.PCS],
    "Plastics": [UoM.KG, UoM.PCS, UoM.BOX, UoM.PKT],
    "Metals": [UoM.KG, UoM.MTR, UoM.PCS, UoM.BOX],
    "Food": [UoM.KG, UoM.LTR, UoM.PCS, UoM.BOX, UoM.PKT],
    "Paper": [UoM.PCS, UoM.BOX, UoM.PKT, UoM.ROL],
    "Rubber": [UoM.PCS, UoM.MTR, UoM.KG, UoM.SET],
    "Furniture": [UoM.PCS, UoM.SET],
}

TAX_RATES = [Decimal("0.05"), Decimal("0.12"), Decimal("0.18"), Decimal("0.28")]


def random_company_name(rng: random.Random) -> str:
    """Generate a random Indian company name."""
    prefix = rng.choice(INDIAN_COMPANY_PREFIXES)
    suffix = rng.choice(INDIAN_COMPANY_SUFFIXES)
    return f"{prefix} {suffix}"


def random_person_name(rng: random.Random) -> str:
    """Generate a random Indian person name."""
    return f"{rng.choice(INDIAN_FIRST_NAMES)} {rng.choice(INDIAN_LAST_NAMES)}"


def random_address(rng: random.Random, state_code: StateCode | None = None) -> Address:
    """Generate a random Indian address."""
    city_data = rng.choice(INDIAN_CITIES)
    city, state_str, pincode = city_data

    if state_code:
        # Find city with matching state
        matching = [c for c in INDIAN_CITIES if c[1] == state_code.value]
        if matching:
            city_data = rng.choice(matching)
            city, state_str, pincode = city_data

    state = StateCode(state_str)
    road_names = [
        'Main',
        'Park',
        'Gandhi',
        'Nehru',
        'MG',
        'Brigade',
        'Residency',
        'Commercial',
    ]
    line1 = f"{rng.randint(1, 999)} {rng.choice(road_names)} Road"
    line2 = rng.choice([
        "Near Metro Station",
        "Opposite Mall",
        "Behind Temple",
        "Next to Bank",
        None,
    ])

    return Address(
        line1=line1,
        line2=line2,
        city=city,
        state=state,
        pincode=pincode,
    )


def random_bank_account(rng: random.Random) -> BankAccount:
    """Generate a random bank account with masked number."""
    account_num = "".join(rng.choices(string.digits, k=rng.randint(10, 16)))
    ifsc_banks = ["SBIN", "HDFC", "ICIC", "UTIB", "BKID", "PUNB", "CNRB", "IDIB", "UBIN", "KKBK"]
    ifsc = rng.choice(ifsc_banks) + "0" + "".join(
        rng.choices(string.ascii_uppercase + string.digits, k=6)
    )
    banks = [
        "State Bank of India",
        "HDFC Bank",
        "ICICI Bank",
        "Axis Bank",
        "Bank of India",
        "Punjab National Bank",
        "Canara Bank",
        "Indian Bank",
        "Union Bank",
        "Kotak Mahindra Bank",
    ]
    branches = [
        "Main Branch",
        "Corporate Branch",
        "Industrial Area Branch",
        "Commercial Branch",
        "City Branch",
    ]

    return BankAccount(
        account_number=account_num,
        ifsc=ifsc,
        bank_name=rng.choice(banks),
        branch=rng.choice(branches),
        account_holder="",  # Will be set by vendor
    )


def random_phone(rng: random.Random) -> str:
    """Generate random Indian phone number."""
    return f"+91-{rng.randint(70000, 99999)}-{rng.randint(10000, 99999)}"


def random_email(rng: random.Random, company_name: str) -> str:
    """Generate random email from company name."""
    clean = "".join(c.lower() for c in company_name if c.isalnum())
    domains = ["gmail.com", "yahoo.com", "outlook.com", "company.com", "business.in"]
    return f"{clean}{rng.randint(1, 999)}@{rng.choice(domains)}"


def generate_vendor(rng: random.Random, state_code: StateCode | None = None) -> Vendor:
    """Generate a single vendor with valid GSTIN."""
    name = random_company_name(rng)
    address = random_address(rng, state_code)
    bank = random_bank_account(rng)
    bank.account_holder = name

    # Generate GSTIN for the vendor's state
    gstin = generate_random_gstin(rng, state_code.value if state_code else None)

    return Vendor(
        name=name,
        gstin=gstin,
        address=address,
        bank_account=bank,
        email=random_email(rng, name),
        phone=random_phone(rng),
        contact_person=random_person_name(rng),
        is_blocked=rng.random() < 0.02,  # 2% blocked
        approval_limit=Decimal(str(rng.choice([100000, 500000, 1000000, 2000000, 5000000]))),
        requires_second_approver=rng.random() < 0.15,
    )


def generate_po_line(rng: random.Random, line_num: int, category: str | None = None) -> POLine:
    """Generate a single PO line item."""
    if category is None:
        category = rng.choice(list(HSN_CODES.keys()))

    hsn = rng.choice(HSN_CODES[category])
    description = rng.choice(ITEM_DESCRIPTIONS[category])
    uom = rng.choice(UOM_BY_CATEGORY[category])
    quantity = Decimal(str(rng.uniform(1, 1000))).quantize(Decimal("0.01"))
    unit_price = Decimal(str(rng.uniform(100, 50000))).quantize(Decimal("0.01"))
    tax_rate = rng.choice(TAX_RATES)
    tax_type = rng.choice([TaxType.CGST, TaxType.SGST, TaxType.IGST])
    discount = Decimal(str(rng.uniform(0, 10))).quantize(Decimal("0.01")) if rng.random() < 0.3 else Decimal("0")

    return POLine(
        line_number=line_num,
        item_code=f"{category[:3].upper()}{rng.randint(100, 999)}",
        item_description=description,
        hsn_code=hsn,
        uom=uom,
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=tax_rate,
        tax_type=tax_type,
        discount_percent=discount,
    )


def generate_purchase_order(rng: random.Random, vendor: Vendor, po_num: int) -> PurchaseOrder:
    """Generate a purchase order for a vendor."""
    num_lines = rng.randint(1, 8)
    category = rng.choice(list(HSN_CODES.keys()))

    lines = [generate_po_line(rng, i + 1, category) for i in range(num_lines)]

    order_date = date.today() - timedelta(days=rng.randint(1, 365))
    delivery_date = order_date + timedelta(days=rng.randint(7, 90))

    return PurchaseOrder(
        po_number=f"PO{po_num:06d}",
        vendor_id=vendor.id,
        vendor_gstin=vendor.gstin,
        order_date=order_date,
        delivery_date=delivery_date,
        lines=lines,
        terms_and_conditions="Standard terms apply. Payment within 30 days.",
        status=rng.choice(["open", "partial", "closed"]),
    )


def generate_grn_line(rng: random.Random, po_line: POLine) -> GRNLine:
    """Generate a GRN line with partial delivery."""
    # Partial delivery: 80-120% of ordered quantity
    factor = rng.uniform(0.8, 1.2)
    received = (po_line.quantity * Decimal(str(factor))).quantize(Decimal("0.01"))
    accepted = received * Decimal(str(rng.uniform(0.95, 1.0)))
    rejected = received - accepted

    return GRNLine(
        po_line_id=po_line.id,
        received_quantity=received.quantize(Decimal("0.01")),
        accepted_quantity=accepted.quantize(Decimal("0.01")),
        rejected_quantity=rejected.quantize(Decimal("0.01")),
        remarks=rng.choice([None, "Minor damage", "Wrong batch", "Delayed delivery", "Quality check pending"]),
    )


def generate_goods_receipt(rng: random.Random, po: PurchaseOrder, grn_num: int) -> GoodsReceipt:
    """Generate a goods receipt for a PO."""
    lines = [generate_grn_line(rng, po_line) for po_line in po.lines]

    receipt_date = po.order_date + timedelta(days=rng.randint(1, 60))

    return GoodsReceipt(
        grn_number=f"GRN{grn_num:06d}",
        po_id=po.id,
        vendor_id=po.vendor_id,
        vendor_gstin=po.vendor_gstin,
        receipt_date=receipt_date,
        lines=lines,
        status=rng.choice(["received", "partial", "completed"]),
    )


def apply_defects(
    rng: random.Random,
    invoice: Invoice,
    po: PurchaseOrder | None,
    grn: GoodsReceipt | None,
    vendor: Vendor,
    defect_type: DefectType,
) -> Invoice:
    """Apply a specific defect to an invoice."""
    # Make a copy to modify
    invoice = invoice.model_copy(deep=True)

    if defect_type == DefectType.D01:
        # Clean - no defects
        invoice.defects = [Defect(type=DefectType.D01, evidence="All fields consistent")]
        return invoice

    elif defect_type == DefectType.D02:
        # Price variance - change unit price on a random line
        if invoice.lines:
            line = rng.choice(invoice.lines)
            original = line.unit_price
            line.unit_price = (
                original * Decimal(str(rng.uniform(1.15, 1.5)))
            ).quantize(Decimal("0.01"))
            invoice.defects.append(
                Defect(
                    type=DefectType.D02,
                    evidence=(
                        f"Line {line.line_number}: PO price {original}, "
                        f"Invoice price {line.unit_price} (>15% variance)"
                    ),
                )
            )
        return invoice

    elif defect_type == DefectType.D03:
        # Over-billing - quantity exceeds GRN
        if grn and invoice.lines and grn.lines:
            line = rng.choice(invoice.lines)
            grn_line = rng.choice(grn.lines)
            line.quantity = (
                grn_line.accepted_quantity * Decimal(str(rng.uniform(1.1, 1.5)))
            ).quantize(Decimal("0.01"))
            invoice.defects.append(
                Defect(
                    type=DefectType.D03,
                    evidence=(
                        f"Line {line.line_number}: Invoiced qty {line.quantity} "
                        f"> GRN accepted {grn_line.accepted_quantity}"
                    ),
                )
            )
        return invoice

    elif defect_type == DefectType.D04:
        # No GRN - remove GRN reference
        invoice.grn_reference = None
        invoice.defects.append(Defect(
            type=DefectType.D04,
            evidence="No Goods Receipt Note found for this invoice"
        ))
        return invoice

    elif defect_type == DefectType.D05:
        # Exact duplicate - will be handled at generation level
        invoice.defects.append(Defect(
            type=DefectType.D05,
            evidence="Exact duplicate of existing invoice (same GSTIN + FY + type + number)"
        ))
        return invoice

    elif defect_type == DefectType.D06:
        # Near duplicate - similar vendor/amount, altered number/date
        invoice.invoice_number = f"INV{rng.randint(100000, 999999)}"
        invoice.invoice_date = date.today() - timedelta(days=rng.randint(1, 30))
        invoice.defects.append(Defect(
            type=DefectType.D06,
            evidence="Near duplicate: similar vendor and amount, different number/date"
        ))
        return invoice

    elif defect_type == DefectType.D07:
        # Wrong tax type - use IGST for intra-state or vice versa
        for line in invoice.lines:
            if line.tax_type == TaxType.CGST:
                line.tax_type = TaxType.IGST
            elif line.tax_type == TaxType.IGST:
                line.tax_type = TaxType.CGST
        invoice.defects.append(Defect(
            type=DefectType.D07,
            evidence="Tax type mismatch: IGST used for intra-state supply or CGST/SGST for inter-state"
        ))
        return invoice

    elif defect_type == DefectType.D08:
        # Tax arithmetic error - make taxes not add up
        if invoice.lines:
            line = rng.choice(invoice.lines)
            line.tax_rate = Decimal(str(rng.uniform(0.05, 0.28))).quantize(Decimal("0.01"))
            # Don't recompute totals - leave them inconsistent
        invoice.defects.append(Defect(
            type=DefectType.D08,
            evidence="Tax arithmetic error: taxes/totals do not add up correctly"
        ))
        return invoice

    elif defect_type == DefectType.D09:
        # Invalid/mismatched GSTIN
        invoice.vendor_gstin = "29INVALIDGSTIN1"
        invoice.defects.append(Defect(
            type=DefectType.D09,
            evidence=f"GSTIN checksum fails or mismatches vendor master: {invoice.vendor_gstin}"
        ))
        return invoice

    elif defect_type == DefectType.D10:
        # Bank detail change
        if invoice.bank_account:
            invoice.bank_account.account_number = "".join(rng.choices(string.digits, k=12))
            invoice.bank_account.ifsc = "CHANGED" + "".join(rng.choices(string.ascii_uppercase + string.digits, k=7))
        invoice.defects.append(Defect(
            type=DefectType.D10,
            evidence="Bank account details differ from vendor master record"
        ))
        return invoice

    elif defect_type == DefectType.D11:
        # Missing/wrong PO reference
        if rng.random() < 0.5:
            invoice.po_reference = None
        else:
            invoice.po_reference = f"PO{rng.randint(100000, 999999)}"
        invoice.defects.append(Defect(
            type=DefectType.D11,
            evidence="PO reference missing or points to non-existent PO"
        ))
        return invoice

    elif defect_type == DefectType.D12:
        # Edited amount - totals inconsistent with line items
        invoice.grand_total = (invoice.grand_total * Decimal(str(rng.uniform(1.05, 1.2)))).quantize(Decimal("0.01"))
        invoice.defects.append(Defect(
            type=DefectType.D12,
            evidence="Post-render edit detected: grand total inconsistent with line items"
        ))
        return invoice

    elif defect_type == DefectType.D13:
        # Embedded instruction (invisible text)
        invoice.defects.append(Defect(
            type=DefectType.D13,
            evidence="Embedded instruction detected in document metadata/white-on-white text"
        ))
        return invoice

    elif defect_type == DefectType.D14:
        # Illegible/not an invoice
        invoice.defects.append(Defect(
            type=DefectType.D14,
            evidence="Document is illegible or not a valid invoice"
        ))
        return invoice

    elif defect_type == DefectType.D15:
        # Policy violation
        invoice.defects.append(Defect(
            type=DefectType.D15,
            evidence="Policy violation: amount exceeds approval limit or vendor blocked"
        ))
        return invoice

    return invoice


def generate_invoice(
    rng: random.Random,
    vendor: Vendor,
    po: PurchaseOrder | None,
    grn: GoodsReceipt | None,
    invoice_num: int,
    template_name: str,
    defect_type: DefectType,
    has_text_layer: bool,
) -> Invoice:
    """Generate a single invoice with optional defects."""
    # Build invoice lines from PO lines if available
    lines = []
    if po:
        for _i, po_line in enumerate(po.lines):
            # 90% chance to include each PO line
            if rng.random() < 0.9:
                invoice_line = InvoiceLine(
                    line_number=len(lines) + 1,
                    item_code=po_line.item_code,
                    item_description=po_line.item_description,
                    hsn_code=po_line.hsn_code,
                    uom=po_line.uom,
                    quantity=po_line.quantity,
                    unit_price=po_line.unit_price,
                    tax_rate=po_line.tax_rate,
                    tax_type=po_line.tax_type,
                    discount_percent=po_line.discount_percent,
                    po_line_id=po_line.id,
                )
                lines.append(invoice_line)

    # If no PO, generate random lines
    if not lines:
        num_lines = rng.randint(1, 6)
        category = rng.choice(list(HSN_CODES.keys()))
        for i in range(num_lines):
            po_line = generate_po_line(rng, i + 1, category)
            invoice_line = InvoiceLine(
                line_number=i + 1,
                item_code=po_line.item_code,
                item_description=po_line.item_description,
                hsn_code=po_line.hsn_code,
                uom=po_line.uom,
                quantity=po_line.quantity,
                unit_price=po_line.unit_price,
                tax_rate=po_line.tax_rate,
                tax_type=po_line.tax_type,
                discount_percent=po_line.discount_percent,
            )
            lines.append(invoice_line)

    # Create invoice
    invoice_date = date.today() - timedelta(days=rng.randint(0, 30))

    invoice = Invoice(
        invoice_number=f"INV{invoice_num:06d}",
        invoice_date=invoice_date,
        vendor_id=vendor.id,
        vendor_gstin=vendor.gstin,
        vendor_name=vendor.name,
        vendor_address=vendor.address,
        buyer_gstin="29AAAAA0000A1Z5",  # Fixed buyer GSTIN
        buyer_name="LedgerLens Technologies Pvt Ltd",
        buyer_address=Address(
            line1="123 Tech Park",
            city="Bengaluru",
            state=StateCode.KA,
            pincode="560100",
        ),
        po_reference=po.po_number if po else None,
        grn_reference=grn.grn_number if grn else None,
        lines=lines,
        place_of_supply=vendor.address.state,
        place_of_delivery=vendor.address.state,
        payment_terms="Net 30 days",
        bank_account=vendor.bank_account,
        template_name=template_name,
        has_text_layer=has_text_layer,
    )

    # Compute totals
    invoice.compute_totals()

    # Apply defects
    invoice = apply_defects(rng, invoice, po, grn, vendor, defect_type)

    # Recompute after defects (except for D08, D12 which should stay inconsistent)
    if defect_type not in [DefectType.D08, DefectType.D12]:
        invoice.compute_totals()

    return invoice


def select_defect_type(rng: random.Random, split: str) -> DefectType:
    """Select defect type based on distribution."""
    if split == "test":
        # Test split: ensure at least 8 of each D02-D15
        # 55% D01, rest distributed among D02-D15
        return _select_defect_for_test(rng)
    else:
        # Dev split: 55% clean, rest spread
        return _select_defect_for_dev(rng)


def _select_defect_for_dev(rng: random.Random) -> DefectType:
    """Select defect for dev split (55% clean)."""
    if rng.random() < 0.55:
        return DefectType.D01

    # 45% spread across D02-D15 (14 types)
    defect_types = list(DefectType)[1:]  # Skip D01
    return rng.choice(defect_types)


def _select_defect_for_test(rng: random.Random) -> DefectType:
    """Select defect for test split with guaranteed minimum per type."""
    # This would need tracking of counts - simplified for now
    if rng.random() < 0.55:
        return DefectType.D01
    defect_types = list(DefectType)[1:]
    return rng.choice(defect_types)


def get_template_for_invoice(rng: random.Random, invoice_num: int) -> str:
    """Select template for an invoice."""
    templates = [
        "template_01_standard",
        "template_02_column_swap",
        "template_03_multi_page",
        "template_04_no_po",
        "template_05_indian_digits",
        "template_06_date_formats",
        "template_07_bilingual_hi",
        "template_08_bilingual_kn",
    ]

    # First 100 invoices use template_01 for consistency
    if invoice_num < 100:
        return templates[0]

    # Distribute remaining across templates
    return rng.choice(templates)


if __name__ == "__main__":
    import random
    rng = random.Random(42)
    vendor = generate_vendor(rng)
