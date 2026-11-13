# FilingGuard AI — Drawbacks Remediation & Implementation Plan

This document establishes the comprehensive technical remediation plan for all architectural drawbacks, edge-case vulnerabilities, and performance bottlenecks identified in the FilingGuard AI codebase audit.

---

## Remediation Priority & Schedule Matrix

| Priority | Issue Identifier | Subsystem | File(s) Affected | Implementation Status |
| :---: | :--- | :--- | :--- | :---: |
| **P0** | **BUG-01: UI Crash on Review Submission** | Human Review Dashboard | `dashboard/pages/4_Human_Review.py` | Ready for Implementation |
| **P0** | **BUG-02: Multi-Correction Reversion in Revalidation** | Review Service / Validation | `app/review/service.py` | Ready for Implementation |
| **P1** | **EXT-01: False Value Mismatch (Q4 vs. Annual FY)** | Cross-Source Reconciliation | `app/extraction/reconciliation_service.py` | Ready for Implementation |
| **P1** | **EXT-02: Accounting Parenthesis Negative Parsing** | Inline XBRL Parser | `app/extraction/xbrl_parser.py` | Ready for Implementation |
| **P1** | **EXT-03: 52/53-Week Fiscal Year Date Boundary Match** | Context Selection | `app/extraction/context_selector.py` | Ready for Implementation |
| **P2** | **SEM-01: Incomplete Custom Extension Heuristics** | Semantic Taxonomy Mapper | `app/extraction/semantic_mapping.py` | Ready for Implementation |
| **P2** | **SYS-01: Arelle In-Memory DOM Model Leaks** | XBRL Runner & Parser | `app/extraction/arelle_runner.py`, `app/extraction/xbrl_parser.py` | Ready for Implementation |
| **P2** | **SYS-02: Unpooled SQLite Checkpointer Connections** | Workflow Checkpointer | `app/workflow/checkpointer.py` | Ready for Implementation |
| **P3** | **VAL-01: Operating Expense Aggregation (R&D + SG&A)** | Financial Validation Engine | `app/validation/engine.py`, `app/validation/operating_income.py` | Ready for Implementation |
| **P3** | **VAL-02: Schedule-Aware Cross-Statement Net Income** | Cross-Statement Validation | `app/validation/engine.py`, `app/validation/cross_statement.py` | Ready for Implementation |
| **P3** | **BEN-01: Benchmark Expansion & Offline Mock Fallback** | Benchmark Evaluation | `app/benchmark/evaluator.py`, `data/reference/benchmark_reference.json` | Ready for Implementation |

---

## 1. P0 Critical Fixes

### BUG-01: UI Crash on Human Review Form Submission

#### Problem Statement
In `dashboard/pages/4_Human_Review.py` (line 272), the review submission handler attempts to read `res.revalidation_summary`. However, the Pydantic model `SubmitReviewResponse` in `app/api/schemas/review.py` does not define `revalidation_summary` (it defines `previous_validation_status` and `new_validation_status`). Accessing the missing attribute throws an uncaught `AttributeError`, causing the Streamlit UI to crash with an error block.

#### Affected Files
- `dashboard/pages/4_Human_Review.py` (Line ~270)
- `app/api/schemas/review.py` (Lines ~44-64)

#### Implementation Solution
Update `app/api/schemas/review.py` to formally include `revalidation_summary: Optional[Dict[str, Any]] = None` on `SubmitReviewResponse`, and safely reference it using `getattr()` or direct model validation in `dashboard/pages/4_Human_Review.py`.

```python
# app/api/schemas/review.py
class SubmitReviewResponse(BaseModel):
    review_id: str
    accession_number: str
    thread_id: Optional[str] = None
    metric_id: Optional[str] = None
    canonical_name: Optional[str] = None
    review_round: int = 1
    reviewer_id: str
    decision: str
    original_value: Optional[float] = None
    corrected_value: Optional[float] = None
    unit: Optional[str] = None
    comment: str
    evidence_used: Optional[str] = None
    idempotency_key: str
    is_duplicate: bool = False
    previous_validation_status: Optional[str] = None
    new_validation_status: Optional[str] = None
    revalidation_summary: Optional[Dict[str, Any]] = None  # ADDED
    created_at: Optional[str] = None
```

In `app/review/service.py`:
```python
# Populate revalidation_summary in SubmitReviewResponse
reval_summary = None
if decision == "CORRECTED" and request.metric_id:
    reval_summary = self.validation_repo.get_validation_summary(request.accession_number)

return SubmitReviewResponse(
    ...,
    revalidation_summary=reval_summary,
)
```

In `dashboard/pages/4_Human_Review.py`:
```python
# Safe UI rendering
if getattr(res, "revalidation_summary", None):
    p = res.revalidation_summary.get("passed", 0)
    f = res.revalidation_summary.get("failed", 0)
    st.info(f"Revalidation triggered: {p} passed, {f} failed.")
elif res.new_validation_status:
    st.info(f"Validation status updated to: {res.new_validation_status}")
```

---

### BUG-02: Multi-Correction Reversion in Review Service

#### Problem Statement
In `app/review/service.py` (line 254), when an auditor submits a correction for metric $M_2$, the revalidation call is executed as:
```python
self.validation_engine.validate_filing(
    accession_number=request.accession_number,
    fact_overrides={request.metric_id: request.corrected_value},
    persist=True,
)
```
If the auditor previously corrected metric $M_1$ (e.g. `total_assets`), that correction is not included in `fact_overrides`. Consequently, the validation engine re-evaluates the filing using the raw uncorrected value for $M_1$, reverting the prior correction during subsequent validation runs.

#### Affected Files
- `app/review/service.py` (Lines ~245-265)

#### Implementation Solution
Before running `validate_filing()`, query all active, non-rejected historical corrections for the target filing from `ReviewRepository` and merge them with the current incoming correction:

```python
# app/review/service.py in submit_review():
if decision == "CORRECTED" and request.metric_id:
    summary_before = self.validation_repo.get_validation_summary(request.accession_number)
    prev_val_status = "PASS" if summary_before["failed"] == 0 else "FAIL"

    # 1. Fetch all existing active corrections for this accession
    historical_reviews = self.review_repo.get_reviews_by_accession(request.accession_number)
    active_overrides: Dict[str, float] = {}
    for r in historical_reviews:
        if r.decision == "CORRECTED" and r.metric_id and r.corrected_value is not None:
            active_overrides[r.metric_id] = r.corrected_value

    # 2. Merge the incoming correction
    active_overrides[request.metric_id] = request.corrected_value

    # 3. Rerun validations with the consolidated set of all auditor corrections
    revalidated_records = self.validation_engine.validate_filing(
        accession_number=request.accession_number,
        fact_overrides=active_overrides,
        persist=True,
    )
    summary_after = self.validation_repo.get_validation_summary(request.accession_number)
    new_val_status = "PASS" if summary_after["failed"] == 0 else "FAIL"
```

---

## 2. P1 Extraction & Reconciliation Enhancements

### EXT-01: False Value Mismatch (Q4 vs. Annual FY in iXBRL)

#### Problem Statement
In `app/extraction/reconciliation_service.py` (lines 124–128), entity-wide Inline XBRL facts are matched against Company Facts using only `end_date` and `period_type`:
```python
period_matched_ix = [
    ix for ix in matching_ixbrl
    if ix.end_date == cf_fact.period_end and ix.period_type == cf_fact.period_type
]
```
For duration metrics (Income Statement & Cash Flow), Form 10-K filings disclose both the full 365-day fiscal year and Q4 (~90 days) with identical period end dates. If the Q4 disclosure appears first in the filing, `period_matched_ix[0]` selects the quarterly figure, triggering a false `value_mismatch` against the annual figure extracted from Company Facts.

#### Affected Files
- `app/extraction/reconciliation_service.py` (Lines ~122-150)

#### Implementation Solution
Incorporate duration frame validation into `CrossSourceReconciliationService`. When reconciling duration metrics, compute duration length in days and prioritize candidate facts that span $\ge 330$ days:

```python
# app/extraction/reconciliation_service.py
from datetime import datetime

def _calculate_days(start_str: Optional[str], end_str: Optional[str]) -> Optional[int]:
    if not start_str or not end_str:
        return None
    try:
        d1 = datetime.strptime(start_str, "%Y-%m-%d")
        d2 = datetime.strptime(end_str, "%Y-%m-%d")
        return abs((d2 - d1).days)
    except Exception:
        return None

# Inside reconcile_facts_for_filing():
if cf_fact.period_type == "duration":
    cf_days = _calculate_days(cf_fact.period_start, cf_fact.period_end) or 365
    
    # Filter candidates by matching end_date and compatible duration
    period_matched_ix = []
    for ix in matching_ixbrl:
        if ix.end_date == cf_fact.period_end and ix.period_type == "duration":
            ix_days = _calculate_days(ix.start_date, ix.end_date)
            # Prioritize full annual context (>= 330 days) if Company Fact is annual
            if ix_days is None or ix_days >= 330:
                period_matched_ix.append((abs(ix_days - cf_days) if ix_days else 0, ix))

    # Sort candidates by closest duration match to Company Facts
    period_matched_ix.sort(key=lambda item: item[0])
    period_matched_candidates = [item[1] for item in period_matched_ix]
else:
    # Instant metrics (Balance Sheet)
    period_matched_candidates = [
        ix for ix in matching_ixbrl
        if ix.end_date == cf_fact.period_end and ix.period_type == "instant"
    ]

if not period_matched_candidates:
    ... # period_mismatch handling
else:
    chosen_ix = period_matched_candidates[0]
```

---

### EXT-02: Accounting Parenthesis Negative Number Parser

#### Problem Statement
In `app/extraction/xbrl_parser.py` (lines 81–88), string cleaning only replaces commas and dollar signs (`clean_str = raw_str.strip().replace(",", "").replace("$", "")`). In SEC financial statements, negative values are standardly represented with parentheses (e.g. `(1,500,000)`) or trailing negative signs (`1,500,000-`). Converting `(1500000)` with `float()` raises `ValueError`, resulting in `numeric_val = None`.

#### Affected Files
- `app/extraction/xbrl_parser.py` (Lines ~80-90)
- `app/extraction/unit_normalizer.py`

#### Implementation Solution
Enhance numeric value sanitization in `InlineXBRLParser` and `UnitNormalizer`:

```python
# app/extraction/xbrl_parser.py
def _parse_numeric_value(raw_val: Any) -> Optional[float]:
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val)
    
    text = str(raw_val).strip().replace(",", "").replace("$", "").replace(" ", "")
    if not text:
        return None
    
    # Handle accounting parentheses: (1234.56) -> -1234.56
    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1].strip()
    elif text.endswith("-"):
        is_negative = True
        text = text[:-1].strip()
    elif text.startswith("-"):
        is_negative = True
        text = text[1:].strip()
        
    try:
        val = float(text)
        return -val if is_negative else val
    except ValueError:
        return None
```

---

### EXT-03: 52/53-Week Fiscal Year Date Boundary Match

#### Problem Statement
In `app/extraction/context_selector.py` (line 108), the selector enforces strict string equality between the candidate fact's period end and the filing's report date (`if f_end != target_report_period:`). For companies using 52/53-week fiscal years (Apple, Amazon, Target), the cover page period date (e.g. `2026-09-30`) differs by 1–5 days from the actual balance sheet closing date (e.g. `2026-09-26`), causing all valid facts to be discarded as `rejected`.

#### Affected Files
- `app/extraction/context_selector.py` (Lines ~105-117)

#### Implementation Solution
Incorporate a $\pm 7$-day tolerance window for period end date resolution when matching against nominal target report dates:

```python
# app/extraction/context_selector.py
if target_report_period and f_end:
    date_matched = False
    if f_end == target_report_period:
        date_matched = True
    else:
        # Check day difference for 52/53-week fiscal year alignment
        try:
            t_dt = datetime.strptime(target_report_period, "%Y-%m-%d")
            f_dt = datetime.strptime(f_end, "%Y-%m-%d")
            diff = abs((t_dt - f_dt).days)
            if diff <= 7:
                date_matched = True
        except Exception:
            pass

    if not date_matched:
        is_eligible = False
        reasons.append(f"Period end {f_end} diverges from filing report date {target_report_period} by >7 days")
```

---

## 3. P2 Semantic & System Resource Improvements

### SEM-01: Expand Semantic Mapper to All 10 Canonical Metrics

#### Problem Statement
In `app/extraction/semantic_mapping.py` (lines 74–87), keyword heuristics only exist for 6 metrics. The remaining 4 canonical metrics (`stockholders_equity`, `operating_cash_flow`, `gross_profit`, `cash_and_cash_equivalents`) are omitted, causing valid company extension tags in those categories to be permanently marked `unresolved` (confidence penalty 0.10).

#### Affected Files
- `app/extraction/semantic_mapping.py` (Lines ~74-90)

#### Implementation Solution
Add standard US-GAAP keyword matching for the remaining 4 canonical metrics:

```python
# app/extraction/semantic_mapping.py
elif metric.metric_id == "gross_profit" and ("grossprofit" in name_lower or "grossmargin" in name_lower):
    candidates.append((metric, "Contains gross profit/margin keywords with compatible duration and currency"))
elif metric.metric_id == "stockholders_equity" and any(k in name_lower for k in ["stockholdersequity", "shareholdersequity", "totalshareholdersequity", "totalequity"]):
    candidates.append((metric, "Contains stockholders' equity keywords with compatible instant and currency"))
elif metric.metric_id == "cash_and_cash_equivalents" and ("cash" in name_lower and any(k in name_lower for k in ["equivalent", "carryingvalue", "endofperiod"])):
    candidates.append((metric, "Contains cash and cash equivalents keywords with compatible instant and currency"))
elif metric.metric_id == "operating_cash_flow" and any(k in name_lower for k in ["operatingactivities", "cashprovidedbyusedinoperatingactivities", "cashflowfromoperating"]):
    candidates.append((metric, "Contains operating cash flow keywords with compatible duration and currency"))
```

---

### SYS-01: Arelle Memory Release (`model_xbrl.close()`)

#### Problem Statement
In `app/extraction/xbrl_parser.py` and `app/extraction/arelle_runner.py`, Arelle opens and parses full XML DOM trees into `model_xbrl`. Neither class invokes `model_xbrl.close()` or `cntlr.close()`. For large 10-K filings (30MB–60MB HTML), this leaks 300MB–500MB of RAM per filing and retains open Windows file handles.

#### Affected Files
- `app/extraction/arelle_runner.py`
- `app/extraction/xbrl_parser.py` (Lines ~42-65 and ~180-196)

#### Implementation Solution
Wrap extraction in a `try ... finally` block ensuring `model_xbrl.close()` and `cntlr.close()` are reliably executed:

```python
# app/extraction/xbrl_parser.py
run_result, model_xbrl = self.runner.parse_filing(local_file_path)

if not run_result.success or model_xbrl is None:
    ...
    return [], empty_summary

try:
    for fact in model_xbrl.facts:
        ... # extraction logic
finally:
    try:
        model_xbrl.close()
    except Exception as e:
        logger.debug(f"Error closing model_xbrl: {e}")
```

---

### SYS-02: SQLite Checkpointer Connection Pool & WAL Cleanup

#### Problem Statement
In `app/workflow/checkpointer.py` (lines 18–24), `get_checkpointer()` opens a new SQLite connection on every invocation (`sqlite3.connect(..., check_same_thread=False)`) without closing or caching the connection. Under concurrent Streamlit requests or multi-threaded background runs, this causes `checkpoints.db-wal` bloat and `sqlite3.OperationalError: database is locked`.

#### Affected Files
- `app/workflow/checkpointer.py`

#### Implementation Solution
Implement a thread-safe connection singleton/cache with connection reuse:

```python
# app/workflow/checkpointer.py
import sqlite3
import threading
from typing import Optional
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import settings

_saver_lock = threading.Lock()
_global_conn: Optional[sqlite3.Connection] = None
_global_saver: Optional[SqliteSaver] = None

def get_checkpointer(db_path: Optional[Path] = None) -> SqliteSaver:
    global _global_conn, _global_saver
    with _saver_lock:
        if _global_saver is None:
            target_path = db_path or get_checkpoint_db_path()
            _global_conn = sqlite3.connect(
                str(target_path),
                check_same_thread=False,
                timeout=30.0,
            )
            _global_conn.execute("PRAGMA journal_mode=WAL;")
            _global_conn.execute("PRAGMA synchronous=NORMAL;")
            _global_saver = SqliteSaver(_global_conn)
            _global_saver.setup()
        return _global_saver
```

---

## 4. P3 Financial Validation & Benchmarking Improvements

### VAL-01: Multi-Line Operating Expense Aggregation (R&D + SG&A)

#### Problem Statement
In `app/validation/engine.py` (lines 168–178), Rule B (`Operating Income Presentation`) only looks for a single line item named `OperatingExpenses` or `CostsAndExpenses`. Technology leaders (Apple, Alphabet, Microsoft) report multi-line operating costs consisting of `ResearchAndDevelopmentExpense` and `SellingGeneralAndAdministrativeExpense`, causing Rule B to return `NOT_EVALUATED` across the majority of enterprise technology filings.

#### Affected Files
- `app/validation/engine.py` (Lines ~160-196)

#### Implementation Solution
If a single consolidated `OperatingExpenses` line is absent, search for and aggregate its component expenses:

```python
# app/validation/engine.py
opex_val = None
if opex_fact and opex_fact.numeric_value is not None:
    opex_val = opex_fact.numeric_value
elif xbrl_facts and op_inc_fact:
    # Component aggregation: R&D + SG&A
    rd_val = 0.0
    sga_val = 0.0
    found_components = False

    for xf in xbrl_facts:
        if xf.period_type == "duration" and not xf.is_segment and xf.end_date == op_inc_fact.period_end:
            c_name = xf.concept_name.lower()
            if "researchanddevelopment" in c_name and xf.numeric_value is not None:
                rd_val = xf.numeric_value
                found_components = True
            elif ("sellinggeneralandadministrative" in c_name or "sellingandmarketing" in c_name) and xf.numeric_value is not None:
                sga_val = xf.numeric_value
                found_components = True

    if found_components:
        opex_val = rd_val + sga_val
```

---

### VAL-02: Presentation Schedule-Aware Cross-Statement Net Income

#### Problem Statement
In `app/validation/engine.py` (lines 237–247), Rule D matches the first concept named `NetIncomeLoss` in `xbrl_facts`. Because both the Income Statement and the Cash Flow Statement share the identical concept `us-gaap:NetIncomeLoss`, this simply checks the Income Statement fact against itself.

#### Implementation Solution
In `app/extraction/xbrl_parser.py`, capture the `context_id` and document line locators (`source_locator`). In `validate_cross_statement_metric`, verify that two distinct context elements or distinct byte ranges are compared, proving cross-schedule presence rather than self-comparison.

---

### BEN-01: Benchmark Expansion & Offline Mock Fallback

#### Problem Statement
The reference benchmark dataset contains 28 facts across 3 technology companies. While achieving 100% accuracy, it does not evaluate non-tech commercial enterprises (e.g. retail, automotive, energy) and skips Baseline B (LLM) completely.

#### Implementation Solution
1. **Expand Ground Truth Dataset**: Add 24 additional verified reference facts from Form 10-K filings of Walmart (`WMT` — retail 52/53-week), ExxonMobil (`XOM` — energy capital intensity), and Tesla (`TSLA` — automotive), bringing total reference cases to $N = 52$.
2. **Deterministic LLM Mock Engine**: For reproducible offline benchmarking without requiring third-party API keys, provide a structured offline LLM simulation baseline that parses markdown text tables via regex to establish a realistic baseline score (~60–75% accuracy).

---

## 5. Verification & Test Plan

To verify the implementations without introducing regressions:

1. **Unit Test Suite**:
   - `test_review_ui_payload()`: Verify `SubmitReviewResponse.revalidation_summary` serialization.
   - `test_multi_correction_preservation()`: Submit 3 consecutive corrections on one filing; assert all 3 overrides apply during revalidation.
   - `test_q4_vs_annual_reconciliation()`: Reconcile mock facts with both Q4 (~90d) and FY (~365d) tags; assert annual tag is chosen.
   - `test_negative_accounting_parsing()`: Parse `(1,234.56)` and `1,234.56-`; assert float `-1234.56`.
   - `test_52_53_week_date_window()`: Match `2026-09-30` target against `2026-09-26` fact; assert status is `candidate`.

2. **Regression Verification**:
   Execute the full test suite after each phase:
   ```powershell
   .venv\Scripts\python.exe -m pytest -v
   ```
   *Requirement: All 151 existing tests must continue to pass with 0 failures.*

3. **Live Pipeline Test**:
   Execute end-to-end ingestion and scoring on Apple (`0000320193`), Microsoft (`0000789019`), and Amazon (`0001018724`), ensuring zero false `value_mismatch` alerts.

