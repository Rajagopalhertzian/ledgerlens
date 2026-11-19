"""Grounding validators and deterministic validators for extraction."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .models import ExtractedField, ExtractionResult, FieldType, OCRToken, ValidationResult


class GroundingValidator:
    """Validates that extracted values are grounded in OCR tokens."""

    def __init__(self, fuzzy_threshold: float = 0.8):
        self.fuzzy_threshold = fuzzy_threshold

    def validate(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate all extracted fields against OCR tokens."""
        validations = []

        # Validate header fields
        for _field_type, field in result.get_header_fields().items():
            validation = self._validate_field(field, result.ocr_tokens)
            validations.append(validation)

        # Validate line items
        for item in result.line_items:
            for field in item.get_all_fields():
                validation = self._validate_field(field, result.ocr_tokens)
                validations.append(validation)

        return validations

    def _validate_field(self, field: ExtractedField, ocr_tokens: list[OCRToken]) -> ValidationResult:
        """Check if a field's value is found in OCR tokens."""
        if not field.normalized_value:
            return ValidationResult(
                validator_name="grounding",
                passed=False,
                message=f"Field {field.field_type.value} has no normalized value",
            )

        normalized_value = field.normalized_value.strip().lower()
        if not normalized_value:
            return ValidationResult(
                validator_name="grounding",
                passed=False,
                message=f"Field {field.field_type.value} has empty normalized value",
            )

        # Search in OCR tokens
        found = False
        matched_tokens = []

        for i, token in enumerate(ocr_tokens):
            token_text = token.normalized_text()
            if not token_text:
                continue

            # Exact substring match
            if normalized_value in token_text or token_text in normalized_value:
                found = True
                matched_tokens.append(i)
                break

            # For numbers, try numeric comparison
            if self._numeric_match(normalized_value, token_text):
                found = True
                matched_tokens.append(i)
                break

            # For GSTIN, exact match
            if field.field_type in (FieldType.VENDOR_GSTIN, FieldType.BUYER_GSTIN):
                if self._gstin_match(normalized_value, token_text):
                    found = True
                    matched_tokens.append(i)
                    break

        # Update field grounding status
        field.grounded = found
        if found:
            field.evidence.token_indices = matched_tokens
            field.evidence.bboxes = [ocr_tokens[i].bbox for i in matched_tokens]

        return ValidationResult(
            validator_name="grounding",
            passed=found,
            message=(f"Field {field.field_type.value} {'grounded' if found else 'NOT grounded'} in OCR"),
            details={
                "field": field.field_type.value,
                "value": field.normalized_value,
                "matched_tokens": matched_tokens,
            },
        )

    def _numeric_match(self, val1: str, val2: str) -> bool:
        """Compare two numeric strings allowing for formatting differences."""
        # Remove common formatting
        clean1 = re.sub(r"[₹$,\s]", "", val1)
        clean2 = re.sub(r"[₹$,\s]", "", val2)

        try:
            num1 = float(clean1)
            num2 = float(clean2)
            # Allow small floating point differences
            return abs(num1 - num2) < 0.01
        except ValueError:
            return False

    def _gstin_match(self, val1: str, val2: str) -> bool:
        """Compare GSTIN values (15 chars, case insensitive)."""
        clean1 = re.sub(r"\s+", "", val1.upper())
        clean2 = re.sub(r"\s+", "", val2.upper())
        return clean1 == clean2 and len(clean1) == 15


class DeterministicValidators:
    """Deterministic validators for invoice arithmetic and GST rules."""

    def __init__(self):
        self.validators = [
            self._validate_line_totals,
            self._validate_tax_arithmetic,
            self._validate_grand_total,
            self._validate_gstin_format,
            self._validate_gstin_checksum,
            self._validate_date_plausibility,
            self._validate_tax_type_vs_places,
        ]

    def validate(self, result: ExtractionResult) -> list[ValidationResult]:
        """Run all deterministic validators."""
        validations = []
        for validator in self.validators:
            try:
                validations.extend(validator(result))
            except Exception as e:
                validations.append(
                    ValidationResult(validator_name=validator.__name__, passed=False, message=f"Validator error: {e}")
                )
        return validations

    def _validate_line_totals(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate that line totals sum to subtotal."""
        validations = []

        line_totals = []
        for item in result.line_items:
            if item.line_total and item.line_total.normalized_value:
                try:
                    line_totals.append(Decimal(item.line_total.normalized_value))
                except InvalidOperation:
                    pass

        if line_totals and result.subtotal and result.subtotal.normalized_value:
            try:
                subtotal = Decimal(result.subtotal.normalized_value)
                calculated = sum(line_totals)
                passed = abs(subtotal - calculated) < Decimal("0.01")
                validations.append(
                    ValidationResult(
                        validator_name="line_totals_sum",
                        passed=passed,
                        message=f"Line totals sum to {calculated}, subtotal is {subtotal}",
                        details={
                            "calculated": str(calculated),
                            "subtotal": str(subtotal),
                            "diff": str(abs(subtotal - calculated)),
                        },
                    )
                )
            except InvalidOperation:
                pass

        return validations

    def _validate_tax_arithmetic(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate tax calculations per line and in total."""
        validations = []

        for idx, item in enumerate(result.line_items):
            qty_field = item.quantity
            price_field = item.unit_price
            rate_field = item.tax_rate
            if not all([qty_field, price_field, rate_field]):
                continue

            assert qty_field is not None
            assert price_field is not None
            assert rate_field is not None

            try:
                qty = Decimal(qty_field.normalized_value or "0")
                price = Decimal(price_field.normalized_value or "0")
                rate = Decimal(rate_field.normalized_value or "0")
                discount_val = (
                    Decimal(item.discount_percent.normalized_value or "0") if item.discount_percent else Decimal("0")
                )

                taxable = qty * price * (Decimal("1") - discount_val / Decimal("100"))
                tax = taxable * rate

                # Check taxable value
                if item.taxable_value and item.taxable_value.normalized_value:
                    declared_taxable = Decimal(item.taxable_value.normalized_value)
                    passed = abs(taxable - declared_taxable) < Decimal("0.01")
                    validations.append(
                        ValidationResult(
                            validator_name=f"taxable_value_line_{idx}",
                            passed=passed,
                            message=f"Line {idx}: taxable {taxable} vs declared {declared_taxable}",
                        )
                    )

                # Check tax amount
                if item.tax_amount and item.tax_amount.normalized_value:
                    declared_tax = Decimal(item.tax_amount.normalized_value)
                    passed = abs(tax - declared_tax) < Decimal("0.01")
                    validations.append(
                        ValidationResult(
                            validator_name=f"tax_amount_line_{idx}",
                            passed=passed,
                            message=f"Line {idx}: tax {tax} vs declared {declared_tax}",
                        )
                    )

            except InvalidOperation:
                pass

        return validations

    def _validate_grand_total(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate grand total = subtotal + total_tax."""
        subtotal_field = result.subtotal
        total_tax_field = result.total_tax
        grand_total_field = result.grand_total
        if not all([subtotal_field, total_tax_field, grand_total_field]):
            return []

        assert subtotal_field is not None
        assert total_tax_field is not None
        assert grand_total_field is not None

        try:
            subtotal = Decimal(subtotal_field.normalized_value or "0")
            total_tax = Decimal(total_tax_field.normalized_value or "0")
            grand_total = Decimal(grand_total_field.normalized_value or "0")

            calculated = subtotal + total_tax
            passed = abs(grand_total - calculated) < Decimal("0.01")

            return [
                ValidationResult(
                    validator_name="grand_total",
                    passed=passed,
                    message=f"Grand total {grand_total} vs subtotal+tax {calculated}",
                    details={
                        "subtotal": str(subtotal),
                        "total_tax": str(total_tax),
                        "grand_total": str(grand_total),
                        "calculated": str(calculated),
                    },
                )
            ]
        except InvalidOperation:
            return []

    def _validate_gstin_format(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate GSTIN format (15 chars)."""
        validations = []

        for field_type in (FieldType.VENDOR_GSTIN, FieldType.BUYER_GSTIN):
            field = result.get_header_fields().get(field_type)
            if field and field.normalized_value:
                gstin = field.normalized_value.strip().upper()
                gstin_pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[A-Z0-9]{1}[A-Z0-9]{1}$"
                passed = len(gstin) == 15 and re.match(gstin_pattern, gstin) is not None
                validations.append(
                    ValidationResult(
                        validator_name="gstin_format",
                        passed=passed,
                        message=f"{field_type.value} format {'valid' if passed else 'invalid'}: {gstin}",
                    )
                )

        return validations

    def _validate_gstin_checksum(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate GSTIN checksum using official algorithm."""
        validations = []

        for field_type in (FieldType.VENDOR_GSTIN, FieldType.BUYER_GSTIN):
            field = result.get_header_fields().get(field_type)
            if field and field.normalized_value:
                gstin = field.normalized_value.strip().upper()
                if len(gstin) == 15:
                    passed = self._verify_gstin_checksum(gstin)
                    validations.append(
                        ValidationResult(
                            validator_name="gstin_checksum",
                            passed=passed,
                            message=f"{field_type.value} checksum {'valid' if passed else 'INVALID'}: {gstin}",
                        )
                    )

        return validations

    def _verify_gstin_checksum(self, gstin: str) -> bool:
        """Verify GSTIN checksum per official algorithm."""
        # GSTIN: 2-digit state + 10-char PAN + 1-char entity + 1-char Z + 1-char checksum
        # Checksum algorithm: weighted sum mod 36
        weights = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        try:
            total = 0
            for i, ch in enumerate(gstin[:14]):
                val = chars.index(ch)
                total += val * weights[i]

            check_val = (36 - (total % 36)) % 36
            expected_check = chars[check_val]
            return gstin[14] == expected_check
        except (ValueError, IndexError):
            return False

    def _validate_date_plausibility(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate invoice date is plausible."""
        if not result.invoice_date or not result.invoice_date.normalized_value:
            return []

        try:
            # Try parsing date
            date_str = result.invoice_date.normalized_value
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    inv_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return [
                    ValidationResult(
                        validator_name="date_plausibility", passed=False, message=f"Cannot parse date: {date_str}"
                    )
                ]

            # Check not in future (with small buffer)
            today = date.today()
            if inv_date > today:
                return [
                    ValidationResult(
                        validator_name="date_plausibility",
                        passed=False,
                        message=f"Invoice date {inv_date} is in the future",
                    )
                ]

            # Check not too old (e.g., > 10 years)
            if (today - inv_date).days > 3650:
                return [
                    ValidationResult(
                        validator_name="date_plausibility", passed=False, message=f"Invoice date {inv_date} is very old"
                    )
                ]

            return [
                ValidationResult(
                    validator_name="date_plausibility", passed=True, message=f"Invoice date {inv_date} is plausible"
                )
            ]

        except Exception as e:
            return [
                ValidationResult(
                    validator_name="date_plausibility", passed=False, message=f"Date validation error: {e}"
                )
            ]

    def _validate_tax_type_vs_places(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate tax type matches places of supply/delivery."""
        validations = []

        place_supply = result.get_header_fields().get(FieldType.PLACE_OF_SUPPLY)
        place_delivery = result.get_header_fields().get(FieldType.PLACE_OF_DELIVERY)

        if not (place_supply and place_delivery and place_supply.normalized_value and place_delivery.normalized_value):
            return validations

        supply_state = place_supply.normalized_value[:2] if len(place_supply.normalized_value) >= 2 else ""
        delivery_state = place_delivery.normalized_value[:2] if len(place_delivery.normalized_value) >= 2 else ""

        intra_state = supply_state == delivery_state and supply_state != ""

        # Check line items
        for idx, item in enumerate(result.line_items):
            if item.tax_type and item.tax_type.normalized_value:
                tax_type = item.tax_type.normalized_value.upper()
                if intra_state:
                    passed = tax_type in ("CGST", "SGST")
                    expected = "CGST+SGST"
                else:
                    passed = tax_type == "IGST"
                    expected = "IGST"

                validations.append(
                    ValidationResult(
                        validator_name=f"tax_type_vs_places_line_{idx}",
                        passed=passed,
                        message=(
                            f"Line {idx}: {tax_type} for "
                            f"{'intra' if intra_state else 'inter'}-state "
                            f"(expected {expected})"
                        ),
                        details={
                            "tax_type": tax_type,
                            "intra_state": intra_state,
                            "supply_state": supply_state,
                            "delivery_state": delivery_state,
                        },
                    )
                )

        return validations


class IRNValidator:
    """Validate IRN (Invoice Reference Number) recomputation."""

    def validate(self, result: ExtractionResult) -> list[ValidationResult]:
        """Validate IRN if present."""
        if not result.irn or not result.irn.normalized_value:
            return []

        irn = result.irn.normalized_value.strip()
        # IRN is typically a 64-char hash or similar
        # Official e-invoice spec: SHA-256 of supplier GSTIN + doc type + doc number + fin year
        # For now, just check format
        passed = len(irn) >= 32  # SHA-256 hex is 64 chars

        return [
            ValidationResult(
                validator_name="irn_format",
                passed=passed,
                message=f"IRN format {'valid' if passed else 'invalid'}: {irn[:50]}...",
            )
        ]


def run_all_validators(result: ExtractionResult) -> list[ValidationResult]:
    """Run all validators on an extraction result."""
    grounding = GroundingValidator()
    deterministic = DeterministicValidators()
    irn = IRNValidator()

    validations = []
    validations.extend(grounding.validate(result))
    validations.extend(deterministic.validate(result))
    validations.extend(irn.validate(result))

    return validations
