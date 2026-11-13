"""
Unit normalization utilities for financial filings.
Standardizes reporting units, currencies, and decimal scale multipliers.
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger("filingguard.extraction.unit_normalizer")

# Standard currency codes and multipliers
CURRENCY_ALIASES = {
    "USD": "USD",
    "ISO4217:USD": "USD",
    "$": "USD",
    "DOLLARS": "USD",
    "EUR": "EUR",
    "ISO4217:EUR": "EUR",
    "GBP": "GBP",
}

SCALE_MULTIPLIERS = {
    "thousands": 1e3,
    "millions": 1e6,
    "billions": 1e9,
}


class UnitNormalizer:
    """Normalizes currency units and scales raw values."""

    @staticmethod
    def normalize_unit(unit_str: Optional[str]) -> str:
        """Standardize a raw unit string into canonical form (e.g. 'USD')."""
        if not unit_str:
            return "USD"
        cleaned = unit_str.strip().upper()
        return CURRENCY_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def scale_value(
        raw_value: float,
        scale_label: Optional[str] = None,
        decimals: Optional[int] = None,
    ) -> float:
        """Scale a reported raw financial value according to scale label or decimals."""
        multiplier = 1.0
        if scale_label:
            cleaned_scale = scale_label.strip().lower()
            multiplier = SCALE_MULTIPLIERS.get(cleaned_scale, 1.0)
        elif decimals is not None and decimals < 0:
            # XBRL decimals attribute: -6 means in millions, -3 means in thousands
            multiplier = 10 ** abs(decimals)

        return raw_value * multiplier

    @staticmethod
    def are_units_compatible(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
        """Check if two unit representations refer to the same monetary currency."""
        norm_a = UnitNormalizer.normalize_unit(unit_a)
        norm_b = UnitNormalizer.normalize_unit(unit_b)
        return norm_a == norm_b

