"""Calibrated confidence model for extraction results."""

import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from .models import CalibratedConfidence, ExtractedField, ExtractionResult, ExtractionSource, FieldType


class ConfidenceCalibrator:
    """Calibrates raw confidence scores using a fitted model."""

    def __init__(self, method: str = "isotonic"):
        self.method = method
        self.model: Any | None = None
        self.is_fitted = False

    def fit(self, features: list[list[float]], labels: list[int]):
        """Fit calibration model on development data."""
        x_arr = np.array(features)
        y_arr = np.array(labels)

        if self.method == "isotonic":
            self.model = IsotonicRegression(out_of_bounds="clip")
            self.model.fit(x_arr[:, 0], y_arr)  # Use raw confidence as single feature
        elif self.method == "logistic":
            self.model = LogisticRegression()
            self.model.fit(x_arr, y_arr)
        else:
            raise ValueError(f"Unknown calibration method: {self.method}")

        self.is_fitted = True

    def predict(self, features: list[list[float]]) -> list[float]:
        """Predict calibrated confidence."""
        if not self.is_fitted:
            # Return raw confidence if not fitted
            return [f[0] for f in features]

        assert self.model is not None, "Model must be fitted before prediction"
        x_arr = np.array(features)
        if self.method == "isotonic":
            return [float(v) for v in self.model.predict(x_arr[:, 0])]
        else:
            return [float(v) for v in self.model.predict_proba(x_arr)[:, 1]]

    def save(self, path: Path):
        """Save fitted model."""
        with open(path, "wb") as f:
            pickle.dump({"model": self.model, "method": self.method, "is_fitted": self.is_fitted}, f)

    @classmethod
    def load(cls, path: Path) -> "ConfidenceCalibrator":
        """Load fitted model."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        calibrator = cls(method=data["method"])
        calibrator.model = data["model"]
        calibrator.is_fitted = data["is_fitted"]
        return calibrator


def extract_calibration_features(field: ExtractedField, result: ExtractionResult) -> list[float]:
    """Extract features for confidence calibration."""
    features = []

    # 1. Raw model confidence
    features.append(field.confidence)

    # 2. OCR confidence (if grounded)
    if field.grounded and field.evidence.token_indices and result.ocr_tokens:
        ocr_confs = [result.ocr_tokens[i].confidence for i in field.evidence.token_indices]
        features.append(np.mean(ocr_confs) if ocr_confs else 0.0)
    else:
        features.append(0.0)

    # 3. Grounded flag
    features.append(1.0 if field.grounded else 0.0)

    # 4. Source agreement (for fused results)
    if field.source == ExtractionSource.FUSED:
        features.append(1.0)
    else:
        features.append(0.0)

    # 5. Field type difficulty (some fields are harder)
    difficulty_map = {
        FieldType.VENDOR_NAME: 0.8,
        FieldType.VENDOR_GSTIN: 0.9,
        FieldType.INVOICE_NUMBER: 0.9,
        FieldType.INVOICE_DATE: 0.85,
        FieldType.SUBTOTAL: 0.7,
        FieldType.TOTAL_TAX: 0.7,
        FieldType.GRAND_TOTAL: 0.8,
        FieldType.ITEM_DESCRIPTION: 0.6,
        FieldType.QUANTITY: 0.85,
        FieldType.UNIT_PRICE: 0.75,
        FieldType.TAX_RATE: 0.9,
        FieldType.LINE_TOTAL: 0.7,
    }
    features.append(difficulty_map.get(field.field_type, 0.7))

    # 6. Text length (longer text = harder)
    text_len = len(field.value) if field.value else 0
    features.append(min(text_len / 100.0, 1.0))

    return features


def calibrate_extraction_result(
    result: ExtractionResult, calibrator: ConfidenceCalibrator | None = None
) -> ExtractionResult:
    """Calibrate confidence for all fields in an extraction result."""
    if calibrator is None:
        # Use default heuristics if no calibrator
        return _heuristic_calibration(result)

    # Collect features for all fields
    all_fields = result.get_all_fields()
    features_list = [extract_calibration_features(f, result) for f in all_fields]

    # Predict calibrated confidences
    calibrated_values = calibrator.predict(features_list)

    # Update result
    for field, calibrated in zip(all_fields, calibrated_values, strict=False):
        field.calibrated_confidence = float(calibrated)
        result.calibrated_confidences[field.field_type] = CalibratedConfidence(
            raw_confidence=field.confidence, grounded=field.grounded, calibrated=field.calibrated_confidence
        )

    return result


def _heuristic_calibration(result: ExtractionResult) -> ExtractionResult:
    """Heuristic calibration when no fitted model is available."""
    for field in result.get_all_fields():
        # Start with raw confidence
        calibrated = field.confidence

        # Boost if grounded
        if field.grounded:
            calibrated = min(1.0, calibrated * 1.1)

        # Boost if from fused source
        if field.source == ExtractionSource.FUSED:
            calibrated = min(1.0, calibrated * 1.05)

        # Reduce for ungrounded VLM
        if field.source == ExtractionSource.VLM and not field.grounded:
            calibrated *= 0.7

        # Reduce for low OCR confidence tokens
        if field.grounded and field.evidence.token_indices and result.ocr_tokens:
            ocr_confs = [result.ocr_tokens[i].confidence for i in field.evidence.token_indices]
            avg_ocr = np.mean(ocr_confs) if ocr_confs else 0.5
            calibrated *= 0.5 + 0.5 * avg_ocr

        field.calibrated_confidence = float(calibrated)
        result.calibrated_confidences[field.field_type] = CalibratedConfidence(
            raw_confidence=field.confidence, grounded=field.grounded, calibrated=float(calibrated)
        )

    return result


def compute_field_ece(
    results: list[ExtractionResult], ground_truth: list[dict[FieldType, str]], field_type: FieldType, n_bins: int = 10
) -> float:
    """Compute Expected Calibration Error for a specific field type."""
    confidences = []
    accuracies = []

    for result, gt in zip(results, ground_truth, strict=False):
        field = result.get_header_fields().get(field_type)
        if field and field.calibrated_confidence is not None:
            gt_value = gt.get(field_type)
            if gt_value is not None:
                confidences.append(field.calibrated_confidence)
                # Check accuracy
                pred_value = field.normalized_value or field.value
                accuracies.append(1.0 if pred_value == gt_value else 0.0)

    if not confidences:
        return 0.0

    # Bin by confidence
    confidences_arr = np.array(confidences)
    accuracies_arr = np.array(accuracies)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        lower = bin_boundaries[i]
        upper = bin_boundaries[i + 1]
        in_bin = (confidences_arr >= lower) & (confidences_arr < upper)
        if i == n_bins - 1:
            in_bin = (confidences_arr >= lower) & (confidences_arr <= upper)

        prop_in_bin = in_bin.mean()
        if prop_in_bin > 0:
            accuracy_in_bin = accuracies_arr[in_bin].mean()
            avg_confidence_in_bin = confidences_arr[in_bin].mean()
            ece += prop_in_bin * abs(avg_confidence_in_bin - accuracy_in_bin)

    return float(ece)


def selective_prediction_curve(
    results: list[ExtractionResult],
    ground_truth: list[dict[FieldType, str]],
    field_type: FieldType,
    n_points: int = 100,
) -> list[tuple[float, float]]:
    """Compute selective prediction curve (coverage vs precision)."""
    pairs = []

    for result, gt in zip(results, ground_truth, strict=False):
        field = result.get_header_fields().get(field_type)
        if field and field.calibrated_confidence is not None:
            gt_value = gt.get(field_type)
            if gt_value is not None:
                pred_value = field.normalized_value or field.value
                accuracy = 1.0 if pred_value == gt_value else 0.0
                pairs.append((field.calibrated_confidence, accuracy))

    if not pairs:
        return []

    # Sort by confidence descending
    pairs.sort(key=lambda x: x[0], reverse=True)
    accuracies = [p[1] for p in pairs]
    total = len(pairs)

    curve = []
    for i in range(1, n_points + 1):
        k = max(1, int(total * i / n_points))
        coverage = k / total
        precision = sum(accuracies[:k]) / k
        curve.append((coverage, precision))

    return curve
