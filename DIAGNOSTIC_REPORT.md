# FilingGuard AI Diagnostic Report

## Findings and disposition

| Status | Finding | Root cause | Action / evidence |
|---|---|---|---|
| Fixed | Human Review approve/reject actions could fail when resuming a workflow. | Dashboard used `notes`, while `WorkflowService.resume_workflow` accepts `decision_notes`. | Updated both calls and covered by workflow tests. |
| Fixed | Extraction failed after retrieval with `'ArelleRunner' object has no attribute 'run'`. | `extract_node` used an obsolete Arelle runner/parser API (`run`/`parse`) instead of the implemented `InlineXBRLParser.parse_document()` API. | Updated workflow extraction to call the supported parser, persist parsed facts, and log when no Inline XBRL facts are produced; added a regression test for the persisted-document path. |
| Fixed | Reconciliation could compare facts without compatible period context, include dimensional facts, and silently choose conflicting duplicate facts. | Period, dimensional, and tie-breaking safeguards were incomplete. | Added explicit non-evaluated/ambiguous outcomes and period/context checks; added regression tests. |
| Fixed | Ticker-based ingestion only worked for a small hard-coded set, and custom ticker selections could not resolve to a company. | API used a static ticker map and the dashboard passed ticker text where a numeric CIK was required. | Added SEC company-directory resolution and used it in the API and dashboard. |
| Fixed | “Quick Ingest Demo Targets” reported existing local rows as if it had retrieved filings. | The button only counted database records. | It now retrieves and stores each preset company's real SEC filing, reports successes and per-company failures, and does not fabricate success. |
| Fixed | Extraction could be launched on a filing belonging to a different company than the selected issuer. | Filing options were not filtered by the selected CIK, and the widget could retain a stale accession. | Filtered options by normalized CIK and clear an invalid retained selection. |
| Fixed | SEC document downloads had no shared retry policy and accepted unsafe document/path inputs. | Binary downloads bypassed the SEC client; accession structure, issuer archive path, and filename were not validated together. | Added retried SEC byte downloads, accession-format validation, issuer-CIK archive-path checks, and strict filename checks. Accession-number prefixes are not treated as the issuer CIK. |
| Fixed | Concurrent SEC calls could race the shared rate limiter; malformed JSON was not reported as an upstream error. | The global limiter was unsynchronized and response parsing assumed valid object-shaped JSON. | Made rate limiting thread-safe and report malformed or unexpected JSON responses explicitly. |
| Fixed | README quickstart described the lightweight `/ui` page as the full dashboard and omitted the SEC contact requirement. | Documentation did not match the multipage Streamlit workflow or SEC fair-access requirements. | Updated dashboard startup guidance and the SEC User-Agent configuration warning. |
| Failing | The benchmark API unit test requires FilingGuard accuracy above 0.8; the current result is 0.5385. | The local benchmark has 52 reference cases, but 24 have no corresponding local filing/facts, including WMT, XOM, and TSLA accessions. | Left the assertion and benchmark values unchanged. Populate the missing real reference filings/facts or revise the benchmark contract with the project owner; do not fabricate results or weaken the assertion to conceal missing coverage. |
| Blocked | Live SEC retrieval and end-to-end ingestion were not verified in this run. | The local `SEC_USER_AGENT` is still an `example.com` placeholder, which does not meet SEC contact requirements. | Configure a descriptive User-Agent with a monitored contact locally, then run bounded SEC integration checks. Do not share that contact in chat. |

## UI changes

- Applied the existing navy, slate, blue, and teal visual system consistently across dashboard pages, with clearer page hierarchy, readable cards, and status treatments.
- Combined issuer selection, filing retrieval, and extraction results in the company workspace.
- Removed the separate “Archived SEC Filings in Local Database” table from Company Selection; persisted filings remain available to the issuer-filtered extraction selector.
- Added metric coverage, Company Facts versus Inline XBRL reconciliation, and source-evidence views based only on persisted workflow data.
- Improved validation, human-review, benchmark, and audit-history displays without inventing financial or benchmark values.
- Corrected the dashboard quickstart to distinguish the full Streamlit dashboard from the lightweight HTML page.

## Modified files

- `DIAGNOSTIC_REPORT.md`
- `README.md`
- `app/api/routes/filings.py`
- `app/extraction/reconciliation_service.py`
- `app/sec/client.py`
- `app/sec/filing_download.py`
- `app/sec/filing_index.py`
- `app/sec/submissions.py`
- `app/workflow/nodes.py`
- `dashboard/Home.py`
- `dashboard/components/styles.py`
- `dashboard/components/ui.py`
- `dashboard/pages/1_Company_Selection.py`
- `dashboard/pages/3_Validation.py`
- `dashboard/pages/4_Human_Review.py`
- `dashboard/pages/5_Accuracy_Report.py`
- `dashboard/pages/6_Audit_History.py`
- `tests/unit/test_filings_api.py`
- `tests/unit/test_sec_retrieval.py`
- `tests/unit/test_semantic_and_reconciliation.py`
- `tests/unit/test_workflow.py`
- `tests/unit/test_xbrl_parsing.py`

## Verification

- The complete `tests/unit` run completed with one failure: `test_run_benchmark_post_api`, due to the actual 0.5385 benchmark accuracy being below its existing `> 0.8` assertion; all other unit tests passed.
- Subsequent focused `test_workflow.py` and `test_xbrl_parsing.py` run passed after fixing the stale Arelle API call.
- Focused SEC, API, workflow, and dashboard regression tests passed.
- Added a regression case for Microsoft CIK `0000789019` with accession `0001193125-26-323660`; URL construction and download now use the issuer CIK for the archive directory and preserve the SEC accession number unchanged.
- `python -m compileall -q app dashboard tests` completed successfully.
- The updated Company Selection page rendered in the local Streamlit app, showed the company-filtered extraction selector, and had no horizontal overflow at the inspected viewport. No SEC action was triggered.
- Live integration tests were not run because SEC contact configuration is still invalid.

## Remaining work

1. Configure a valid SEC User-Agent locally and verify retrieval, document download, and extraction against SEC.
2. Obtain and persist the missing benchmark filing data, then rerun the benchmark without changing its expected threshold.
3. Rerun the complete unit suite after those data/configuration updates and execute the permitted live integration tests.
