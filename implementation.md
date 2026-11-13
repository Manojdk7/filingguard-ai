# FilingGuard AI --- Implementation Plan

## MINEARENA 2026 \| Financial Filing Auditor

**Document:** `implementation.md`\
**Version:** 1.0\
**Build target:** 24-hour hackathon MVP\
**Initial scope:** US SEC annual Form 10-K filings\
**Recommended stack:** Python 3.11+, FastAPI, LangGraph, SQLite,
Streamlit, SEC EDGAR APIs, Inline XBRL/Arelle

------------------------------------------------------------------------

# 1. Project Overview

## 1.1 Product name

**FilingGuard AI --- Evidence-First Financial Filing Auditor**

## 1.2 One-line pitch

An evidence-linked financial filing auditor that extracts financial
facts from SEC 10-K filings, validates them using deterministic
financial rules, escalates uncertain or inconsistent findings to a human
reviewer, resumes from a durable checkpoint, and verifies extracted
facts against SEC structured data and a manually checked benchmark.

## 1.3 Problem statement

Financial filings contain large amounts of structured and unstructured
information. Extracting a number is not sufficient: the system must also
select the correct accounting concept, reporting period, unit,
dimensional context and filing version. It must show where the value
came from, run appropriate consistency checks, explain uncertainty and
preserve the history of human decisions.

The system is an **auditor copilot**, not an autonomous statutory
auditor, fraud detector or provider of investment advice. It supports
review; it does not certify that a company's accounts are true or free
from fraud.

## 1.4 Main users

-   Financial analysts reviewing public-company filings.
-   Audit associates and reviewers.
-   Hackathon judges evaluating reliable agentic workflows.
-   Developers testing financial extraction and validation.

## 1.5 MVP goals

The MVP must:

1.  Retrieve real SEC filing metadata and an actual 10-K.
2.  Extract at least 8 core financial metrics with period, unit, concept
    and accession metadata.
3.  Preserve source evidence for each extracted value.
4.  Handle annual period selection and units explicitly.
5.  Calculate transparent extraction-quality indicators.
6.  Run deterministic accounting and anomaly checks.
7.  Escalate uncertain or failed checks to a human.
8.  Pause and resume a LangGraph workflow using persistent
    checkpointing.
9.  Compare the selected facts with SEC Company Facts where comparable.
10. Produce an accuracy report against a manually verified reference
    sample.
11. Record decisions in a tamper-evident, hash-chained audit event log.
12. Include automated tests and a reliable offline demo fallback.

## 1.6 Explicit non-goals

Do not attempt these in the 24-hour MVP:

-   Detecting or declaring fraud.
-   Replacing a professional auditor or audit opinion.
-   Supporting every global accounting standard.
-   Full OCR of scanned documents.
-   Full PDF table understanding.
-   Full 10-Q, 20-F and 8-K support before 10-K is stable.
-   Multi-tenant RBAC or enterprise SSO.
-   Cloud deployment unless the MVP is already complete.
-   Autonomous filing submission or external financial actions.
-   Treating an LLM response as numeric ground truth.

------------------------------------------------------------------------

# 2. Product Principles

1.  **Evidence before explanation:** every displayed financial fact must
    point to a source.
2.  **Deterministic numeric logic:** Python code performs calculations,
    comparisons and validation.
3.  **Context-aware extraction:** a metric is not identified by tag name
    alone; period, unit, accession and dimensions matter.
4.  **Visible uncertainty:** ambiguous facts are escalated rather than
    guessed.
5.  **Human accountability:** a reviewer owns approval, correction or
    rejection.
6.  **Recoverable workflow:** completed work is checkpointed;
    interrupted work can resume.
7.  **Reproducible decisions:** preserve filing accession, extraction
    version, rule version and reviewer action.
8.  **Honest claims:** API agreement is not independent proof that a
    company-reported number is economically correct.

------------------------------------------------------------------------

# 3. Existing-System Research and Positioning

Research these products before finalising claims about differentiation:

  -----------------------------------------------------------------------
  Product                 Relevant capability to  Our research question
                          study                   
  ----------------------- ----------------------- -----------------------
  Trullion                Financial statement     What evidence, tie-out
                          validation, evidence    and review capabilities
                          and audit workflows     are already
                                                  commercialised?

  dnl.ai                  Financial disclosure    How are disclosure
                          review and AI-assisted  checks and auditor
                          checking                judgment handled?

  Suralink                Financial statement     Which arithmetic and
                          tie-out                 cross-statement checks
                                                  are automated?

  Flowie Statement        Agent-based statement   Which statement-level
  Auditor                 review                  checks and review
                                                  workflows are
                                                  advertised?

  Calcbench               SEC/XBRL financial data How much extraction,
                          and footnote analytics  historical comparison
                                                  and source traceability
                                                  already exists?

  BamSEC                  SEC filing research     How do users search and
                                                  compare filings?

  AlphaSense              AI-powered financial    What document analysis
                          research and cited      and evidence-linking is
                          document answers        already available?

  Workiva                 SEC reporting, XBRL and How are reporting,
                          compliance workflows    controls, versioning
                                                  and audit trails
                                                  handled?

  Arelle                  Open-source XBRL        Which XBRL parsing and
                          processing and          validation functions
                          validation              can we reuse?

  MindBridge              Financial risk and      How are anomaly and
                          anomaly analytics       risk scoring approaches
                                                  presented?

  Anthropic               Financial workflow      What can a
  financial-services      agent templates         general-purpose agent
  agents                                          template already do?
  -----------------------------------------------------------------------

## 3.1 Positioning rule

Do not claim that competitors lack human review, evidence, audit trails,
confidence scores or anomaly detection unless a reliable source
establishes that limitation.

Classify each finding as one of:

-   **Documented capability:** explicitly described by the vendor or
    technical documentation.
-   **Documented limitation:** explicitly described by a reliable
    source.
-   **Not publicly verified:** public materials reviewed do not
    establish whether the feature exists.
-   **Our prototype opportunity:** a capability we choose to demonstrate
    more specifically.

## 3.2 Proposed differentiation to test

FilingGuard should focus on a narrow, measurable combination:

-   Filing-specific XBRL fact selection.
-   Standard and custom taxonomy mapping with reviewer escalation.
-   Period, unit and dimensional-context validation.
-   Filing-version and accession-aware comparisons.
-   Evidence-linked deterministic financial checks.
-   Durable human-review pause/resume.
-   Independently labelled benchmark results.
-   Tamper-evident decision history.

These are proposed differentiators, not claims that every competitor
lacks them.

------------------------------------------------------------------------

# 4. Scope and Supported Financial Metrics

## 4.1 Initial companies

Use a small, cached set of public companies with strong SEC filing
coverage:

  Company              CIK Why selected
  ----------- ------------ ---------------------------
  Apple         0000320193 Baseline large filer
  Microsoft     0000789019 Large technology filer
  Amazon        0001018724 Segment complexity
  NVIDIA        0001045810 High-growth example
  Walmart       0000104169 Different fiscal year-end

Confirm the latest available filing and accession at runtime. Never
hardcode a filing date or assume the latest filing remains unchanged.

## 4.2 Core metrics

Implement at least these eight; target ten if time permits:

1.  Revenue
2.  Net Income
3.  Total Assets
4.  Total Liabilities
5.  Stockholders' Equity
6.  Net Cash Provided by Operating Activities
7.  Gross Profit
8.  Operating Income
9.  Cash and Cash Equivalents
10. Payments to Acquire Property, Plant and Equipment (CapEx)

## 4.3 Canonical metric mapping

Maintain a versioned mapping file, not scattered `if` statements.

For every metric mapping, store:

-   Canonical metric ID and display name.
-   Candidate taxonomy concepts.
-   Expected unit types.
-   Expected context type (instant or duration).
-   Preferred annual period rules.
-   Sign conventions where relevant.
-   Whether dimensions are permitted or required.
-   Mapping source and mapping version.
-   Notes on concept comparability.

Examples of common US-GAAP concepts include `Assets`, `Liabilities`,
`StockholdersEquity`, `NetIncomeLoss`, `OperatingIncomeLoss`,
`GrossProfit` and `NetCashProvidedByUsedInOperatingActivities`. Revenue
and cash concepts may have multiple valid tags. Treat this as a
candidate mapping list, not a universal one-tag-per-metric rule.

Do not silently map a custom extension to a standard concept based only
on a similar label. Inspect definition, presentation relationships,
calculation relationships, dimensions and filing context; otherwise
escalate.

------------------------------------------------------------------------

# 5. High-Level Architecture

``` text
                         USER / REVIEWER
                                |
                                v
                       Streamlit Dashboard
                                |
                                v
                         FastAPI Backend
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
          Workflow Service                SEC Client
                 |                             |
                 v                             v
            LangGraph                    SEC EDGAR APIs
                 |                      Submissions / Company Facts
                 |                      Filing index / Inline XBRL
                 v                             |
         Persistent Checkpointer               v
                 |                       Filing Evidence Store
                 |
                 v
  +-----------------------------------------------+
  |              LANGGRAPH WORKFLOW               |
  |                                               |
  |  1. Retrieve filing                            |
  |  2. Extract structured facts                   |
  |  3. Parse/inspect Inline XBRL as needed         |
  |  4. Select metric facts by context              |
  |  5. Locate source evidence                      |
  |  6. Score extraction quality                    |
  |  7. Run deterministic validations              |
  |  8. Route: auto-pass or human review            |
  |  9. Interrupt and persist checkpoint            |
  | 10. Resume after reviewer decision              |
  | 11. Verify against SEC facts / reference set    |
  | 12. Generate report and audit events            |
  +-----------------------------------------------+
                 |
        +--------+---------+
        |                  |
        v                  v
    SQLite DB        Append-only audit events
  business records    + SHA-256 hash chain
  review decisions    + chain verification
```

## 5.1 Recommended technology stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Language                Python 3.11+            Main implementation

  API                     FastAPI                 Start, status and
                                                  review endpoints

  Workflow                LangGraph               Stateful conditional
                                                  workflow and interrupts

  Checkpoint              LangGraph SQLite        Persist workflow state
                          checkpointer            

  Business DB             SQLite                  Filings, facts,
                                                  metrics, validations
                                                  and reviews

  Frontend                Streamlit               Reviewer dashboard and
                                                  results

  SEC retrieval           `requests` or `httpx`   Official SEC JSON and
                                                  filing retrieval

  HTML parsing            `lxml`, BeautifulSoup   Filing document
                                                  inspection

  XBRL processing         Arelle                  Reuse established XBRL
                                                  processing capabilities

  Models                  Pydantic                Strict input/output
                                                  contracts

  Hashing                 `hashlib`               Tamper-evident audit
                                                  chain

  Testing                 pytest                  Unit, integration and
                                                  workflow tests

  Optional LLM            Configurable provider   Explain cited findings
                                                  only
  -----------------------------------------------------------------------

Use a separate business database and workflow checkpointer unless there
is a clear reason to combine them. Keep their responsibilities explicit.

------------------------------------------------------------------------

# 6. SEC Data Retrieval Design

## 6.1 Official endpoints

Use the official SEC EDGAR resources:

-   Submissions: `https://data.sec.gov/submissions/CIK##########.json`
-   Company Facts:
    `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
-   Company Concept:
    `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/ConceptName.json`
-   Filing archives:
    `https://www.sec.gov/Archives/edgar/data/{cik_without_leading_zeroes}/{accession_without_dashes}/`
-   Filing index: `{filing_archive_base}/index.json`

Use the SEC documentation to confirm current endpoint details before
implementation.

## 6.2 Request policy

-   No API key is normally required for the public SEC data APIs.
-   Send a descriptive User-Agent identifying the application and a
    monitored contact address.
-   Respect SEC fair-access guidance and the published request-rate
    limit.
-   Cache responses locally.
-   Implement timeout, retry with backoff and clear error messages.
-   Do not send concurrent bursts of requests.
-   Do not scrape the website as a substitute for available official
    APIs.
-   Do not commit contact details, tokens or secrets to source control.

## 6.3 Filing selection

Select the latest eligible 10-K using submissions metadata:

-   CIK.
-   Form type `10-K`.
-   Filing date.
-   Accession number.
-   Primary document.
-   Report period, when available.

Handle `10-K/A` explicitly. Do not automatically treat an amendment as a
complete replacement for every fact in the original filing. Show
original and amended versions separately and define the selected version
in the audit report.

## 6.4 Filing identity

Every workflow must be pinned to:

-   CIK.
-   Accession number.
-   Form type.
-   Filing date.
-   Report period.
-   Primary document URL.
-   Retrieval timestamp.
-   Content hash of downloaded source, where practical.

This prevents a later filing from silently changing the source of a
prior audit run.

------------------------------------------------------------------------

# 7. Extraction Engine

## 7.1 Hybrid extraction strategy

Use two complementary sources:

**Path A --- SEC Company Facts**

Useful for standard taxonomy facts aggregated at the filing-entity
level.

**Path B --- Original filing Inline XBRL / XBRL instance**

Needed for filing-specific facts, custom taxonomy extensions, dimensions
and more detailed contexts that may not be represented in Company Facts.

Do not assume Company Facts contains every fact in the filing. SEC
Company Facts has scope limitations, including its focus on non-custom
taxonomies and entity-wide facts.

## 7.2 Fact selection algorithm

For each canonical metric:

1.  Load candidate taxonomy concepts.
2.  Find candidate facts in the selected filing.
3.  Match accession number where available.
4.  Match annual form and target fiscal period.
5.  Validate start and end dates for duration facts.
6.  Validate instant date for balance-sheet facts.
7.  Validate unit and scale.
8.  Inspect dimensions and segment context.
9.  Resolve duplicate candidates using explicit, documented rules.
10. Preserve all candidates and the selection reason.
11. Escalate if multiple candidates remain ambiguous.

## 7.3 Duration versus instant

-   Income statement and cash flow metrics generally use duration
    contexts.
-   Balance sheet metrics generally use instant contexts.

Do not compare an instant fact with a duration fact.

For annual values, ensure the context covers the intended fiscal year
rather than a quarter or year-to-date interval. Fiscal year-end may
differ by company.

## 7.4 Unit and scale handling

Store the raw value and normalized value separately.

Example:

-   Raw fact: `352583`
-   Unit: USD
-   Filing display scale: USD millions
-   Display value: `$352.583 billion` only if the source context and
    scaling justify it.

Never infer scale from a visual table label without preserving the
original XBRL unit and source evidence.

## 7.5 Evidence record

Every extracted metric should include:

``` json
{
  "metric_id": "total_assets",
  "canonical_name": "Total Assets",
  "raw_value": 352583000000,
  "normalized_value": 352583000000,
  "unit": "USD",
  "taxonomy": "us-gaap",
  "concept": "Assets",
  "context_id": "example_context",
  "period_type": "instant",
  "period_start": null,
  "period_end": "2025-09-27",
  "fiscal_year": 2025,
  "fiscal_period": "FY",
  "form": "10-K",
  "accession_number": "example-accession",
  "source_url": "https://www.sec.gov/Archives/...",
  "evidence_locator": "Balance Sheet / Total Assets",
  "evidence_snippet": "Illustrative source excerpt",
  "selection_reason": "Matched filing, annual period, instant context and USD unit"
}
```

This is a schema example only. Do not use illustrative values as real
filing data.

------------------------------------------------------------------------

# 8. Confidence and Quality Scoring

## 8.1 Do not call confidence accuracy

The score represents extraction evidence quality, not the probability
that the company's reported financial statement is true.

Current transparent score (rubric v2):

``` text
Quality Score = 100 * (
    0.30 * source_reliability +
    0.15 * cross_source_agreement +
    0.20 * period_compatibility +
    0.10 * unit_dimensional_compatibility +
    0.25 * extraction_mapping_quality
)
```

Each raw factor is in the range 0 to 1. Persist and display its weight,
weighted contribution, evidence, and deduction reasons. Missing period or
dimensional evidence must not earn full points. A local SHA-256 match proves
consistency with the stored copy; it does not independently authenticate the
bytes against SEC. The source-reliability factor is capped below 1.0 until
independent source authenticity is established. These scores are deterministic
quality indicators, not calibrated probabilities.

## 8.2 Suggested routing

-   85--100: eligible for automatic pass only if all mandatory
    validations pass.
-   60--84: review if any ambiguity, warning or failed check exists.
-   Below 60: mandatory review.
-   Any wrong or ambiguous period/unit: mandatory review.
-   Any unresolved custom-tag mapping: mandatory review.
-   Any critical accounting validation failure: mandatory review.
-   Any material anomaly: flag for review, not automatic rejection.

These are starting thresholds. Calibrate them using the benchmark set.

## 8.3 Separate status dimensions

Display separate fields:

-   Extraction quality score.
-   Evidence status.
-   Context status.
-   Validation status.
-   Review status.

A single number must not hide a critical failure.

------------------------------------------------------------------------

# 9. Deterministic Validation Engine

Implement rules as independent, tested Python functions. Each rule
returns a structured `ValidationResult`.

## 9.1 Accounting equation

``` text
Assets ≈ Liabilities + Equity
```

Use a configurable tolerance:

``` text
absolute_difference = abs(assets - (liabilities + equity))
tolerance = max(absolute_tolerance, relative_tolerance * abs(assets))
passed = absolute_difference <= tolerance
```

Start with a configurable relative tolerance such as 0.5%, but make it
clear that this is a prototype threshold. Consider noncontrolling
interests, presentation differences and rounding. Do not assume every
reported equity line has identical scope.

## 9.2 Segment reconciliation

Only run when compatible segment facts and the reconciliation disclosure
are available.

``` text
Segment total
+ / - disclosed reconciliation items
≈ consolidated reported total
```

Do not simply add segment values and label any difference an error.
Consider intersegment eliminations, unallocated amounts and other
reconciliation items.

If required information is unavailable, return `NOT_APPLICABLE` or
`INSUFFICIENT_EVIDENCE`, not `PASS`.

## 9.3 Year-over-year variance

``` text
YoY Change (%) =
((current_value - prior_value) / abs(prior_value)) * 100
```

Handle zero prior values and sign changes explicitly.

A threshold such as 40% is configurable and is only an anomaly flag. It
is not proof of an error, misconduct or fraud.

## 9.4 Cross-statement checks

Where compatible facts exist, implement checks such as:

-   Net income versus cash flow statement reconciliation context.
-   Cash balance versus cash flow statement ending cash, after checking
    restricted cash and statement definitions.
-   Debt-related balance sheet values versus relevant note disclosures.
-   Revenue and segment reconciliation.

Do not add a check unless its accounting meaning and required context
are documented.

## 9.5 Validation result schema

``` json
{
  "rule_id": "balance_sheet_equation",
  "status": "PASS",
  "severity": "INFO",
  "metric_ids": ["total_assets", "total_liabilities", "equity"],
  "observed_difference": 1000000,
  "tolerance": 5000000,
  "explanation": "Difference is within configured tolerance.",
  "evidence_refs": ["fact_1", "fact_2", "fact_3"],
  "rule_version": "1.0"
}
```

Allowed statuses: `PASS`, `FAIL`, `WARNING`, `NOT_APPLICABLE`,
`INSUFFICIENT_EVIDENCE`.

------------------------------------------------------------------------

# 10. Agentic Workflow --- LangGraph

## 10.1 Workflow state

Use a typed state model containing:

-   `workflow_id`
-   `thread_id`
-   `company`
-   `cik`
-   `filing`
-   `facts`
-   `selected_metrics`
-   `evidence`
-   `quality_scores`
-   `validation_results`
-   `review_items`
-   `review_decisions`
-   `ground_truth_comparison`
-   `audit_event_ids`
-   `workflow_status`
-   `errors`

Keep state serializable. Avoid storing large raw filing documents in
graph state; store file paths or stable document references and keep
content in the evidence store.

## 10.2 Graph nodes

1.  `retrieve_filing`
2.  `fetch_company_facts`
3.  `load_filing_document`
4.  `extract_inline_xbrl`
5.  `select_metric_facts`
6.  `locate_evidence`
7.  `score_quality`
8.  `run_validations`
9.  `route_for_review`
10. `human_review_interrupt`
11. `apply_review_decision`
12. `rerun_affected_validations`
13. `compare_sec_facts`
14. `generate_report`
15. `append_audit_events`
16. `complete_workflow`

## 10.3 Conditional routing

-   All required facts selected, adequate quality and checks pass →
    verification.
-   Low quality, ambiguous context or failed critical check → human
    review.
-   Reviewer approves → record approval and continue.
-   Reviewer corrects → preserve original, store corrected value, rerun
    affected checks.
-   Reviewer rejects → mark unresolved or excluded; do not invent a
    replacement.
-   Missing source data → explicit error or insufficient-evidence
    status.

## 10.4 Interrupt and resume

Use LangGraph's documented `interrupt()` and `Command(resume=...)`
pattern with a persistent checkpointer.

Important implementation requirements:

-   Use a stable `thread_id` for a workflow.
-   Persist the graph state.
-   Resume the same thread after review.
-   Make side effects idempotent.
-   A node containing `interrupt()` can restart from its beginning when
    resumed. Do not place non-idempotent writes before the interrupt
    without safeguards.
-   Test process restart, not just a pause/resume in one Python process.
-   Use a review ID and idempotency key to prevent duplicate decisions.

Use the currently supported LangGraph SQLite checkpoint package and
follow its installed-version documentation. Verify imports and APIs with
a minimal checkpoint/resume test before implementing the full graph.

------------------------------------------------------------------------

# 11. Human Review Experience

## 11.1 Review queue

The dashboard should show:

-   Company and filing period.
-   Metric name.
-   Extracted value and unit.
-   XBRL taxonomy and concept.
-   Context and accession.
-   Quality score and factor breakdown.
-   Evidence link and excerpt.
-   Validation finding.
-   Escalation reason.

## 11.2 Reviewer actions

-   Approve.
-   Correct.
-   Reject / mark unresolved.
-   Add comment.

A correction must preserve:

-   Original value.
-   Corrected value.
-   Reviewer identity.
-   Timestamp.
-   Comment.
-   Evidence used.
-   Previous validation result.
-   New validation result.

## 11.3 Review safety

-   Never allow an LLM to approve or overwrite a financial value.
-   Require a reviewer identity field for the MVP.
-   Validate corrected values and units.
-   Do not permit a rejected metric to appear as verified.
-   Keep a clear distinction between company-reported facts and reviewer
    corrections.

------------------------------------------------------------------------

# 12. Database Design

Use SQLite for the hackathon MVP.

Recommended tables:

## 12.1 `companies`

-   `company_id` primary key
-   `cik` unique
-   `name`
-   `ticker`

## 12.2 `filings`

-   `filing_id` primary key
-   `company_id`
-   `accession_number`
-   `form_type`
-   `filing_date`
-   `period_end_date`
-   `primary_document_url`
-   `source_hash`
-   `retrieved_at`
-   Unique key on company and accession number

## 12.3 `facts`

-   `fact_id` primary key
-   `filing_id`
-   `taxonomy`
-   `concept`
-   `context_id`
-   `unit`
-   `raw_value`
-   `normalized_value`
-   `period_start`
-   `period_end`
-   `fiscal_year`
-   `fiscal_period`
-   `dimensions_json`
-   `source_locator`

## 12.4 `extracted_metrics`

-   `metric_id` primary key
-   `filing_id`
-   `canonical_metric`
-   `selected_fact_id`
-   `raw_value`
-   `final_value`
-   `unit`
-   `quality_score`
-   `evidence_url`
-   `evidence_snippet`
-   `status`
-   `mapping_version`

## 12.5 `validation_results`

-   `validation_id` primary key
-   `filing_id`
-   `rule_id`
-   `status`
-   `severity`
-   `details_json`
-   `rule_version`
-   `created_at`

## 12.6 `human_reviews`

-   `review_id` primary key
-   `metric_id`
-   `review_round`
-   `reviewer_id`
-   `decision`
-   `original_value`
-   `corrected_value`
-   `comment`
-   `created_at`
-   Unique key on metric and review round

## 12.7 `audit_events`

-   `event_id` primary key
-   `workflow_id`
-   `metric_id`
-   `event_type`
-   `actor`
-   `payload_json`
-   `previous_hash`
-   `event_hash`
-   `created_at`

## 12.8 `benchmark_results`

-   `benchmark_id` primary key
-   `filing_id`
-   `metric_name`
-   `expected_value`
-   `expected_unit`
-   `expected_period`
-   `predicted_value`
-   `result`
-   `reviewer_reference`
-   `test_case_id`

Store money values as integers in the smallest source unit or as
`Decimal`-compatible strings. Avoid binary floating-point for exact
financial comparisons.

------------------------------------------------------------------------

# 13. Tamper-Evident Audit Ledger

## 13.1 Hash chain

For each event:

``` python
event_hash = sha256(
    previous_hash + canonical_json(payload) + created_at
).hexdigest()
```

Use a canonical JSON serializer with stable key ordering and
well-defined number/string handling.

## 13.2 Requirements

-   Audit events are insert-only through a dedicated service.
-   No application update/delete endpoint for historical audit events.
-   Each new event references the previous event hash.
-   Chain verification recomputes every event hash in order.
-   A verification failure reports the first broken event.
-   Use database permissions and backups as additional safeguards.
-   Optionally sign periodic checkpoint hashes with a key stored outside
    the database.

Do not describe a local SQLite table as absolutely immutable. The
correct claim is **tamper-evident hash-chained audit history**.

------------------------------------------------------------------------

# 14. API Design

Suggested FastAPI routes:

  ------------------------------------------------------------------------------------------
  Method                  Endpoint                                   Purpose
  ----------------------- ------------------------------------------ -----------------------
  POST                    `/api/workflows`                           Start an audit workflow

  GET                     `/api/workflows/{workflow_id}`             Get workflow status

  GET                     `/api/workflows/{workflow_id}/metrics`     Get extracted metrics

  GET                     `/api/workflows/{workflow_id}/reviews`     Get review queue

  POST                    `/api/reviews/{review_id}/decision`        Approve, correct or
                                                                     reject

  GET                     `/api/workflows/{workflow_id}/report`      Get final report

  GET                     `/api/workflows/{workflow_id}/audit-log`   Get audit events

  GET                     `/api/audit/verify/{workflow_id}`          Verify hash chain

  GET                     `/api/health`                              Health check
  ------------------------------------------------------------------------------------------

Validate every request with Pydantic. Add clear error responses and
prevent duplicate review submissions with idempotency keys.

------------------------------------------------------------------------

# 15. Streamlit Dashboard Pages

## Page 1 --- Company Selection

-   Company name and ticker.
-   CIK.
-   Latest eligible 10-K.
-   Filing date and period.
-   Start audit button.

## Page 2 --- Extraction Overview

-   Metric cards.
-   Value and unit.
-   Fiscal period.
-   Taxonomy concept.
-   Quality score.
-   Evidence link.

## Page 3 --- Validation Dashboard

-   Accounting equation.
-   Segment reconciliation.
-   YoY variance.
-   Cross-statement checks.
-   Pass, fail, warning and insufficient-evidence statuses.

## Page 4 --- Human Review Queue

-   Flagged metrics.
-   Reason for escalation.
-   Original evidence.
-   Approve, correct or reject controls.
-   Reviewer comment.

## Page 5 --- Accuracy Report

-   Number of reference facts.
-   Exact matches.
-   Numeric mismatches.
-   Period mismatches.
-   Unit mismatches.
-   Unresolved cases.
-   Precision/recall for anomaly flags where labelled data exists.

## Page 6 --- Audit History

-   Chronological events.
-   Original and corrected values.
-   Reviewer.
-   Hash chain status.
-   Verify button.

Use a clean, professional financial-audit interface. Prioritise clarity
and evidence over decorative charts.

------------------------------------------------------------------------

# 16. Testing Strategy --- Mandatory

Testing is part of the product, not a final optional activity.

## 16.1 Test pyramid

### Unit tests

Test each small function independently:

-   CIK formatting.
-   Accession formatting.
-   Filing selection.
-   Annual context selection.
-   Instant versus duration validation.
-   Unit conversion.
-   Tag mapping.
-   Confidence component calculation.
-   Accounting equation.
-   Segment reconciliation.
-   YoY calculation.
-   Hash generation and verification.

### Integration tests

Test interactions between modules:

-   SEC submissions retrieval using saved fixtures.
-   Company Facts parsing.
-   Inline XBRL parsing.
-   Metric selection.
-   Evidence locator.
-   SQLite persistence.
-   LangGraph checkpoint persistence.
-   Review decision and resume.
-   Audit chain verification.

### End-to-end tests

Test the complete workflow:

1.  Select a company.
2.  Retrieve a filing.
3.  Extract facts.
4.  Run validation.
5.  Trigger review.
6.  Correct or approve a value.
7.  Resume workflow.
8.  Generate final report.
9.  Verify audit chain.

## 16.2 Essential test cases

  -----------------------------------------------------------------------
  ID                      Test                    Expected result
  ----------------------- ----------------------- -----------------------
  TC01                    Valid annual revenue    Correct fact selected
                          fact                    

  TC02                    Quarterly fact appears  Annual fact selected
                          alongside annual fact   

  TC03                    Wrong period            Rejected or escalated

  TC04                    USD and USD millions    Unit mismatch detected
                          mixed                   

  TC05                    Custom extension tag    Mapped with evidence or
                                                  escalated

  TC06                    Multiple candidate      Ambiguity exposed
                          concepts                

  TC07                    Instant fact used for   Context mismatch
                          duration metric         detected

  TC08                    Balance-sheet equation  PASS
                          within tolerance        

  TC09                    Balance-sheet equation  FAIL / review
                          outside tolerance       

  TC10                    Segment elimination     Reconciliation handled
                          exists                  

  TC11                    Segment data            NOT_APPLICABLE /
                          unavailable             insufficient evidence

  TC12                    Revenue change exceeds  WARNING, not fraud
                          threshold               claim

  TC13                    Prior-year value is     No division-by-zero
                          zero                    failure

  TC14                    Filing amendment exists Versions preserved

  TC15                    Reviewer corrects a     Original and correction
                          value                   retained

  TC16                    Same review submitted   Duplicate prevented
                          twice                   

  TC17                    Process restarts while  Workflow resumes
                          review pending          

  TC18                    Audit event modified    Hash verification fails

  TC19                    SEC request times out   Retry/fallback works

  TC20                    Filing contains no      Explicit missing-data
                          expected metric         status
  -----------------------------------------------------------------------

## 16.3 Benchmark design

Start with five companies and two annual filings per company if time
allows.

Create a manually verified reference sample for each selected metric. A
reference record must identify the exact filing, accession, concept,
context, unit, period, source URL, exact evidence locator and verification
method. A boolean reviewer flag or free-text statement/page citation is a
claim, not independent evidence; disclose incomplete provenance in the
benchmark report.

Compare methods only when each has an executable extraction implementation:

-   Baseline A: simple candidate-tag lookup.
-   Baseline B: LLM-only extraction from selected filing text.
-   FilingGuard: hybrid XBRL, context-aware selection and deterministic
    validation.

Use the same filings and reference facts for all methods. Never derive a
baseline prediction from the expected reference value. Mark unavailable
methods as not evaluated and exclude those cases from accuracy denominators;
keep missing predictions from an evaluated method as failures. Count
evidence support only when a selected prediction has a matching source
locator linked to the locally hash-verified filing.

Report:

-   Exact value match rate.
-   Period selection accuracy.
-   Unit accuracy.
-   Evidence support rate.
-   Custom-tag handling rate.
-   Anomaly precision and recall.
-   False-positive rate.
-   Review escalation rate.
-   Workflow recovery success.

Do not invent baseline results. Run the tests and report actual results,
including failures.

## 16.4 Example pytest commands

``` bash
pytest -q
pytest tests/unit -q
pytest tests/integration -q
pytest tests/workflow -q
pytest --cov=app --cov-report=term-missing
```

Set a realistic coverage target for critical financial logic, such as
85% or higher, but prioritise meaningful assertions over coverage
percentage.

------------------------------------------------------------------------

# 17. Recommended Project Folder Structure

``` text
filingguard-ai/
│
├── README.md
├── implementation.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
│
├── app/
│   ├── __init__.py
│   │
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   ├── workflows.py
│   │   │   ├── metrics.py
│   │   │   ├── reviews.py
│   │   │   ├── reports.py
│   │   │   └── audit.py
│   │   └── schemas/
│   │       ├── workflow.py
│   │       ├── metric.py
│   │       ├── review.py
│   │       └── validation.py
│   │
│   ├── sec/
│   │   ├── client.py
│   │   ├── submissions.py
│   │   ├── company_facts.py
│   │   ├── filing_index.py
│   │   ├── filing_download.py
│   │   └── cache.py
│   │
│   ├── extraction/
│   │   ├── xbrl_parser.py
│   │   ├── arelle_runner.py
│   │   ├── taxonomy_mapping.py
│   │   ├── context_selector.py
│   │   ├── unit_normalizer.py
│   │   ├── metric_extractor.py
│   │   └── evidence_locator.py
│   │
│   ├── validation/
│   │   ├── engine.py
│   │   ├── accounting_equation.py
│   │   ├── segment_reconciliation.py
│   │   ├── yoy_analysis.py
│   │   └── cross_statement.py
│   │
│   ├── scoring/
│   │   ├── quality_score.py
│   │   └── escalation.py
│   │
│   ├── workflow/
│   │   ├── state.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   ├── checkpointer.py
│   │   └── resume.py
│   │
│   ├── review/
│   │   ├── service.py
│   │   └── idempotency.py
│   │
│   ├── audit/
│   │   ├── ledger.py
│   │   ├── hashing.py
│   │   └── verification.py
│   │
│   ├── benchmark/
│   │   ├── evaluator.py
│   │   ├── metrics.py
│   │   └── reference_loader.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── repositories/
│   │
│   └── services/
│       ├── report_service.py
│       └── workflow_service.py
│
├── dashboard/
│   ├── Home.py
│   ├── pages/
│   │   ├── 1_Company_Selection.py
│   │   ├── 2_Extraction_Results.py
│   │   ├── 3_Validation.py
│   │   ├── 4_Human_Review.py
│   │   ├── 5_Accuracy_Report.py
│   │   └── 6_Audit_History.py
│   └── components/
│
├── config/
│   ├── companies.json
│   ├── metric_mappings.json
│   ├── validation_rules.json
│   └── scoring_config.json
│
├── data/
│   ├── cache/
│   ├── filings/
│   ├── fixtures/
│   ├── reference/
│   └── database/
│
├── scripts/
│   ├── preload_demo_data.py
│   ├── verify_audit_chain.py
│   └── run_benchmark.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── workflow/
│   ├── api/
│   ├── end_to_end/
│   └── fixtures/
│
└── docs/
    ├── architecture.md
    ├── competitor_analysis.md
    ├── benchmark_methodology.md
    ├── demo_script.md
    └── known_limitations.md
```

Create only the folders and modules needed for the current phase. Avoid
generating dozens of empty files before a working vertical slice exists.

------------------------------------------------------------------------

# 18. Environment Setup

## 18.1 Requirements

-   Python 3.11 or compatible version supported by chosen package
    releases.
-   Git.
-   VS Code or another Python IDE.
-   Internet access for SEC retrieval during setup.
-   A valid descriptive SEC User-Agent contact.
-   Optional LLM API key; the core numeric pipeline must work without
    one.

## 18.2 Windows PowerShell setup

``` powershell
mkdir filingguard-ai
cd filingguard-ai

python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
```

Create a dependency file and install pinned, compatible versions after
checking the current official documentation.

Core package candidates:

``` text
fastapi
uvicorn[standard]
streamlit
langgraph
langgraph-checkpoint-sqlite
langchain-core
pydantic
requests
httpx
beautifulsoup4
lxml
pandas
pytest
pytest-cov
python-dotenv
```

Arelle can be installed using its current official distribution
instructions. Verify command-line and Python integration in a small
proof of concept before coupling it to the full application.

## 18.3 Environment variables

`.env.example`:

``` env
APP_ENV=development
DATABASE_URL=sqlite:///./data/database/filingguard.db
SEC_USER_AGENT=FilingGuardAI/1.0 contact@example.com
SEC_REQUEST_TIMEOUT=30
SEC_CACHE_ENABLED=true
SEC_CACHE_TTL_HOURS=24
REVIEWER_ID=demo_reviewer
LLM_ENABLED=false
LLM_API_KEY=
```

Replace the example contact with a real monitored contact before making
SEC requests. Never commit `.env`.

------------------------------------------------------------------------

# 19. Micro-Phased Development Plan

Each phase must end with a working output and tests. Do not move forward
while the current phase is broken.

## Phase 0 --- Understand and freeze requirements

Tasks: 1. Read the problem statement carefully. 2. Record mandatory
judging requirements. 3. Confirm the exact expected input and output. 4.
Finalise the initial 10-K-only scope. 5. Create acceptance criteria. 6.
Record out-of-scope features.

Deliverables: - `implementation.md` - `docs/architecture.md` - Feature
checklist

Exit test: - Every mandatory requirement maps to a module and a test.

## Phase 1 --- Repository and environment

Tasks: 1. Create Git repository. 2. Create virtual environment. 3. Add
dependencies. 4. Add `.env.example`. 5. Add `.gitignore`. 6. Create
FastAPI health route. 7. Create Streamlit landing page. 8. Add pytest
configuration.

Deliverables: - Running API. - Running dashboard. - First passing test.

Exit test:

``` bash
uvicorn app.main:app --reload
streamlit run dashboard/Home.py
pytest -q
```

## Phase 2 --- SEC retrieval

Tasks: 1. Implement CIK normalisation. 2. Implement SEC request client.
3. Set descriptive User-Agent. 4. Add timeout and retry. 5. Add local
response cache. 6. Fetch submissions JSON. 7. Select latest eligible
10-K. 8. Retrieve filing index. 9. Resolve primary document URL. 10.
Save filing metadata.

Deliverables: - Real company filing metadata. - Cached filing source. -
Retrieval error handling.

Exit tests: - Valid CIK works. - Invalid CIK returns clear error. - No
eligible 10-K returns explicit status. - Repeat request uses cache. -
SEC outage does not crash the application.

## Phase 3 --- Company Facts extraction

Tasks: 1. Retrieve Company Facts JSON. 2. Parse candidate metric
concepts. 3. Filter facts by accession where available. 4. Select fiscal
year and annual context. 5. Validate units. 6. Separate instant and
duration facts. 7. Preserve all candidate facts. 8. Store selected facts
and selection explanation.

Deliverables: - At least eight metrics for one filing. - Context-aware
fact records.

Exit tests: - Quarterly fact cannot silently replace annual fact. - USD
and USD millions are distinguished. - Missing metric is not
fabricated. - Duplicate candidates are exposed or resolved by documented
rules.

## Phase 4 --- Original filing and Inline XBRL

Tasks: 1. Retrieve original filing document. 2. Inspect Inline XBRL
structure. 3. Prototype Arelle processing. 4. Parse contexts and units.
5. Inspect custom taxonomy concepts. 6. Inspect dimensional facts. 7.
Link parsed facts to filing source locations. 8. Preserve source
document hash.

Deliverables: - Filing-level fact extraction. - Custom-tag and
dimensional fact inspection.

Exit tests: - A custom fact can be preserved. - A dimensioned fact is
not incorrectly treated as entity-wide. - Evidence link resolves to the
correct filing.

## Phase 5 --- Semantic mapping and context selector

Tasks: 1. Create canonical metric mapping. 2. Add candidate standard
concepts. 3. Add custom extension review flow. 4. Validate concept
meaning and unit. 5. Validate duration/instant type. 6. Validate fiscal
period. 7. Detect ambiguous candidates. 8. Store mapping version and
reason.

Deliverables: - Reusable metric selection engine.

Exit tests: - Correct annual fact selected. - Wrong period escalated. -
Ambiguous concept escalated. - Mapping decision is reproducible.

## Phase 6 --- Evidence and confidence

Tasks: 1. Create evidence record schema. 2. Link each selected fact to
its source. 3. Capture context and accession metadata. 4. Implement
quality score components. 5. Show factor-level score explanations. 6.
Separate quality score from validation status. 7. Configure review
thresholds.

Deliverables: - Evidence-backed metric records. - Transparent quality
score.

Exit tests: - Missing evidence reduces quality. - Wrong period is not
hidden by a high aggregate score. - Score calculation is deterministic.

## Phase 7 --- Financial validation engine

Tasks: 1. Implement accounting equation. 2. Add configurable tolerances.
3. Implement YoY calculations. 4. Handle zero and negative prior values.
5. Implement segment reconciliation only with appropriate data. 6. Add
selected cross-statement checks. 7. Produce structured validation
results. 8. Add rule versioning.

Deliverables: - Three validation families at minimum. - Explanation for
every warning and failure.

Exit tests: - Valid example passes. - Invalid example fails. - Missing
inputs return insufficient evidence. - Anomaly is not labelled fraud.

## Phase 8 --- LangGraph workflow

Tasks: 1. Define typed workflow state. 2. Implement retrieval node. 3.
Implement extraction node. 4. Implement scoring and validation nodes. 5.
Add conditional routing. 6. Add review interrupt. 7. Configure SQLite
checkpoint persistence. 8. Implement stable thread ID. 9. Add resume
handler. 10. Add idempotent side-effect handling.

Deliverables: - Workflow runs from start to review. - Workflow resumes
after reviewer input.

Exit tests: - Low-quality item interrupts. - Valid item follows
auto-pass route. - Process restart does not lose pending review. -
Duplicate resume does not duplicate review or audit events.

## Phase 9 --- Human review and API

Tasks: 1. Implement workflow start endpoint. 2. Implement status and
metrics endpoints. 3. Implement review queue. 4. Implement
approve/correct/reject. 5. Validate reviewer input. 6. Add idempotency
key. 7. Resume LangGraph with decision. 8. Persist original and
corrected values. 9. Rerun affected validations.

Deliverables: - Functional human review loop.

Exit tests: - Approval is recorded. - Correction preserves original
value. - Rejection remains unresolved. - Invalid correction is
rejected. - Duplicate review is prevented.

## Phase 10 --- Audit ledger

Tasks: 1. Implement canonical JSON. 2. Implement hash calculation. 3.
Implement insert-only audit service. 4. Add event ordering. 5. Add chain
verification. 6. Add tamper test. 7. Add optional signed checkpoint
export.

Deliverables: - Verifiable audit history.

Exit tests: - Valid chain returns VALID. - Modified payload returns
TAMPERED. - Deleted/reordered event is detected. - Review event includes
decision provenance.

## Phase 11 --- Benchmark and final verification

Tasks: 1. Create reference fact dataset with source-level provenance. 2.
Independently verify each reference record against its filing. 3. Run only
executable baselines. 4. Mark unavailable methods as not evaluated. 5.
Run FilingGuard against locally available facts and report missing cases. 6.
Compare values, periods, units and traceable evidence. 7. Measure anomaly
precision and recall only when the labeled sample supports it. 8. Record
failures, provenance gaps and unresolved cases. 9. Generate benchmark report.

Deliverables: - Reproducible benchmark results. - Known limitations.

Exit tests: - All results link to test cases. - No fabricated accuracy
numbers. - Same input and configuration reproduce the same deterministic
results.

## Phase 12 --- Dashboard and demo

Tasks: 1. Complete company selection. 2. Display extraction table. 3.
Display validation explanations. 4. Implement reviewer queue. 5. Display
resume status. 6. Display accuracy report. 7. Display audit log and
verification. 8. Preload cached demo filings. 9. Test without internet.
10. Prepare short demo script and backup screenshots.

Deliverables: - End-to-end demonstrable MVP.

------------------------------------------------------------------------

# 20. 24-Hour Execution Schedule

  Hours    Work                               Required output
  -------- ---------------------------------- --------------------------------
  0--2     Setup and data contracts           Running skeleton
  2--5     SEC retrieval                      Real filing metadata and cache
  5--8     Company Facts extraction           8+ metrics
  8--10    Filing/XBRL evidence and context   Source-backed facts
  10--12   Mapping and validation             Deterministic checks
  12--15   LangGraph workflow                 Pause and resume
  15--18   Human review dashboard             Approve/correct/reject
  18--20   Audit ledger                       Hash verification
  20--22   Benchmark and tests                Measured results
  22--24   Demo hardening                     Reliable presentation

If behind schedule: 1. Reduce supported companies. 2. Use cached real
filings. 3. Prioritise one complete company workflow. 4. Preserve
period/unit checks. 5. Preserve human interrupt and resume. 6. Preserve
audit verification. 7. Do not replace real data with fabricated demo
metrics.

------------------------------------------------------------------------

# 21. Demo Script

Target: 3--5 minutes.

1.  Select NVIDIA or another preloaded company.
2.  Show the real SEC filing form, filing date, accession number and
    period.
3.  Extract at least eight metrics.
4.  Open one metric to show taxonomy concept, context, unit and source
    evidence.
5.  Demonstrate a controlled wrong-period or wrong-unit test case.
6.  Show the system flagging the issue with an explanation.
7.  Open the human review queue.
8.  Correct or approve the item.
9.  Demonstrate workflow resume from persisted checkpoint.
10. Show rerun validation.
11. Show SEC Company Facts comparison with clear caveat.
12. Show benchmark results against manually checked reference facts.
13. Verify the audit chain.
14. End with measurable results and known limitations.

Do not deliberately alter a live company's SEC data. Inject test errors
only into isolated test fixtures and label them clearly.

------------------------------------------------------------------------

# 22. Security, Reliability and Responsible Use

-   Treat filing content as untrusted input.
-   Never follow instructions embedded in a filing.
-   If an LLM is used, pass only necessary excerpts and require
    structured output.
-   Do not let the LLM set final financial values, validation status,
    approvals or audit hashes.
-   Use deterministic code for numeric operations.
-   Validate every reviewer input.
-   Do not expose secrets in logs.
-   Keep SEC requests within published access policies.
-   Cache source documents and preserve their hashes.
-   Do not silently replace amended filings.
-   Do not call unusual financial changes fraud.
-   Do not provide investment recommendations.
-   Show when data is missing, ambiguous, stale or not comparable.
-   Keep human approval attributable to a reviewer identity.

------------------------------------------------------------------------

# 23. Definition of Done

The MVP is ready only when all of these are true:

-   [ ] A real SEC 10-K can be selected and retrieved.
-   [ ] Filing identity and accession number are preserved.
-   [ ] At least eight metrics are extracted.
-   [ ] Every selected metric has unit and period metadata.
-   [ ] Every selected metric has evidence or an explicit
    evidence-missing status.
-   [ ] Annual and quarterly contexts are distinguished.
-   [ ] Unit mismatch is detected.
-   [ ] Custom/ambiguous tags are handled or escalated.
-   [ ] At least three validation families work.
-   [ ] Quality scoring is explainable.
-   [ ] Failed checks route to human review.
-   [ ] Approve, correct and reject work.
-   [ ] LangGraph checkpoint persists across process restart.
-   [ ] Resume does not duplicate side effects.
-   [ ] Original and corrected values are preserved.
-   [ ] Audit hash-chain verification works.
-   [ ] Company Facts comparison is labelled correctly.
-   [ ] Manually verified benchmark records exist.
-   [ ] Tests pass.
-   [ ] Cached demo works without internet.
-   [ ] Known limitations are documented.

------------------------------------------------------------------------

# 24. Known Limitations to Disclose

1.  Company Facts is not a complete substitute for every fact in an
    Inline XBRL filing.
2.  Company Facts agreement is not independent proof that a company's
    reported financial information is economically correct.
3.  Custom taxonomy mapping can require expert review.
4.  Segment reconciliation is not always possible from a simple sum.
5.  Accounting checks can flag legitimate differences caused by
    presentation, scope or accounting policy.
6.  A YoY anomaly is not evidence of fraud.
7.  A confidence score is not a calibrated probability unless tested and
    calibrated.
8.  A local hash chain is tamper-evident, not absolutely immutable.
9.  The prototype is not a statutory audit tool or a substitute for
    professional judgment.
10. The MVP focuses on US SEC 10-K filings, not all jurisdictions and
    filing types.

------------------------------------------------------------------------

# 25. MASTER PROMPT FOR AI CODING AGENT

Copy the following prompt into your coding agent (Codex, Claude Code,
Cursor, Windsurf or another repository-aware coding tool) after placing
this `implementation.md` at the repository root.

------------------------------------------------------------------------

## MASTER BUILD PROMPT

You are a senior Python architect, SEC EDGAR/XBRL engineer, financial
data validation specialist, LangGraph workflow engineer, QA engineer and
pragmatic hackathon technical lead.

Your task is to build **FilingGuard AI --- Evidence-First Financial
Filing Auditor**, following the repository's `implementation.md` as the
primary project specification.

### A. First: inspect and understand

1.  Read the complete `implementation.md`.
2.  Inspect the existing repository, files, installed dependencies and
    current implementation.
3.  Do not overwrite working code without understanding it.
4.  Identify completed, incomplete and missing phases.
5.  Create or update a concise `docs/build_status.md`.
6.  Present a proposed implementation sequence with dependencies and
    risks.
7.  If the repository is empty, initialise the project according to the
    folder structure in the specification.
8.  Do not ask the user to repeat requirements already stated in
    `implementation.md`.

### B. Non-negotiable engineering principles

-   Use real SEC EDGAR data for real filing demonstrations.
-   Do not invent financial facts, filings, source URLs or benchmark
    results.
-   Preserve CIK, accession number, filing date, period, taxonomy,
    concept, context and unit.
-   Treat Company Facts as a structured comparison source, not
    independent economic ground truth.
-   Use original Inline XBRL/Arelle processing where Company Facts is
    insufficient.
-   Use Python for all numeric calculations and financial validation.
-   LLMs may explain cited evidence, but must never authoritatively set
    financial values, approvals or validation outcomes.
-   Do not claim fraud based on a variance or anomaly.
-   Never silently substitute a quarterly value for an annual value.
-   Never silently mix currencies or scales.
-   Do not silently map an ambiguous custom extension.
-   Preserve original and corrected values.
-   Make all external side effects idempotent.
-   Keep secrets in environment variables.
-   Follow SEC request policies and cache retrieved data.
-   Build a working vertical slice before adding optional features.

### C. Development must be micro-phased

Work in the order specified in `implementation.md`.

For every phase:

1.  State the phase objective.
2.  Identify exact files to create or modify.
3.  Explain the implementation approach briefly.
4.  Implement the smallest complete working increment.
5.  Add or update tests immediately.
6.  Run relevant tests and static checks.
7.  Inspect errors and fix them.
8.  Summarise files changed and commands executed.
9.  Record known issues and the next phase.
10. Update `docs/build_status.md`.

Do not mark a phase complete unless its exit tests pass.

### D. Architecture requirements

Implement separate modules for:

-   SEC retrieval and caching.
-   Filing selection and identity.
-   Company Facts parsing.
-   Inline XBRL/Arelle processing.
-   Canonical metric mapping.
-   Period/context selection.
-   Unit normalisation.
-   Evidence location.
-   Quality scoring.
-   Deterministic financial validation.
-   LangGraph workflow and checkpointing.
-   Human review.
-   Audit hash chain.
-   Benchmark evaluation.
-   FastAPI.
-   Streamlit dashboard.

Avoid a single oversized Python file.

### E. Extraction requirements

For every extracted fact preserve:

-   Canonical metric.
-   Raw and normalised value.
-   Unit.
-   Taxonomy and concept.
-   Context ID.
-   Instant or duration type.
-   Start and end dates.
-   Fiscal year and period.
-   Accession number.
-   Filing form.
-   Dimensions.
-   Evidence URL and locator.
-   Selection explanation.
-   Mapping version.

If a fact cannot be selected safely, mark it ambiguous or missing and
escalate. Do not guess.

### F. Validation requirements

Implement tested, deterministic rules for:

1.  Accounting equation with documented tolerance.
2.  Segment reconciliation with disclosed eliminations and adjustments.
3.  Year-over-year variance with safe handling of zero and negative
    prior values.
4.  Additional cross-statement checks only when compatible facts and
    accounting definitions exist.

Return structured validation results. Missing information must not
become PASS.

### G. Workflow requirements

Use LangGraph for:

-   Stateful nodes.
-   Conditional routing.
-   Human interrupt.
-   Persistent SQLite checkpoint.
-   Resume with the same stable thread ID.
-   Idempotent side effects.
-   Recovery after process restart.

Write a small checkpoint/resume proof of concept before integrating the
complete workflow. Follow the installed LangGraph version's
documentation. Do not assume an old import path or API.

### H. Human review requirements

The reviewer must see the extracted value, evidence, taxonomy, context,
period, unit, quality factors and validation explanation.

Support approve, correct and reject.

A correction must: - Preserve the original. - Store the corrected value
separately. - Require reviewer identity and comment. - Trigger affected
validations again. - Append an audit event. - Avoid duplicate
application if submitted twice.

### I. Testing requirements

Create and maintain:

-   Unit tests.
-   Integration tests.
-   Workflow checkpoint/resume tests.
-   API tests.
-   End-to-end tests.
-   SEC response fixtures.
-   Controlled incorrect-data fixtures.
-   Benchmark reference records.

At minimum, test wrong period, wrong unit, custom tag ambiguity,
instant/duration mismatch, missing evidence, accounting equation
failure, segment reconciliation, zero prior-year value, duplicate
review, process restart and audit tampering.

Never write tests that merely assert that a function ran. Assert
meaningful expected values, statuses and side effects.

Run:

``` bash
pytest -q
pytest --cov=app --cov-report=term-missing
```

Fix failures before moving on.

### J. Benchmark requirements

Compare:

-   Simple tag lookup baseline.
-   LLM-only baseline, if available.
-   FilingGuard hybrid pipeline.

Use identical filings and manually verified reference facts.

Report actual: - Value accuracy. - Period accuracy. - Unit accuracy. -
Evidence support. - Custom-tag handling. - Anomaly precision/recall. -
False-positive rate. - Review escalation rate. - Resume reliability.

Do not fabricate benchmark outcomes. Clearly label small-sample results
as prototype results.

### K. User interface requirements

Build a clear financial audit dashboard with:

1.  Company and filing selection.
2.  Metric extraction table.
3.  Evidence details.
4.  Validation dashboard.
5.  Human review queue.
6.  Final accuracy report.
7.  Audit history and verification.

Do not prioritise visual polish over correctness and evidence
traceability.

### L. Reliability and hackathon constraints

-   Target a working end-to-end MVP within 24 hours.
-   Prioritise one company workflow before five-company coverage.
-   Cache real filing data.
-   Provide offline demo mode.
-   Use sample fixtures only when clearly labelled.
-   Do not build cloud deployment, complex RBAC or unnecessary agent
    features before mandatory requirements pass.
-   Keep README setup instructions accurate.
-   Include known limitations.

### M. Completion report after each phase

At the end of each phase, report:

1.  What was implemented.
2.  Files created or modified.
3.  Tests executed.
4.  Test results.
5.  Bugs discovered and fixed.
6.  Remaining limitations.
7.  Exact next development step.

### N. Final completion criteria

Do not declare the project complete until the Definition of Done
checklist in `implementation.md` has been evaluated.

The final project must demonstrate:

-   Real SEC filing retrieval.
-   Evidence-linked, context-aware extraction.
-   Deterministic financial validation.
-   Explainable escalation.
-   Human review.
-   Persistent workflow interruption and resume.
-   SEC structured-data comparison.
-   Manually verified benchmark results.
-   Tamper-evident audit history.
-   Passing automated tests.
-   A reliable demo.

**Start now with repository inspection and Phase 0. Do not generate the
entire application in one response. Build, test and verify each small
phase before continuing.**

------------------------------------------------------------------------

# 26. Final Instruction to the Team

The most important engineering objective is not to finish every planned
feature. It is to demonstrate one complete, trustworthy workflow:

**Real SEC filing → correct context-aware extraction → evidence →
deterministic validation → human review → checkpoint resume → final
verification → tamper-evident audit record.**

If this vertical slice works reliably and its accuracy is measured
honestly, it will provide a much stronger hackathon demonstration than a
large but unreliable collection of AI features.
