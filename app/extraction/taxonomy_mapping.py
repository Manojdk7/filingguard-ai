import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("filingguard.extraction.taxonomy_mapping")


class MetricDefinition(BaseModel):
    metric_id: str
    canonical_name: str
    statement: str
    period_type: str  # 'duration' or 'instant'
    default_unit: str  # e.g., 'USD'
    is_consolidated_only: bool = True
    concepts: List[str]
    description: str


class TaxonomyMappingManager:
    """Loads and manages canonical financial metric definitions and candidate US-GAAP concepts."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (settings.CONFIG_DIR / "metric_mappings.json")
        self.metrics: Dict[str, MetricDefinition] = self._load_mappings()

    def _load_mappings(self) -> Dict[str, MetricDefinition]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Metric mappings configuration not found at {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        metrics_dict: Dict[str, MetricDefinition] = {}
        for m_id, m_meta in data.get("metrics", {}).items():
            metrics_dict[m_id] = MetricDefinition(
                metric_id=m_id,
                canonical_name=m_meta["canonical_name"],
                statement=m_meta["statement"],
                period_type=m_meta["period_type"],
                default_unit=m_meta.get("default_unit", "USD"),
                is_consolidated_only=m_meta.get("is_consolidated_only", True),
                concepts=m_meta.get("concepts", []),
                description=m_meta.get("description", ""),
            )
        return metrics_dict

    def get_all_metrics(self) -> List[MetricDefinition]:
        return list(self.metrics.values())

    def get_metric(self, metric_id: str) -> Optional[MetricDefinition]:
        return self.metrics.get(metric_id)

    def find_metric_by_concept(self, concept_name: str) -> Optional[MetricDefinition]:
        """Reverse lookup: find canonical metric that includes concept_name."""
        for m_def in self.metrics.values():
            if concept_name in m_def.concepts:
                return m_def
        return None
