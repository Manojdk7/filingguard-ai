# Benchmark Methodology & Evaluation Design

## 1. Objective
Evaluate the extraction accuracy, evidence grounding, and anomaly sensitivity of FilingGuard AI against two baseline architectures across 28 manually verified SEC Form 10-K facts.

## 2. Baselines
- **Baseline A (Simple Tag Lookup)**: Extracts values using naive concept name matching directly from raw XBRL without advanced duration frame matching, context resolution, or dimensional separation.
- **Baseline B (LLM-Only Baseline)**: Prompts an LLM for structured JSON metric extraction from filing text. When API credentials are absent in offline environments, test cases are cleanly skipped with disclosure.
- **Method C (FilingGuard Hybrid Pipeline)**: Uses deterministic company facts extraction, duration frame matching, cross-source reconciliation against Inline XBRL, and SHA-256 evidence links.

## 3. Evaluation Metrics
- **Exact Match Rate**: Percentage of test cases where extracted value, unit, and period end date simultaneously match reference truth.
- **Value Match Rate**: Percentage of test cases where extracted value matches reference truth within a $\pm \$1.00$ tolerance.
- **Evidence Support Rate**: Proportion of facts anchored by cryptographic primary document SHA-256 hashes and line item citations.
- **Missing Value Rate**: Proportion of canonical metrics absent in output.
- **Anomaly Precision & Recall**: Accuracy in identifying flagged financial variances (e.g. Apple's +52.02% stockholders' equity variance).

