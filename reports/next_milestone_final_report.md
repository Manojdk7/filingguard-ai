# FilingGuard AI Scoring and Benchmark Integrity — Final Report

## Outcome

Completed the scoring-transparency and benchmark-integrity milestone without
changing extraction, reconciliation, validation, or audit algorithms.

## Changes

- Replaced the five scoring factors with source reliability, cross-source
  agreement, period compatibility, unit/dimensional compatibility, and
  extraction/mapping quality. Scores now retain factor values, weights,
  weighted contributions, supporting evidence, and deductions.
- Prevented local document-hash consistency from being presented as independent
  SEC authentication. Missing period context is handled more conservatively,
  and older persisted scores are identified as legacy in the extraction
  results page.
- Tightened benchmark evidence checks to require matching Inline XBRL facts,
  values, units, periods, locators, document hashes, and locally verified filing
  bytes.
- Removed the ground-truth-derived regex simulation. The regex and
  unimplemented LLM baselines are reported as not evaluated. Missing
  predictions remain failures; unevaluated cases are excluded from accuracy
  denominators.
- Updated benchmark API fields, accuracy-report disclosures, tests, README,
  and implementation documentation to distinguish coverage, evidence support,
  and reference-data provenance.
- Added deterministic ordering when repeated reconciliation rows are read.

## Modified application and test files

- `app/scoring/quality_score.py`
- `config/scoring_config.json`
- `dashboard/pages/2_Extraction_Results.py`
- `app/benchmark/evaluator.py`
- `app/benchmark/metrics.py`
- `app/benchmark/reference_loader.py`
- `app/api/schemas/benchmark.py`
- `dashboard/pages/5_Accuracy_Report.py`
- `app/database/repositories/reconciliation_repository.py`
- `tests/unit/test_scoring_engine.py`
- `tests/integration/test_scoring_live.py`
- `tests/unit/test_benchmark.py`
- `tests/unit/test_benchmark_api.py`
- `tests/integration/test_benchmark_live.py`
- `README.md`
- `implementation.md`

The pre-change findings are recorded in
[`next_milestone_baseline.md`](./next_milestone_baseline.md).

## Observed local benchmark results

These are results from the locally persisted dataset, not live SEC retrieval:

- FilingGuard: 28 exact matches out of 52 reference cases; 24 predictions
  missing. Of the 28 returned predictions, 17 had matching traceable source
  evidence.
- Simple-tag baseline: 10 exact matches out of 52 full-set cases. On the
  cached AAPL/MSFT/AMZN subset, it returned 10 exact matches out of 28 and
  missed 11.
- LLM and regex/table baselines: not evaluated.
- The reference records contain reviewer flags but lack source-level
  provenance sufficient to independently verify every reference value.

## Verification

- Complete test suite in the project virtual environment: **211 tests passed**.
- Pylance syntax checks: no syntax errors in the modified scoring, benchmark,
  API schema, dashboard, and focused unit-test files.
- Accuracy Report rendered at a 1440px desktop viewport. Measured document and
  body widths were both 1440px, with no horizontal overflow in the inspected
  report view.
- The default system Python could not collect tests because `langgraph` is not
  installed there; the project `.venv` contains the correct test environment
  and passed the full suite.

## Remaining limitations

- Live SEC verification remains blocked because the configured SEC User-Agent
  still contains a placeholder contact. Configure a valid monitored contact
  locally before attempting live retrieval; do not commit or report the
  contact value.
- Reference-data reviewer flags are not independently substantiated by
  source URLs, precise evidence locators, or documented verification methods.
- Existing persisted v1 scores remain legacy until their records are rescored
  under the v2 rubric.
- The dashboard preview emitted Streamlit deprecation warnings for
  `use_container_width`; they did not prevent rendering and were not part of
  this scoring/benchmark-integrity scope.
