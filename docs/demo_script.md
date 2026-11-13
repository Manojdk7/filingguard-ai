# FilingGuard AI — Hackathon Live Demo Script (3–5 Minutes)

1. **Company Selection (Page 1)**:
   - Select Apple Inc. (CIK `0000320193`) from preloaded targets.
   - Show the official Form 10-K metadata, filing date (2026-09-26), and SHA-256 hash.
   - Click **Run Agentic Workflow (LangGraph)** to execute the pipeline through retrieve, extract, score, and validate.
2. **Extraction & Reconciliation (Page 2)**:
   - Inspect the 10 extracted canonical metrics.
   - Point out the 5-factor confidence score breakdown (Evidence 30%, Mapping 25%, Period 20%, etc.).
   - Expand an extracted metric (e.g. Total Revenue: $478,834M) to view the SHA-256 verified source citation.
3. **Financial Validation Engine (Page 3)**:
   - Review the 14 accounting rules.
   - Highlight the Balance Sheet Accounting Equation passing with $0 difference.
   - Point out the YoY Stockholders' Equity Variance warning (+52.02% growth exceeding 40% threshold).
4. **Human Review Queue & Workflow Resume (Page 4)**:
   - Note the workflow paused state (`PAUSED_FOR_REVIEW`) on thread `thread_0000320193-26-000026`.
   - Submit an auditor approval or correction with reviewer identity (`auditor_jane_doe`) and justification comment.
   - Demonstrate the workflow resuming and reaching terminal `COMPLETED` state.
5. **Accuracy Report & Benchmark (Page 5)**:
   - Show the 3-baseline benchmark table: FilingGuard (100% accuracy) vs Naive Tag Lookup (35.7% accuracy).
6. **Cryptographic Audit Ledger (Page 6)**:
   - Verify the audit ledger shows `🟢 Chain Status: VALID`.
   - Click **Simulate Payload Tampering** to demonstrate fraud detection in action (`🔴 TAMPERED! Alert at sequence #`).
   - Click **Repair Ledger** to restore integrity, then download the signed checkpoint JSON.

