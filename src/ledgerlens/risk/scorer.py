"""Risk scoring for invoices."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..db.database import get_session
from ..db.models import Invoice, Vendor
from ..matching.models import MatchResult
from ..validation.orchestrator import ValidationSummary


@dataclass
class RiskFactor:
    """Individual risk factor."""

    name: str
    triggered: bool
    score: float  # 0-100
    description: str
    details: dict = field(default_factory=dict)


@dataclass
class RiskScore:
    """Overall risk score."""

    level: str  # low, medium, high
    score: float  # 0-100
    factors: list[RiskFactor] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def is_high_risk(self) -> bool:
        return self.level == "high"

    @property
    def is_medium_risk(self) -> bool:
        return self.level == "medium"


# Risk factor weights
RISK_WEIGHTS = {
    "new_vendor": 15,
    "bank_change": 20,
    "amount_near_limit": 15,
    "duplicate_likelihood": 25,
    "low_extraction_confidence": 10,
    "injection_flag": 30,
    "validation_failures": 20,
    "match_mismatch": 25,
}

# Thresholds
HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40


async def calculate_risk(
    invoice: Invoice,
    validation_results: ValidationSummary,
    match_result: MatchResult | None = None,
    extraction_confidence: float | None = None,
    session=None,
) -> RiskScore:
    """Calculate risk score for an invoice."""
    if session is None:
        async with get_session() as session:
            return await _calculate_risk(session, invoice, validation_results, match_result, extraction_confidence)
    else:
        return await _calculate_risk(session, invoice, validation_results, match_result, extraction_confidence)


async def _calculate_risk(
    session,
    invoice: Invoice,
    validation_results: ValidationSummary,
    match_result: MatchResult | None,
    extraction_confidence: float | None,
) -> RiskScore:
    """Internal risk calculation."""
    factors = []

    # Get vendor
    vendor_result = await session.execute(select(Vendor).where(Vendor.id == invoice.vendor_id))
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        factors.append(
            RiskFactor(name="unknown_vendor", triggered=True, score=50, description="Vendor not found in master data")
        )
    else:
        # Factor 1: New vendor (registered < 90 days)
        if vendor.created_at:
            days_since_creation = (date.today() - vendor.created_at.date()).days
            if days_since_creation < 90:
                factors.append(
                    RiskFactor(
                        name="new_vendor",
                        triggered=True,
                        score=RISK_WEIGHTS["new_vendor"],
                        description=f"Vendor registered {days_since_creation} days ago",
                        details={"vendor_id": vendor.id, "days_since_creation": days_since_creation},
                    )
                )
            else:
                factors.append(
                    RiskFactor(
                        name="new_vendor",
                        triggered=False,
                        score=0,
                        description=f"Vendor established ({days_since_creation} days)",
                    )
                )

        # Factor 2: Bank details change
        bank_changed = False
        if invoice.bank_account_number and vendor.bank_account_number:
            if invoice.bank_account_number.strip() != vendor.bank_account_number.strip():
                bank_changed = True
        if invoice.bank_ifsc and vendor.bank_ifsc:
            if invoice.bank_ifsc.strip().upper() != vendor.bank_ifsc.strip().upper():
                bank_changed = True

        if bank_changed:
            factors.append(
                RiskFactor(
                    name="bank_change",
                    triggered=True,
                    score=RISK_WEIGHTS["bank_change"],
                    description="Bank details differ from vendor master",
                    details={
                        "invoice_account": invoice.bank_account_number,
                        "master_account": vendor.bank_account_number,
                        "invoice_ifsc": invoice.bank_ifsc,
                        "master_ifsc": vendor.bank_ifsc,
                    },
                )
            )
        else:
            factors.append(
                RiskFactor(name="bank_change", triggered=False, score=0, description="Bank details match vendor master")
            )

    # Factor 3: Amount near approval limit
    # Assuming approval limits: <1L = auto, 1L-10L = manager, >10L = director
    amount = invoice.grand_total
    if amount >= Decimal("1000000"):  # 10 Lakhs
        factors.append(
            RiskFactor(
                name="amount_near_limit",
                triggered=True,
                score=RISK_WEIGHTS["amount_near_limit"],
                description=f"Amount {amount} exceeds high-value threshold",
                details={"amount": str(amount), "threshold": "1000000"},
            )
        )
    elif amount >= Decimal("100000"):  # 1 Lakh
        factors.append(
            RiskFactor(
                name="amount_near_limit",
                triggered=True,
                score=RISK_WEIGHTS["amount_near_limit"] * 0.5,
                description=f"Amount {amount} requires manager approval",
                details={"amount": str(amount), "threshold": "100000"},
            )
        )
    else:
        factors.append(
            RiskFactor(
                name="amount_near_limit",
                triggered=False,
                score=0,
                description=f"Amount {amount} within auto-approval limit",
            )
        )

    # Factor 4: Duplicate likelihood
    # Check V8 and V9 validation results
    v8_failed = any(r.validator == "V8" and not r.passed for r in validation_results.results)
    v9_failed = any(r.validator == "V9" and not r.passed for r in validation_results.results)

    if v8_failed:
        factors.append(
            RiskFactor(
                name="duplicate_likelihood",
                triggered=True,
                score=RISK_WEIGHTS["duplicate_likelihood"],
                description="Exact duplicate detected",
                details={"validator": "V8"},
            )
        )
    elif v9_failed:
        factors.append(
            RiskFactor(
                name="duplicate_likelihood",
                triggered=True,
                score=RISK_WEIGHTS["duplicate_likelihood"] * 0.7,
                description="Near duplicate detected",
                details={"validator": "V9"},
            )
        )
    else:
        factors.append(
            RiskFactor(name="duplicate_likelihood", triggered=False, score=0, description="No duplicates detected")
        )

    # Factor 5: Low extraction confidence
    if extraction_confidence is not None:
        if extraction_confidence < 0.7:
            factors.append(
                RiskFactor(
                    name="low_extraction_confidence",
                    triggered=True,
                    score=RISK_WEIGHTS["low_extraction_confidence"],
                    description=f"Low extraction confidence: {extraction_confidence:.2f}",
                    details={"confidence": extraction_confidence},
                )
            )
        elif extraction_confidence < 0.85:
            factors.append(
                RiskFactor(
                    name="low_extraction_confidence",
                    triggered=True,
                    score=RISK_WEIGHTS["low_extraction_confidence"] * 0.5,
                    description=f"Moderate extraction confidence: {extraction_confidence:.2f}",
                    details={"confidence": extraction_confidence},
                )
            )
        else:
            factors.append(
                RiskFactor(
                    name="low_extraction_confidence",
                    triggered=False,
                    score=0,
                    description=f"High extraction confidence: {extraction_confidence:.2f}",
                )
            )
    else:
        # Check invoice's stored extraction confidence
        if invoice.extraction_confidence:
            conf = float(invoice.extraction_confidence)
            if conf < 0.7:
                factors.append(
                    RiskFactor(
                        name="low_extraction_confidence",
                        triggered=True,
                        score=RISK_WEIGHTS["low_extraction_confidence"],
                        description=f"Low extraction confidence: {conf:.2f}",
                    )
                )
            else:
                factors.append(
                    RiskFactor(
                        name="low_extraction_confidence",
                        triggered=False,
                        score=0,
                        description=f"Extraction confidence: {conf:.2f}",
                    )
                )

    # Factor 6: Injection flag (from defect flags)
    if invoice.defect_flags:
        injection_flag = invoice.defect_flags.get("injection_detected", False)
        if injection_flag:
            factors.append(
                RiskFactor(
                    name="injection_flag",
                    triggered=True,
                    score=RISK_WEIGHTS["injection_flag"],
                    description="Prompt injection detected in document",
                    details={"defect_flags": invoice.defect_flags},
                )
            )
        else:
            factors.append(
                RiskFactor(name="injection_flag", triggered=False, score=0, description="No injection detected")
            )
    else:
        factors.append(RiskFactor(name="injection_flag", triggered=False, score=0, description="No defect flags"))

    # Factor 7: Validation failures
    failed_validations = validation_results.get_failed()
    if failed_validations:
        # Weight by severity
        critical_failures = [f for f in failed_validations if f.validator in ("V1", "V2", "V3", "V4", "V5", "V6")]
        high_failures = [f for f in failed_validations if f.validator in ("V8", "V10", "V11")]

        val_score = 0
        if critical_failures:
            val_score = RISK_WEIGHTS["validation_failures"]
        elif high_failures:
            val_score = RISK_WEIGHTS["validation_failures"] * 0.7
        elif failed_validations:
            val_score = RISK_WEIGHTS["validation_failures"] * 0.3

        factors.append(
            RiskFactor(
                name="validation_failures",
                triggered=val_score > 0,
                score=val_score,
                description=f"{len(failed_validations)} validation(s) failed",
                details={
                    "failed_count": len(failed_validations),
                    "failed_validators": [f.validator for f in failed_validations],
                },
            )
        )
    else:
        factors.append(
            RiskFactor(name="validation_failures", triggered=False, score=0, description="All validations passed")
        )

    # Factor 8: Match mismatch
    if match_result:
        if match_result.status in ("mismatch", "missing_po", "missing_grn"):
            factors.append(
                RiskFactor(
                    name="match_mismatch",
                    triggered=True,
                    score=RISK_WEIGHTS["match_mismatch"],
                    description=f"3-way match status: {match_result.status.value}",
                    details={
                        "status": match_result.status.value,
                        "mismatched_lines": match_result.mismatched_lines,
                        "missing_in_grn": match_result.missing_in_grn,
                        "missing_in_po": match_result.missing_in_po,
                    },
                )
            )
        elif match_result.status == "partial":
            factors.append(
                RiskFactor(
                    name="match_mismatch",
                    triggered=True,
                    score=RISK_WEIGHTS["match_mismatch"] * 0.5,
                    description=f"3-way match partial: {match_result.partial_lines} partial lines",
                    details={"status": match_result.status.value},
                )
            )
        else:
            factors.append(
                RiskFactor(name="match_mismatch", triggered=False, score=0, description="3-way match successful")
            )
    else:
        factors.append(
            RiskFactor(name="match_mismatch", triggered=False, score=0, description="No match result available")
        )

    # Calculate total score
    total_score = sum(f.score for f in factors)
    total_score = min(total_score, 100)  # Cap at 100

    # Determine level
    if total_score >= HIGH_RISK_THRESHOLD:
        level = "high"
    elif total_score >= MEDIUM_RISK_THRESHOLD:
        level = "medium"
    else:
        level = "low"

    # Collect reasons
    reasons = [f.description for f in factors if f.triggered]

    return RiskScore(level=level, score=total_score, factors=factors, reasons=reasons)


def calculate_risk_sync(
    invoice: Invoice,
    validation_results: ValidationSummary,
    match_result: MatchResult | None = None,
    extraction_confidence: float | None = None,
) -> RiskScore:
    """Synchronous version for testing."""
    import asyncio

    return asyncio.run(calculate_risk(invoice, validation_results, match_result, extraction_confidence))


from sqlalchemy import select  # noqa: E402
