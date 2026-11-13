import logging
from typing import Dict, List, Optional
from pydantic import BaseModel
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact

logger = logging.getLogger("filingguard.extraction.segment_classifier")


class SegmentFactRecord(BaseModel):
    concept_name: str
    dimension_axis: str
    dimension_member: str
    raw_value: Optional[str] = None
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    period_type: str
    start_date: Optional[str] = None
    end_date: str
    source_locator: Optional[str] = None
    context_id: str


class SegmentClassificationReport(BaseModel):
    accession_number: str
    total_segment_facts: int
    unique_axes: List[str]
    unique_members: List[str]
    segments_by_axis: Dict[str, List[SegmentFactRecord]]


class SegmentClassifier:
    """
    Classifies dimensional segment facts using XBRL axes and members.
    Strictly prevents mistaking segment or geographic facts for consolidated company values.
    Does not perform additive aggregations without explicit disclosure justification.
    """

    def classify_segments(
        self,
        accession_number: str,
        parsed_facts: List[ParsedXBRLFact],
    ) -> SegmentClassificationReport:
        """
        Groups and classifies all dimensional facts for an accession number.
        """
        segment_facts: List[ParsedXBRLFact] = [f for f in parsed_facts if f.is_segment]

        segments_by_axis: Dict[str, List[SegmentFactRecord]] = {}
        unique_axes = set()
        unique_members = set()

        for f in segment_facts:
            # f.dimensions is a dictionary mapping {axis: member}
            for axis, member in f.dimensions.items():
                unique_axes.add(axis)
                unique_members.add(member)

                item = SegmentFactRecord(
                    concept_name=f.concept_name,
                    dimension_axis=axis,
                    dimension_member=member,
                    raw_value=f.value,
                    numeric_value=f.numeric_value,
                    unit=f.unit,
                    period_type=f.period_type,
                    start_date=f.start_date,
                    end_date=f.end_date,
                    source_locator=f.source_locator,
                    context_id=f.context_id,
                )
                segments_by_axis.setdefault(axis, []).append(item)

        return SegmentClassificationReport(
            accession_number=accession_number,
            total_segment_facts=len(segment_facts),
            unique_axes=sorted(list(unique_axes)),
            unique_members=sorted(list(unique_members)),
            segments_by_axis=segments_by_axis,
        )

