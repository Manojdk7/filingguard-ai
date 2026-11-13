# FilingGuard AI – Build Status

## Overview
- **Project**: FilingGuard AI
- **Description**: Deterministic Financial Filing Integrity Engine
- **Current Phase**: Phase 12 – Dashboard & Demo Completed (Project 100% Complete)

---

## Implemented Functionality

### Phase 1: Repository & Environment Baseline
- Virtual environment (`.venv`) initialized and configured with Python 3.13.2.
- Core dependencies installed: FastAPI, Uvicorn, Streamlit, LangGraph, Pydantic, Requests, HTTPX, BeautifulSoup4, LXML, Pandas, Pytest.
- Configuration management in `app/config.py` loading `.env` and `.env.example`.
- SQLite database connection & transaction provider in `app/database/connection.py`.
- Health check endpoints (`/` and `/health`) in `app/main.py` and `app/api/routes/health.py`.
- Streamlit Home landing dashboard in `dashboard/Home.py`.
- Base unit and API health tests.

### Phase 2: SEC Retrieval Engine
- **CIK Normalization (`app/sec/client.py`)**: Validates CIK formats (normalizes to 10 digits with leading zeroes), rejects invalid formats with `InvalidCIKError`.
- **SEC HTTP Client & Rate Limiter (`app/sec/client.py`)**: Respects SEC fair-access policies (<10 req/s), configurable timeout and exponential backoff retry for transient network/server codes (`429`, `5xx`).
- **Local Response Cache (`app/sec/cache.py`)**: SHA-256 hashed filesystem cache under `data/cache/` with configurable TTL and auto-purge of corrupt files.
- **Submissions & 10-K Selection (`app/sec/submissions.py`)**: Fetches submissions JSON, extracts latest eligible `10-K`, isolates `10-K/A` amendments.
- **Filing Index & Document URL Resolver (`app/sec/filing_index.py`)**: Maps EDGAR archive directories (`/Archives/edgar/data/...`), validates primary document accession ownership.
- **Database Persistence (`app/database/models.py`, `app/database/repositories/filing_repository.py`)**: SQLite `filings` table storing filing metadata with idempotent update on conflicts.

### Phase 3: Company Facts Extraction Engine
- **Company Facts Retrieval (`app/sec/company_facts.py`)**: Fetches official SEC Company Facts JSON (`/api/xbrl/companyfacts/CIK{cik}.json`), validates payload structure with `MalformedCompanyFactsError`.
- **Taxonomy Mapping Manager (`app/extraction/taxonomy_mapping.py`, `config/metric_mappings.json`)**: Configured 10 canonical financial metrics mapped to prioritized standard US-GAAP concepts.
- **Deterministic Context Selector (`app/extraction/context_selector.py`)**: Enforces exact accession matching, ~365-day full annual duration (preventing quarterly replacement), instant vs. duration separation, and exposes ambiguous candidate facts without guessing.
- **Fact Database Persistence (`app/database/models.py`, `app/database/repositories/fact_repository.py`)**: SQLite table `company_facts` with indexes on `(accession_number, metric_id)` and `(cik, fiscal_year)`.
- **Metric Extraction Coordinator (`app/extraction/metric_extractor.py`)**: Orchestrates company facts retrieval, filing binding, and extraction report generation.

### Phase 4: Original Filing & Inline XBRL Extraction
- **Original Filing Downloader (`app/sec/filing_download.py`)**:
  - Downloads primary filing HTML / Inline XBRL documents directly from official SEC archive URLs.
  - Caches documents locally in `data/filings/{accession_number}/{primary_document}` to prevent redundant SEC downloads.
  - Computes SHA-256 cryptographic integrity hash and file size for every downloaded document.
  - Error handling: validates HTTP status codes and rejects invalid protocols with `SECRequestError` / `ValueError`.
- **Arelle Isolated Runner (`app/extraction/arelle_runner.py`)**:
  - Integrated `arelle-release` (v2.47.4).
  - Sandboxed configuration: overrides `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` to `data/cache/arelle/` to isolate runtime state and eliminate permission conflicts.
  - Non-crashing fault tolerance: catches parsing errors and returns structured `ArelleRunResult`.
- **Inline XBRL Parser (`app/extraction/xbrl_parser.py`)**:
  - Parses Inline XBRL elements: concepts, namespaces, raw values, units, contexts, instant vs. duration periods.
  - Extracts raw value text and cleans punctuation ($ ,) to avoid Inline XBRL type coercion limitations.
  - Traverses XML context tree directly to extract exact period dates (preventing Arelle end-of-day +1 offset).
  - Separates entity-wide facts from dimensional segment facts (`hasSegment`, `qnameDims` mapping dimension axes to members).
  - Identifies company-specific custom taxonomy concepts (e.g. `http://www.apple.com/20260926`).
  - Evidence linking: binds each fact to `accession_number`, `source_url`, `source_doc_hash`, and source line locators (`source_locator`).
- **Database Persistence (`app/database/models.py`, `app/database/repositories/`)**:
  - `downloaded_documents`: stores primary document paths, sizes, retrieval timestamps, and SHA-256 hashes (`DocumentRepository`).
  - `xbrl_parsed_facts`: stores parsed XBRL facts, units, duration/instant bounds, `is_segment`, `dimensions_json`, and evidence links (`XBRLFactRepository`).

### Phase 5: Semantic Mapping & Cross-Source Reconciliation Engine
- **Custom Taxonomy Semantic Mapper (`app/extraction/semantic_mapping.py`)**:
  - Conservative, deterministic heuristic mapping of company-specific extension concepts against standard US-GAAP definitions.
  - Requires statement type compatibility, period type match (instant vs duration), unit compatibility (USD), and explicit consolidated-only validation (dimensional segment facts are blocked from mapping to consolidated canonical metrics).
  - Conservative classification outputs: `candidate_for_review` (never silently accepted as authoritative) or `unresolved`.
- **Segment Classifier (`app/extraction/segment_classifier.py`)**:
  - Isolates dimensional facts from consolidated financial facts.
  - Classifies facts by dimension axis and member without arbitrary aggregation.
  - Validates that segment facts cannot overwrite or be compared against consolidated metric totals.
- **Cross-Source Reconciliation Engine (`app/extraction/reconciliation_service.py`)**:
  - Compares Path A (SEC Company Facts) against Path B (Original Inline XBRL facts).
  - Categorizes comparisons into 11 deterministic audit statuses:
    - `exact_match`, `value_mismatch`, `period_mismatch`, `unit_mismatch`, `segment_vs_consolidated_mismatch`, `missing_in_company_facts`, `missing_in_ixbrl`, `missing_in_both`, `not_comparable`, `context_mismatch`, `ambiguous_mapping`.
- **Canonical Taxonomy Definitions (`config/metric_mappings.json`, `app/extraction/taxonomy_mapping.py`)**:
  - Enriched metric mappings with `is_consolidated_only` flags across all 10 canonical metrics.
  - Added reverse lookup capability (`find_metric_by_concept`) to resolve concepts back to canonical definitions.
- **Database Persistence (`app/database/models.py`, `app/database/repositories/reconciliation_repository.py`)**:
  - `cross_source_reconciliations` and `custom_concept_candidates` persistence with idempotent replacement.

### Phase 6: Evidence & Confidence Scoring Engine
- **Deterministic 5-Factor Scoring Formulation (`app/scoring/quality_score.py`, `config/scoring_config.json`)**:
  - Normalized confidence score $[0.0, 1.0]$ derived from $F_{\text{evidence}}$ (30%), $F_{\text{mapping}}$ (25%), $F_{\text{period}}$ (20%), $F_{\text{unit}}$ (10%), and $F_{\text{cross\_check}}$ (15%).
- **Document Integrity Verification (`app/scoring/quality_score.py`)**:
  - Cryptographically verifies local primary filing files against recorded SHA-256 hashes in `downloaded_documents`.
  - Explains that local matching hash proves consistency with the retrieved copy, not independent SEC origin authenticity.
- **Escalation & Review Routing Manager (`app/scoring/escalation.py`)**:
  - Categorizes scores into `HIGH`, `MEDIUM`, `LOW`.
  - Evaluates mandatory review triggers: hash mismatch, value mismatch, ambiguous period/unit, unresolved or candidate custom tag, missing metric.
  - Assigns routing categories: `AUTO_PASS`, `REVIEW_RECOMMENDED`, and `MANDATORY_REVIEW`.
- **Filing-Level Aggregation (`app/scoring/quality_score.py`)**:
  - Assesses all 10 canonical metrics, penalizing missing disclosures ($0.0$).
  - Enforces mandatory review and score capping if critical core financial metrics are missing.
- **Database Persistence (`app/database/models.py`, `app/database/repositories/scoring_repository.py`)**:
  - `metric_confidence_scores` and `filing_confidence_scores` tables with idempotent upsert logic.
- **FastAPI Endpoints (`app/api/routes/metrics.py`, `app/api/schemas/metric.py`)**:
  - Endpoints to score a filing, get filing confidence, and get metric confidence.
- **Streamlit Dashboard Integration (`dashboard/pages/2_Extraction_Results.py`)**:
  - Interactive extraction confidence review, factor breakdown, SHA-256 integrity status, and drilldown expanders.

### Phase 7: Financial Validation Engine
- **Deterministic Accounting Rules (`app/validation/`)**:
  - **Rule A: Accounting Equation (`app/validation/accounting_equation.py`)**:
    - Validates $\text{Assets} \approx \text{Liabilities} + \text{Equity}$ using `Decimal` arithmetic.
    - Configurable tolerance: $\max(\text{abs\_tol}, \text{rel\_tol} \times |\text{Assets}|)$.
    - Explicitly returns `NOT_EVALUATED` if components are missing—never substitutes zero.
  - **Rule B: Operating Income Presentation (`app/validation/operating_income.py`)**:
    - Validates $\text{Operating Income} \approx \text{Gross Profit} - \text{Operating Expenses}$.
    - Traceable Operating Expenses pulled directly from filing iXBRL facts (`OperatingExpenses`).
    - Returns `NOT_EVALUATED` if components are unavailable (e.g. single-step format).
  - **Rule C: Year-over-Year (YoY) Variance Analysis (`app/validation/yoy_analysis.py`)**:
    - Formula: $\text{YoY Change (\%)} = \frac{\text{Current Value} - \text{Prior Value}}{|\text{Prior Value}|} \times 100$.
    - Handles zero prior values (division by zero avoided, returns absolute change and `WARNING`).
    - Preserves directional signs for negative values.
    - Anomaly threshold ($40\%$ default) flags material variances as `WARNING`—never labels anomalies as fraud.
  - **Rule D: Cross-Statement Consistency (`app/validation/cross_statement.py`)**:
    - Compares Net Income across Income Statement and Cash Flow Statement reconciliation.
    - Compares Cash & Cash Equivalents across Balance Sheet and Cash Flow Statement ending cash.
- **Centralized Validation Configuration (`config/validation_rules.json`)**:
  - Configurable relative/absolute tolerances, anomaly warning thresholds, and rule enable flags.
- **Validation Engine Coordinator (`app/validation/engine.py`)**:
  - Coordinates facts, comparative prior-year disclosures, iXBRL secondary facts, and Phase 6 confidence metadata.
  - Generates structured `ValidationRecord` outputs with rule versioning and explanations.
- **Database Persistence (`app/database/models.py`, `app/database/repositories/validation_repository.py`)**:
  - `financial_validations` SQLite table storing execution results, calculations, and evidence references with idempotent replacement.
- **FastAPI Endpoints (`app/api/routes/validations.py`, `app/api/schemas/validation.py`)**:
  - `POST /validations/run/{accession_number}`: triggers validation rules execution.
  - `GET /validations/{accession_number}`: retrieves summary and validation records.
  - `GET /validations/{accession_number}/rules/{rule_id}`: retrieves single rule details.
- **Streamlit Dashboard Integration (`dashboard/pages/3_Validation.py`)**:
  - Summary KPI cards (total, passed, failed, warnings, not evaluated).
  - Interactive sections for core accounting equations, YoY variance table, and cross-statement checks.

### Phase 8: Agentic Workflow using LangGraph
- **Typed Workflow State (`app/workflow/state.py`)**:
  - Strongly typed `FilingWorkflowState` (TypedDict) tracking workflow ID, thread ID, accession number, CIK, metadata, retrieval, extraction, quality scores, validation results, review requirements, review decisions, errors, and append-only execution log.
- **Durable SQLite Checkpointer (`app/workflow/checkpointer.py`)**:
  - `SqliteSaver` instance connecting to `data/database/checkpoints.db` (`check_same_thread=False`).
  - Idempotent table migration (`saver.setup()`).
  - Full execution state persists across process crashes and server restarts.
- **Deterministic Pipeline Nodes (`app/workflow/nodes.py`)**:
  - Node 1: `retrieve_node` – Resolves metadata and ensures primary document is downloaded with SHA-256 integrity verification.
  - Node 2: `extract_node` – Extracts Company Facts, iXBRL facts via Arelle runner, executes cross-source reconciliation, and discovers custom concept candidates.
  - Node 3: `score_node` – Runs Phase 6 5-factor confidence scoring engine.
  - Node 4: `validate_node` – Executes Phase 7 financial validation rules.
  - Node 5: `review_routing_node` – Deterministic policy gate checking `MANDATORY_REVIEW`, `REVIEW_RECOMMENDED`, missing critical metrics, or validation failures.
  - Node 6: `human_review_node` – Pauses workflow using LangGraph native `interrupt()` with structured review payload; unblocks when auditor submits decision via `Command(resume=...)`.
  - Node 7: `complete_node` – Finalizes state to `COMPLETED`, `REJECTED`, or `FAILED`.
- **Conditional Routing (`app/workflow/routing.py`, `app/workflow/graph.py`)**:
  - Routing guards ensuring errors immediately short-circuit to completion.
  - Escalation routing directing auto-pass filings directly to completion while routing flagged filings to `human_review`.
- **Workflow Service Orchestration (`app/workflow/resume.py`)**:
  - `start_workflow()`: Compiles graph with checkpointer and triggers execution.
  - `get_workflow_state()`: Inspects thread state, checks if paused for review, extracts interrupt details.
  - `resume_workflow()`: Validates paused state, applies `Command(resume=payload)`, and executes downstream completion.
- **FastAPI Workflow Endpoints (`app/api/routes/workflows.py`, `app/api/schemas/workflow.py`)**:
  - `POST /workflows/start`: Initiates workflow for an accession number/CIK.
  - `GET /workflows/{thread_id}/status`: Queries stage, pause status, review requirements, and execution log.
  - `GET /workflows/{thread_id}/result`: Retrieves full typed state dictionary.
  - `POST /workflows/{thread_id}/review`: Resumes interrupted workflow with auditor decision (`APPROVED`, `REJECTED`, `CORRECTED`).
- **Streamlit Human Review Dashboard (`dashboard/pages/4_Human_Review.py`)**:
  - Dedicated page for reviewing workflow runs, viewing pause reasons, inspecting evidence, and submitting auditor decisions with real-time feedback.

### Phase 9: Human Review & Auditor Interface
- **Human Review Persistence (`app/database/models.py`, `app/database/repositories/review_repository.py`)**:
  - SQLite table `human_reviews` storing review ID, accession number, thread ID, metric ID, review round, reviewer ID, decision (`APPROVED`, `CORRECTED`, `REJECTED`), original value, corrected value, unit, mandatory comment, evidence citation, idempotency key, validation statuses, and timestamp.
  - Indexed on `accession_number`, `(accession_number, metric_id)`, and `idempotency_key`.
- **Review Idempotency & Safety Engine (`app/review/idempotency.py`)**:
  - Enforces review idempotency keys, preventing duplicate processing, double execution, or duplicate audit events when reviewers double-click or replay submissions.
  - Form validation: rejects empty, malformed, or automated/bot reviewer identities (`ai`, `bot`, `system`, `llm`), enforcing human accountability.
- **Review Service & Automated Validation Recalculation (`app/review/service.py`)**:
  - `get_review_queue()`: Gathers pending items across filings, linking extracted facts, quality score factor breakdown, source locators, and validation findings.
  - `submit_review()`:
    - **Approval**: Records reviewer sign-off without mutating factual values.
    - **Correction**: Strictly preserves original extracted value (`original_value`) and stores reviewer correction separately (`corrected_value`).
    - **Validation Recalculation**: Automatically re-runs affected accounting rules (e.g. Accounting Equation, Operating Income, YoY Analysis) with `fact_overrides` and logs previous vs. new validation outcomes (`PASS` / `FAIL`).
    - **Rejection**: Flags metrics as unresolved, preventing unverified facts from being treated as reliable.
    - **Workflow Resumption**: Resumes associated LangGraph workflow threads when currently paused at the review gate.
- **FastAPI Human Review Endpoints (`app/api/routes/reviews.py`, `app/api/schemas/review.py`)**:
  - `GET /reviews/queue`: Query pending review queue items with full evidence and escalation context.
  - `GET /reviews/history/{accession_number}`: Retrieve complete human review audit trail for a filing.
  - `POST /reviews/submit`: Submit auditor decision with idempotency validation and real-time validation rerun.
- **Streamlit Auditor Dashboard Integration (`dashboard/pages/4_Human_Review.py`)**:
  - Multi-tab auditor interface:
    - **Review Queue Tab**: Interactive queue table, evidence drilldown expander, and decision submission form.
    - **Workflow Gate Tab**: Real-time pause banner, active triggers, and workflow resume controls.
    - **Review Audit History Tab**: Historical log of all review rounds, original vs. corrected values, reviewer IDs, comments, and timestamps.
    - **Pipeline Artifacts Tab**: JSON inspection for confidence scores, validation summaries, and execution trace logs.

### Phase 10: Tamper-Evident Audit Ledger
- **Deterministic Canonical JSON Serialization (`app/audit/hashing.py`)**:
  - Implemented `canonical_json(data)` guaranteeing stable, lexicographically sorted dictionary keys, compact formatting without extraneous whitespace (`separators=(',', ':')`), explicit null/boolean representations, and unescaped Unicode.
- **Cryptographic SHA-256 Hash Chaining (`app/audit/hashing.py`)**:
  - Hash computation formula:
    $$\text{event\_hash} = \text{SHA256}(\text{previous\_hash} + \text{canonical\_json}(\text{payload}) + \text{created\_at})$$
  - Fixed, well-defined genesis reference: $\text{GENESIS\_PREVIOUS\_HASH} = \text{"0"} \times 64$.
  - Optional HMAC-SHA256 signed checkpoint export (`sign_checkpoint`).
- **Insert-Only Ledger Service & Persistence (`app/audit/ledger.py`, `app/database/models.py`, `app/database/repositories/audit_repository.py`)**:
  - SQLite table `audit_events` with unique monotonic sequence numbers (`sequence_num`), `event_id`, `event_type`, `actor`, `payload_json`, `previous_hash`, `event_hash`, `created_at`, and `signature`.
  - Transaction-safe append-only execution (`BEGIN IMMEDIATE`) preventing sequence collisions or concurrent chain branching.
  - No update or delete operations exist in the audit service or repository.
  - Idempotent duplicate event suppression based on type, actor, accession, and payload.
- **Independent Chain Verification & Tamper Detection (`app/audit/verification.py`)**:
  - Implemented `AuditVerifier.verify_chain()`:
    - Sequentially re-computes every hash from its canonical payload and timestamp.
    - Validates sequence monotonicity ($seq_i = seq_{i-1} + 1$).
    - Validates pointer continuity ($previous\_hash_i == event\_hash_{i-1}$).
    - Detects modified payloads, forged hashes, broken pointers, deleted events, and reordered records.
    - Pinpoints the exact event ID, sequence number, and failure explanation; never reports a corrupted chain as `VALID`.
- **System Integration**:
  - Automatically records `REVIEW_DECISION_RECORDED` events with reviewer identity, decision, original/corrected values, and comments.
  - Records `WORKFLOW_STARTED` and `WORKFLOW_RESUMED` events during agentic execution.
- **FastAPI Audit Ledger Endpoints (`app/api/routes/audit.py`, `app/api/schemas/audit.py`)**:
  - `GET /audit/events`: Retrieve chronological audit ledger events.
  - `GET /audit/verify`: Cryptographically verify audit ledger hash chain (`VALID` / `TAMPERED`).
  - `GET /audit/export`: Export signed cryptographic checkpoint of current audit ledger state.
- **Streamlit Dashboard Integration (`dashboard/pages/4_Human_Review.py`)**:
  - Added "Tamper-Evident Audit Ledger" tab with live cryptographic chain integrity badge, total event count, latest head hash, sequential audit trail table, expandable event payloads, and one-click signed checkpoint export download.

### Phase 11: Benchmark and Final Verification
- **Verified Reference Dataset (`data/reference/benchmark_reference.json`, `app/benchmark/reference_loader.py`)**:
  - Curated 28 manually verified SEC reference facts spanning 3 distinct companies across 4 annual filings:
    - Apple Inc. FY2026 (`0000320193-26-000026`) - 10 canonical metrics.
    - Microsoft Corp FY2026 (`0001193125-26-323660`) - 10 canonical metrics.
    - Amazon.com Inc. FY2025 (`0001018724-26-000004`) - 7 canonical metrics.
    - Apple Inc. FY2023 (`0000320193-23-000106`) - 1 canonical metric.
  - Every reference record documents: `test_case_id`, `company_name`, `ticker`, `cik`, `accession_number`, `fiscal_year`, `period_end`, `period_type`, `metric_id`, `canonical_name`, `expected_value`, `expected_unit`, `expected_concept`, `statement_type`, `evidence_source`, and `has_anomaly`.
  - 100% verified against original 10-K primary financial statements.
- **Benchmark Evaluator Engine (`app/benchmark/evaluator.py`)**:
  - **Baseline A (Simple Tag Lookup)**: Naive concept lookup directly from raw XBRL without advanced duration matching, context resolution, or dimensional filtering.
  - **Baseline B (LLM-Only Baseline)**: Evaluates structured extraction from filing text. When LLM credentials are absent, cleanly skips with explicit disclosure per specification.
  - **Method C (FilingGuard Hybrid Pipeline)**: Uses deterministic company facts extraction, duration frame matching, cross-source reconciliation, and primary document SHA-256 evidence links.
- **Evaluation Metrics Engine (`app/benchmark/metrics.py`)**:
  - Computes exact match rate (accuracy), value match rate (tolerance $\le 1.0$), unit accuracy, period selection accuracy, evidence support rate, missing-value rate, false-positive rate, and anomaly precision/recall.
  - Generates per-metric and per-company breakdown statistics.
- **Database Persistence (`app/database/models.py`, `app/database/repositories/benchmark_repository.py`)**:
  - SQLite table `benchmark_results` per Section 12.8 specification with indexes on `filing_id`, `test_case_id`, and `method`.
  - `BenchmarkRepository` supporting `save_results`, `get_results` (filtered by method/filing), and idempotent `clear_results`.
- **FastAPI Benchmark Endpoints (`app/api/routes/reports.py`, `app/api/schemas/benchmark.py`)**:
  - `GET /benchmark/report`: Full comparison report with summary, method metrics, comparison table, and documented limitations.
  - `GET /benchmark/summary`: High-level reference summary and comparative accuracy rates.
  - `GET /benchmark/results`: Itemized evaluation results, filterable by method.
  - `GET /benchmark/comparison`: Side-by-side row comparison across methods.
  - `POST /benchmark/run`: Executes benchmark run and persists results to SQLite.
- **Streamlit Accuracy Report Dashboard (`dashboard/pages/5_Accuracy_Report.py`)**:
  - Live benchmark re-run button, reference dataset summary cards, 3-way comparative performance table, itemized test case drilldown, metric breakdowns, and documented limitations.

---

## Live Apple 10-K Financial Validation Results

**Filing**: Apple Inc. (CIK `0000320193`) – Form 10-K (`0000320193-26-000026`)
- **Total Rules Executed**: 14
- **Passed**: 13 | **Failed**: 0 | **Warnings**: 1 | **Not Evaluated**: 0

| Rule ID | Name | Category | Status | Expected Value | Actual Value | Difference | Result Explanation |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`balance_sheet_equation`** | Accounting Equation | Balance Sheet | `PASS` | $404,548,000,000 | $404,548,000,000 | $0.00 | Exact match ($0 difference): Assets = Liabilities + Equity |
| **`operating_income_presentation`** | Operating Income | Income Statement | `PASS` | $158,063,000,000 | $158,063,000,000 | $0.00 | Exact match ($0 difference): Gross Profit - Opex = Operating Income |
| **`yoy_variance_revenue`** | YoY Revenue | Variance | `PASS` | $416,161,000,000 | $478,834,000,000 | +$62,673,000,000 | Normal growth: +15.06% YoY |
| **`yoy_variance_net_income`** | YoY Net Income | Variance | `PASS` | $112,010,000,000 | $132,175,000,000 | +$20,165,000,000 | Normal growth: +18.00% YoY |
| **`yoy_variance_gross_profit`** | YoY Gross Profit | Variance | `PASS` | $195,201,000,000 | $233,602,000,000 | +$38,401,000,000 | Normal growth: +19.67% YoY |
| **`yoy_variance_operating_income`** | YoY Operating Income | Variance | `PASS` | $133,050,000,000 | $158,063,000,000 | +$25,013,000,000 | Normal growth: +18.80% YoY |
| **`yoy_variance_total_assets`** | YoY Total Assets | Variance | `PASS` | $359,241,000,000 | $404,548,000,000 | +$45,307,000,000 | Normal growth: +12.61% YoY |
| **`yoy_variance_total_liabilities`** | YoY Total Liabilities | Variance | `PASS` | $285,508,000,000 | $292,455,000,000 | +$6,947,000,000 | Normal growth: +2.43% YoY |
| **`yoy_variance_stockholders_equity`** | YoY Stockholders' Equity | Variance | `WARNING` | $73,733,000,000 | $112,093,000,000 | +$38,360,000,000 | Material variance: +52.02% exceeds 40% threshold (auditor review flagged) |
| **`yoy_variance_cash_and_cash_eq`** | YoY Cash & Cash Eq | Variance | `PASS` | $35,934,000,000 | $36,305,000,000 | +$371,000,000 | Normal growth: +1.03% YoY |
| **`yoy_variance_operating_cash_flow`** | YoY Operating Cash Flow | Variance | `PASS` | $111,482,000,000 | $145,097,000,000 | +$33,615,000,000 | Normal growth: +30.15% YoY |
| **`yoy_variance_capital_expenditure`** | YoY CapEx | Variance | `PASS` | $12,715,000,000 | $9,041,000,000 | -$3,674,000,000 | Normal variance: -28.90% YoY |
| **`cross_statement_net_income`** | Net Income Consistency | Cross-Statement | `PASS` | $132,175,000,000 | $132,175,000,000 | $0.00 | Exact match ($0 difference): Income Statement vs Cash Flow Statement |
| **`cross_statement_cash`** | Cash Balance Consistency | Cross-Statement | `PASS` | $36,305,000,000 | $36,305,000,000 | $0.00 | Exact match ($0 difference): Balance Sheet vs Cash Flow Statement |

---

## Test Execution Results

**Test command**:
```bash
pytest -v
```

**Results**:
- `tests/api/test_health.py`: 2 passed
- `tests/integration/test_company_facts_live_extraction.py`: 1 passed
- `tests/integration/test_reconciliation_live.py`: 1 passed
- `tests/integration/test_scoring_live.py`: 1 passed
- `tests/integration/test_sec_live_retrieval.py`: 3 passed
- `tests/integration/test_validation_live.py`: 1 passed (Real Apple 10-K financial validation: 14 rules, 0 failures, 1 warning)
- `tests/integration/test_xbrl_live_extraction.py`: 1 passed
- `tests/unit/test_company_facts_extraction.py`: 8 passed
- `tests/unit/test_database_and_config.py`: 2 passed
- `tests/unit/test_scoring_api.py`: 4 passed
- `tests/unit/test_scoring_engine.py`: 13 passed
- `tests/unit/test_sec_retrieval.py`: 9 passed
- `tests/unit/test_semantic_and_reconciliation.py`: 6 passed
- `tests/unit/test_validation_api.py`: 4 passed (FastAPI validation endpoints, 404 handling, summary schema)
- `tests/unit/test_validation_engine.py`: 18 passed
  - `test_accounting_equation_exact_match`
  - `test_accounting_equation_within_tolerance`
  - `test_accounting_equation_outside_tolerance`
  - `test_missing_equity_or_liabilities_not_evaluated`
  - `test_operating_income_exact_match`
  - `test_operating_expenses_unavailable_not_evaluated`
  - `test_operating_income_mismatch`
  - `test_positive_yoy_growth`
  - `test_negative_yoy_growth_anomaly`
  - `test_previous_year_value_zero`
  - `test_negative_financial_values_yoy`
  - `test_missing_prior_year_facts`
  - `test_unit_mismatch_yoy`
  - `test_cross_statement_exact_match`
  - `test_cross_statement_mismatch`
  - `test_low_confidence_input_facts_flagged`
  - `test_rule_versioning`
  - `test_idempotent_persistence`
- `tests/unit/test_workflow.py`: 8 passed
  - `test_typed_workflow_state_structure`
  - `test_successful_end_to_end_graph_execution`
  - `test_sec_retrieval_failure_handling`
  - `test_scoring_mandatory_review_interruption`
  - `test_human_review_approval_and_resume`
  - `test_human_review_rejection_and_resume`
  - `test_sqlite_checkpoint_persistence_and_restart`
  - `test_invalid_thread_id_raises_value_error`
- `tests/unit/test_workflow_api.py`: 5 passed
  - `test_start_workflow_invalid_input`
  - `test_get_workflow_status_not_found`
  - `test_get_workflow_result_not_found`
  - `test_submit_review_invalid_thread`
  - `test_workflow_start_api_success`
- `tests/integration/test_workflow_live.py`: 1 passed (Live Apple Inc. 10-K end-to-end execution, scores, validation, SQLite persistence)
- `tests/unit/test_review_service.py`: 7 passed
  - `test_submit_approval_recorded`
  - `test_submit_correction_preserves_original_and_reruns_validation`
  - `test_submit_rejection_marks_unresolved`
  - `test_invalid_correction_values_rejected`
  - `test_automated_actor_rejected`
  - `test_duplicate_review_prevented_by_idempotency_key`
  - `test_review_resumes_paused_workflow`
- `tests/unit/test_review_api.py`: 5 passed
  - `test_get_review_queue_endpoint`
  - `test_get_review_history_empty_accession`
  - `test_get_review_history_success`
  - `test_submit_review_validation_errors`
  - `test_submit_review_success_and_idempotency`
- `tests/integration/test_review_live.py`: 1 passed (Live Apple Inc. 10-K review queue, approval, persistence, and duplicate idempotency)
- `tests/unit/test_audit_hashing.py`: 4 passed
  - `test_canonical_json_key_ordering`
  - `test_canonical_json_data_types`
  - `test_event_hash_calculation_determinism`
  - `test_checkpoint_signature_generation`
- `tests/unit/test_audit_ledger.py`: 4 passed
  - `test_genesis_event_creation`
  - `test_linear_hash_chaining`
  - `test_duplicate_event_suppression`
  - `test_missing_actor_or_type_raises_value_error`
- `tests/unit/test_audit_verification.py`: 8 passed
  - `test_valid_chain_verification`
  - `test_empty_chain_is_valid`
  - `test_tampered_payload_detected`
  - `test_tampered_event_hash_detected`
  - `test_broken_previous_hash_pointer_detected`
  - `test_missing_or_deleted_event_detected`
  - `test_reordered_events_detected`
  - `test_checkpoint_export`
- `tests/unit/test_audit_api.py`: 4 passed
  - `test_get_audit_events_endpoint`
  - `test_verify_audit_ledger_valid`
  - `test_verify_audit_ledger_tampered`
  - `test_export_checkpoint_endpoint`
- `tests/integration/test_audit_live.py`: 1 passed (Live end-to-end audit ledger integration, VALID verification, and SQL tamper detection)
- `tests/unit/test_xbrl_parsing.py`: 7 passed
- `tests/unit/test_benchmark.py`: 9 passed
  - `test_reference_dataset_loads_correctly`
  - `test_reference_summary_and_grouping`
  - `test_values_match_tolerance`
  - `test_compute_metrics_calculation`
  - `test_evaluator_simple_tag_baseline`
  - `test_evaluator_llm_baseline_disclosure`
  - `test_evaluator_filingguard_pipeline`
  - `test_deterministic_reproducibility`
  - `test_benchmark_repository_crud`
- `tests/unit/test_benchmark_api.py`: 5 passed
  - `test_get_benchmark_summary_api`
  - `test_get_benchmark_report_api`
  - `test_get_benchmark_results_filter_api`
  - `test_get_benchmark_comparison_api`
  - `test_run_benchmark_post_api`
- `tests/integration/test_benchmark_live.py`: 1 passed (Live end-to-end benchmark across AAPL, MSFT, and AMZN, SQLite persistence, and traceability validation)
- `tests/unit/test_filings_api.py`: 4 passed (SEC filings API routes, list, retrieval, ingest validation)
- `tests/unit/test_dashboard_pages.py`: 2 passed (All dashboard pages compile to bytecode without syntax errors, UI helper tests)

**Total**: 150 passed in 38.37s.

---

## Benchmark Measured Results (Phase 11)

**Reference Dataset**: 28 manually verified SEC reference facts across 3 companies (Apple Inc., Microsoft Corp, Amazon.com Inc.) and 4 annual filings (`0000320193-26-000026`, `0001193125-26-323660`, `0001018724-26-000004`, `0000320193-23-000106`).

| Metric / Criterion | Baseline A: Simple Tag Lookup | Baseline B: LLM-Only | FilingGuard (Hybrid Pipeline) |
| :--- | :---: | :---: | :---: |
| **Exact Match Rate (Accuracy)** | **35.7%** (10/28) | 0.0% (0/28 - Skipped) | **100.0%** (28/28) |
| **Value Match Rate** | 35.7% (10/28) | 0.0% (0/28 - Skipped) | **100.0%** (28/28) |
| **Period Selection Accuracy** | 100.0% (evaluated) | 0.0% (Skipped) | **100.0%** |
| **Unit Accuracy** | 100.0% (evaluated) | 0.0% (Skipped) | **100.0%** |
| **Evidence Support Rate** | 0.0% (no cryptographic link) | 0.0% | **100.0%** (SHA-256 + source statement) |
| **Missing / Unresolved Value Rate** | 64.3% (18/28) | 100.0% (28/28) | **0.0%** (0/28) |
| **False-Positive / Mismatch Rate** | 0.0% | 0.0% | **0.0%** |
| **Anomaly Precision** | 0.0% | 0.0% | **100.0%** |
| **Anomaly Recall** | 0.0% | 0.0% | **100.0%** |

*Note: Baseline B was cleanly skipped with disclosure as API credentials were not configured in this environment, per Section 16.3.*

---

## Known Limitations & Validation Assumptions
1. **Traceable Operating Expenses**: Operating expenses are strictly parsed from reported Inline XBRL line items (`OperatingExpenses`). If omitted in filing presentation (e.g. single-step format), the engine returns `NOT_EVALUATED` rather than inventing or imputing figures.
2. **Material Anomaly $\neq$ Fraud**: A warning on YoY variance (such as Apple's +52.02% equity increase) flags significant operational or capital structure events for auditor review; it is never labelled as fraud.
3. **Cross-Statement Scope**: Cross-statement checks require exact alignment of entity, duration, and unit before comparison, guarding against false divergence alerts.
4. **Correction Immutability**: Reviewer corrections strictly preserve original SEC-reported facts in `company_facts` and `xbrl_parsed_facts`; corrected values are persisted exclusively in `human_reviews` and evaluated dynamically via `fact_overrides`.
5. **Tamper-Evident History**: SQLite tables can be accessed or altered by superusers at the storage layer; the cryptographic hash chain does not make local disk blocks physically unwriteable, but guarantees that any modification, reordering, or deletion is mathematically detected and localized upon verification.
6. **Benchmark Sample Scope**: Prototype benchmark comprises 28 reference facts across 3 companies. Non-standard presentations (e.g. Amazon missing separate gross profit line item in standard taxonomy facts) are transparently recorded as missing rather than imputed.

---

## Phase Status Summary
- **Phase 0**: Understand & freeze requirements - Completed
- **Phase 1**: Repository and environment baseline - Completed
- **Phase 2**: SEC Retrieval - Completed
- **Phase 3**: Company Facts Extraction - Completed
- **Phase 4**: Original Filing and Inline XBRL - Completed
- **Phase 5**: Semantic Mapping and Context Selector - Completed
- **Phase 6**: Evidence and Confidence Scoring Engine - Completed
- **Phase 7**: Financial Validation Engine - Completed
- **Phase 8**: Agentic Workflow using LangGraph - Completed
- **Phase 9**: Human Review and API - Completed
- **Phase 10**: Tamper-Evident Audit Ledger - Completed
- **Phase 11**: Benchmark and Final Verification - Completed
- **Phase 12**: Dashboard and Demo (Complete UI/UX Redesign) - Completed
- **Project Status**: 100% Complete & Verified (150/150 Tests Passing)
