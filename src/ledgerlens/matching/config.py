"""Configuration loader for matching."""

from pathlib import Path

import yaml

from .models import MatchingConfig

_DEFAULT_CONFIG_PATH = Path("config/matching.yaml")


def load_matching_config(config_path: Path | None = None) -> MatchingConfig:
    """Load matching configuration from YAML file."""
    if config_path is None:
        config_path = _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        # Return defaults
        return MatchingConfig()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return MatchingConfig()

    # Parse UoM conversions
    uom_conversions = {}
    for from_uom, to_factors in data.get("uom_conversions", {}).items():
        uom_conversions[from_uom] = {}
        for to_uom, factor in to_factors.items():
            uom_conversions[from_uom][to_uom] = factor

    # Parse HSN overrides
    hsn_overrides = {}
    for hsn, overrides in data.get("hsn_overrides", {}).items():
        hsn_overrides[hsn] = overrides

    return MatchingConfig(
        price_tolerance_pct=data.get("price_tolerance_pct", 2.0),
        quantity_tolerance_abs=data.get("quantity_tolerance_abs", 0.01),
        uom_conversions=uom_conversions,
        hsn_overrides=hsn_overrides,
        require_grn=data.get("require_grn", True),
        require_po=data.get("require_po", True),
    )


def get_hsn_config(hsn_code: str, config: MatchingConfig) -> dict:
    """Get HSN-specific configuration overrides."""
    return config.hsn_overrides.get(hsn_code, {})
