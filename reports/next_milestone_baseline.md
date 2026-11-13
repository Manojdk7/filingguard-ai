# FilingGuard AI Reliability Milestone — Baseline

## Scope and constraints

This baseline was collected before changing application code. It covers the test
suite, confidence scoring, benchmark dataset and evaluator, local persistence,
checkpoint storage, and SEC request configuration. No live SEC retrieval was
attempted because the configured User-Agent still contains a placeholder contact.

## Test baseline

- `pytest --collect-only -q`: 206 tests across 32 test files.
- The full baseline suite had two failures:
  - `tests/integration/test_benchmark_live.py::test_live_benchmark_end_to_end`
    expected the simple-tag missing rate to exceed 0.50; observed 0.392857
    (11 of 28 missing).
  - `tests/unit/test_benchmark_api.py::test_run_benchmark_post_api` expected
    FilingGuard accuracy above 0.80; observed 0.538462 (28 of 52 exact).
- In the integration test's intended cached subset (AAPL, MSFT, AMZN), a
  non-persisting baseline run returned FilingGuard 28/28 exact, no missing
  values, and an evidence-support rate of 1.0. Simple-tag returned 10/28 exact,
  11 missing, and an evidence-support rate of 0.0.
- A non-persisting full-dataset run returned FilingGuard 28/52 exact, 24
  missing, and an evidence-support rate of 1.0. All 24 missing cases belong to
  WMT, XOM, or TSLA (eight cases each). The reference data covers 52 cases,
  six companies, seven accessions, and ten metrics.

These are observed local-database benchmark results, not real-time SEC results.
The benchmark evaluator reads locally persisted facts. The "live" integration
test name does not indicate that it contacts SEC.

## Benchmark integrity observations

- All 52 reference records have `reviewer_verified=true`, but each record
  provides only an `evidence_source` free-text citation (usually a statement/page
  reference). The schema contains no source URL, filing form/date, exact fact
  context, or verification method. The loader validates the boolean and unique
  case IDs; it does not independently verify reference values.
- The evaluator's FilingGuard evidence flag is true for every selected Company
  Facts value, regardless of record-level source locator, matching Inline XBRL
  evidence, or persisted document integrity. Thus the reported 100% evidence
  support rate is not evidence that every prediction has a traceable evidence
  chain.
- Accuracy is exact value + unit + period matches divided by all reference
  cases, so missing predictions count as non-matches. This explains the
  observed full-set accuracy of 28/52 (0.538462); it must not be changed merely
  to make an existing threshold pass.
- The simple-tag integration expectation conflicts with the observed dataset:
  its missing rate on the selected 28-case subset is 11/28 (0.392857), not
  greater than 0.50.

## Confidence scoring observations

- The configured five weights sum to 1.0:
  evidence 0.30, concept mapping 0.25, period 0.20, unit 0.10, and cross-check
  0.15.
- Scores are deterministic rubric scores, not calibrated probabilities.
- The persisted Apple accession `0000320193-26-000026` has ten metric scores;
  all five stored factors and composite scores equal 1.0. The stored filing
  score is 1.0.
- Current scoring can grant full evidence points when a local document hash
  matches and reconciliation is `exact_match` or `value_mismatch`; the code
  describes the two SEC-derived pathways as "independent" without supporting
  independence. A hash match establishes consistency with the stored copy, not
  independent SEC authenticity.
- Missing duration dates receive a high fallback period score (0.85), and
  successful branches can receive full factor points without granular,
  persisted scoring evidence. Both contribute to scores that appear more
  certain than the evidence warrants.
- Local reconciliation rows are append-only in `save_reconciliations`; a
  delete-by-accession helper exists but is not performed by that save method.
  The application database currently has 31 reconciliation rows, so repeated
  runs can leave duplicate historical rows. This needs to be considered when
  ensuring scoring reads a deterministic latest set.

## Local state snapshot

Observed during this baseline (the application may be used concurrently, so
these counts are a snapshot, not immutable project constants):

- Application database: 8 filings, 152 Company Facts rows, 5,075 parsed XBRL
  facts, 52 metric score rows, 7 filing score rows, 517 audit events, and 208
  benchmark result rows.
- Workflow checkpoints are stored separately in
  `data/database/checkpoints.db`, with `checkpoints` and `writes` tables
  (295 and 4,554 rows respectively). There is no `workflow_checkpoints` table
  in the application database.
- The scoring tables include one ten-metric score set per accession for five
  accessions in the snapshot; the filing-score table does not include every
  accession with metric scores.

## SEC verification limitation

The configured SEC User-Agent contains an `example.com` placeholder. Live SEC
verification remains blocked until the project owner configures a valid,
monitored contact locally. The contact value must not be committed or included
in reports. No SEC response or end-to-end live retrieval is claimed in this
baseline.

## Baseline decision

Proceed by correcting the score rubric and its evidence explanations,
benchmark evidence/coverage semantics, and tests to assert behavior supported
by the local data. Do not edit reference financial values or present them as
independently verified without obtaining and recording source-level
verification. Keep real SEC verification explicitly blocked until configuration
is valid.
