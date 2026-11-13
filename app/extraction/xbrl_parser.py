import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
from app.extraction.arelle_runner import ArelleRunner, ArelleRunResult
from app.database.repositories.xbrl_fact_repository import ParsedXBRLFact

logger = logging.getLogger("filingguard.extraction.xbrl_parser")


def parse_accounting_number(
    raw_val: Any,
    sign: Optional[str] = None,
    scale: Optional[int] = None,
) -> Optional[float]:
    """Parse numeric values from financial/accounting representations.

    Supports:
    - Standard positive/negative numbers: "1,234.56", "-1,234.56"
    - Parentheses negative numbers: "(1,234.56)", "(500)"
    - Trailing minus negative numbers: "1,234.56-", "500-"
    - Currency symbols: $, €, £, ¥ inside or outside parentheses
    - Commas and embedded whitespace
    - Safe handling of zero and negative zero
    - XBRL sign attribute handling without double-negation
    - Optional scale multiplier handling without double scaling
    - Safe rejection of non-numeric, malformed, or invalid inputs
    """
    if raw_val is None:
        return None

    if isinstance(raw_val, (int, float)):
        if math.isnan(raw_val) or math.isinf(raw_val):
            return None
        val = float(raw_val)
        if sign in ("-", "-1") and val > 0:
            val = -val
        if scale is not None and scale != 0:
            multiplier = 10 ** abs(scale) if scale < 0 else 10 ** scale
            val = val * multiplier
        return 0.0 if val == 0.0 else val

    if not isinstance(raw_val, str):
        return None

    s = raw_val.strip()
    if not s:
        return None

    # Strip currency symbols and whitespace from outer edges
    currency_symbols = ("$", "€", "£", "¥")
    for sym in currency_symbols:
        if s.startswith(sym):
            s = s[len(sym):].strip()
        if s.endswith(sym):
            s = s[:-len(sym)].strip()

    is_negative = False

    # Check parentheses: (1,234.56) or ($1,234.56)
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
        for sym in currency_symbols:
            if s.startswith(sym):
                s = s[len(sym):].strip()
            if s.endswith(sym):
                s = s[:-len(sym)].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    # Clean commas, internal spaces, and any remaining currency signs
    s = s.replace(",", "").replace(" ", "")
    for sym in currency_symbols:
        s = s.replace(sym, "")

    # In case there was also a minus sign inside parentheses: e.g. (-1,234.56)
    # Avoid double-negation: (-1,234) is still negative, not positive
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()

    if not s:
        return None

    try:
        val = float(s)
    except (ValueError, TypeError):
        return None

    if math.isnan(val) or math.isinf(val):
        return None

    # Handle XBRL sign attribute (sign='-') without double-negation
    if sign in ("-", "-1"):
        is_negative = True  # Enforce negative, never flip an already negative value back to positive

    # Handle scale attribute if provided
    if scale is not None and scale != 0:
        multiplier = 10 ** abs(scale) if scale < 0 else 10 ** scale
        val = val * multiplier

    result = -abs(val) if is_negative else abs(val)
    if result == 0.0:
        return 0.0
    return result


class XBRLParsingSummary(BaseModel):
    accession_number: str
    total_facts: int
    entity_wide_facts: int
    dimensional_facts: int
    custom_facts: int
    standard_facts: int
    contexts_count: int
    units_count: int


class InlineXBRLParser:
    """
    Parses original filing documents (Inline XBRL / XBRL) via Arelle,
    extracts contexts, units, dimensions, and custom concepts,
    and constructs evidence-linked ParsedXBRLFact objects.
    """

    def __init__(self, arelle_runner: Optional[ArelleRunner] = None):
        self.runner = arelle_runner or ArelleRunner()

    def parse_document(
        self,
        local_file_path: str,
        accession_number: str,
        source_url: str,
        source_doc_hash: str,
    ) -> Tuple[List[ParsedXBRLFact], XBRLParsingSummary]:
        """
        Parses document using Arelle and extracts facts, contexts, units,
        and dimensional attributes.
        """
        run_result, model_xbrl = self.runner.parse_filing(local_file_path)

        if not run_result.success or model_xbrl is None:
            logger.warning(f"Arelle could not process {local_file_path}: {run_result.error_message}")
            empty_summary = XBRLParsingSummary(
                accession_number=accession_number,
                total_facts=0,
                entity_wide_facts=0,
                dimensional_facts=0,
                custom_facts=0,
                standard_facts=0,
                contexts_count=0,
                units_count=0,
            )
            return [], empty_summary

        parsed_facts: List[ParsedXBRLFact] = []
        entity_wide_cnt = 0
        dimensional_cnt = 0
        custom_cnt = 0
        standard_cnt = 0

        # Standard US namespaces
        standard_prefixes = ("us-gaap", "dei", "invest", "srt")

        try:
            for fact in model_xbrl.facts:
                try:
                    # 1. Concept & Namespace
                    qname = fact.qname
                    concept_name = qname.localName if qname else str(fact.elementQname)
                    ns = qname.namespaceURI if qname else ""
                    prefix = qname.prefix if qname else ""

                    # Identify custom concepts (company extensions outside standard taxonomies)
                    is_custom = prefix not in standard_prefixes and not any(std in ns for std in standard_prefixes)

                    # 2. Value extraction
                    raw_str = fact.value
                    sign_attr = None
                    if hasattr(fact, "get"):
                        sign_attr = fact.get("sign")
                    elif hasattr(fact, "attrib") and isinstance(fact.attrib, dict):
                        sign_attr = fact.attrib.get("sign")

                    numeric_val = parse_accounting_number(raw_str, sign=sign_attr)
                    if numeric_val is None and hasattr(fact, "xValue") and isinstance(fact.xValue, (int, float)):
                        if not (math.isnan(fact.xValue) or math.isinf(fact.xValue)):
                            numeric_val = float(fact.xValue)

                    # 3. Context & Period extraction
                    context = fact.context
                    context_id = context.id if context else "UNKNOWN_CTX"
                    period_type = "instant"
                    start_date: Optional[str] = None
                    end_date: str = ""

                    if context:
                        # Prefer exact XML text from context elements if available
                        for elem in context.iter():
                            tag = elem.tag
                            if "instant" in tag and elem.text:
                                period_type = "instant"
                                end_date = elem.text.strip()
                            elif "startDate" in tag and elem.text:
                                period_type = "duration"
                                start_date = elem.text.strip()
                            elif "endDate" in tag and elem.text:
                                period_type = "duration"
                                end_date = elem.text.strip()

                        # Fallback to Arelle datetime properties if not resolved from element text
                        if not end_date:
                            if context.isInstantPeriod:
                                period_type = "instant"
                                end_date = str(context.instantDatetime.date()) if context.instantDatetime else ""
                            elif context.isStartEndPeriod:
                                period_type = "duration"
                                start_date = str(context.startDatetime.date()) if context.startDatetime else None
                                end_date = str(context.endDatetime.date()) if context.endDatetime else ""

                    # 4. Unit extraction
                    unit_obj = fact.unit
                    unit_str: Optional[str] = None
                    if unit_obj:
                        measures = unit_obj.measures
                        if measures and len(measures) > 0 and len(measures[0]) > 0:
                            unit_str = measures[0][0].localName
                        else:
                            unit_str = unit_obj.id

                    # 5. Dimension & Segment extraction
                    dimensions_map: Dict[str, str] = {}
                    is_segment = False
                    if context and context.hasSegment:
                        # Context has dimensional segment members
                        is_segment = True
                        for dim_qname, dim_val in context.qnameDims.items():
                            dim_name = dim_qname.localName
                            if hasattr(dim_val, "memberQname") and dim_val.memberQname:
                                member_name = dim_val.memberQname.localName
                            else:
                                member_name = str(dim_val)
                            dimensions_map[dim_name] = member_name

                    # 6. Source location evidence locator
                    source_loc: Optional[str] = None
                    if hasattr(fact, "sourceline") and fact.sourceline is not None:
                        source_loc = f"line_{fact.sourceline}"
                    elif hasattr(fact, "objectIndex"):
                        source_loc = f"obj_{fact.objectIndex}"

                    parsed_record = ParsedXBRLFact(
                        accession_number=accession_number,
                        concept_name=concept_name,
                        namespace=ns,
                        is_custom=is_custom,
                        value=raw_str,
                        numeric_value=numeric_val,
                        unit=unit_str,
                        context_id=context_id,
                        period_type=period_type,
                        start_date=start_date,
                        end_date=end_date,
                        is_segment=is_segment,
                        dimensions=dimensions_map,
                        source_locator=source_loc,
                        source_doc_hash=source_doc_hash,
                        source_url=source_url,
                    )
                    parsed_facts.append(parsed_record)

                    if is_segment:
                        dimensional_cnt += 1
                    else:
                        entity_wide_cnt += 1

                    if is_custom:
                        custom_cnt += 1
                    else:
                        standard_cnt += 1

                except Exception as item_err:
                    logger.debug(f"Skipping unparseable fact item: {item_err}")
                    continue

            summary = XBRLParsingSummary(
                accession_number=accession_number,
                total_facts=len(parsed_facts),
                entity_wide_facts=entity_wide_cnt,
                dimensional_facts=dimensional_cnt,
                custom_facts=custom_cnt,
                standard_facts=standard_cnt,
                contexts_count=run_result.contexts_count,
                units_count=run_result.units_count,
            )

            return parsed_facts, summary
        finally:
            if hasattr(self.runner, "close_model"):
                self.runner.close_model(model_xbrl)
            elif hasattr(model_xbrl, "close"):
                try:
                    model_xbrl.close()
                except Exception:
                    pass
