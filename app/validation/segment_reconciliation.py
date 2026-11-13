"""
Segment reconciliation validation service.
Validates that dimensional segment line items do not conflict with consolidated totals.
"""
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("filingguard.validation.segment_reconciliation")


class SegmentRollupResult(BaseModel):
    metric_id: str
    consolidated_value: float
    segment_sum: float
    difference: float
    is_valid: bool
    segment_count: int
    tolerance: float


class SegmentReconciliationService:
    """Verifies that reported segment breakdowns reconcile cleanly with consolidated figures."""

    @staticmethod
    def verify_segment_sum(
        metric_id: str,
        consolidated_value: float,
        segment_values: List[float],
        tolerance_pct: float = 0.01,
    ) -> SegmentRollupResult:
        """Compare the sum of dimensional segment components against reported consolidated total."""
        seg_sum = sum(segment_values)
        diff = abs(consolidated_value - seg_sum)
        allowed_tol = max(1.0, abs(consolidated_value) * tolerance_pct)
        is_valid = diff <= allowed_tol

        return SegmentRollupResult(
            metric_id=metric_id,
            consolidated_value=consolidated_value,
            segment_sum=seg_sum,
            difference=diff,
            is_valid=is_valid,
            segment_count=len(segment_values),
            tolerance=allowed_tol,
        )

