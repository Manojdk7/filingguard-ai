# FilingGuard AI — System Architecture

## Architecture Overview

FilingGuard AI is structured as a layered, evidence-first financial auditing pipeline designed for deterministic reproducibility and human-in-the-loop governance.

```
┌────────────────────────────────────────────────────────┐
│                   Presentation Layer                   │
│   FastAPI (REST API at /docs) | Streamlit (Port 8501)   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Workflow Layer                      │
│       LangGraph Agentic StateGraph (7-Node Pipeline)    │
│      Durable Checkpointing via SQLite Checkpointer     │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Auditing Engines                    │
│   1. Extraction: SEC Company Facts + Arelle iXBRL      │
│   2. Reconciliation: 11 Deterministic Audit Categories │
│   3. Scoring: 5-Factor Composite Quality [0.0, 1.0]    │
│   4. Validation: 14 Deterministic Accounting Rules     │
│   5. Human Review: Idempotent Decision Loop & Overrides │
│   6. Benchmark: 3-Method Comparative Evaluation Engine │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Integrity Layer                     │
│    Tamper-Evident SHA-256 Linear Audit Ledger Chain    │
│            HMAC-SHA256 Signed Checkpoints              │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                    Storage Layer                       │
│           SQLite (data/database/filingguard.db)        │
│        Filesystem Cache (data/cache/, data/filings/)   │
└────────────────────────────────────────────────────────┘
```

## Security & Access Policies
- SEC EDGAR HTTP requests adhere to published access policies (<10 requests/sec with custom `User-Agent` header).
- Response cache prevents redundant SEC network lookups via SHA-256 keying.
- All reviewer identities are validated to reject automated agents (`bot`, `system`, `ai`).

