# FilingGuard AI 🛡️

> **Deterministic Financial Filing Integrity Engine & Evidence-First Auditor**  
> Built for official SEC EDGAR 10-K Filings | Python 3.13 | FastAPI | Streamlit | LangGraph | SQLite

---

## Overview

**FilingGuard AI** is an evidence-first review aid for SEC Form 10-K filings. It supports extraction, deterministic checks, human review, and tamper-evident audit history; it does not certify the truth of company statements or eliminate all extraction errors.

Unlike black-box LLM extractors that guess financial figures, FilingGuard AI operates deterministically:
- Selects canonical financial metrics from **SEC Company Facts JSON** and parses **Inline XBRL** for comparison.
- Links facts to parsed source locations and local document hashes when those records are available; a local hash match proves consistency with the stored copy, not independent SEC authenticity.
- Executes **cross-source reconciliation** across 11 deterministic audit categories.
- Evaluates a deterministic **5-factor evidence-quality score** and routes low-quality or ambiguous metrics for human review; scores are not calibrated probabilities.
- Validates **14 deterministic accounting rules** (Balance Sheet Equation, Operating Presentation, YoY Variances, Cross-Statement Consistency).
- Manages human auditor oversight via **LangGraph agentic stateful workflows** with durable SQLite checkpointing and `interrupt()` pauses.
- Chains all state transitions and auditor decisions into an **insert-only, SHA-256 tamper-evident cryptographic audit ledger**.
- Evaluates multi-method performance against the configured SEC reference benchmark; the report displays the loaded dataset size and does not assume all reference filings are available locally.

---

## System Architecture

```
                                  [ Official SEC EDGAR ]
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
          [ SEC Company Facts API ]                   [ Primary 10-K Document ]
         (/api/xbrl/companyfacts/...)                (Inline XBRL / HTML Archive)
                       │                                           │
                       ▼                                           ▼
          [ Context Selector Engine ]                     [ Arelle Runner ]
       (Duration matching & selection)               (iXBRL parsing & SHA-256 hash)
                       │                                           │
                       └─────────────────────┬─────────────────────┘
                                             ▼
                          [ Cross-Source Reconciliation ]
                        (11 deterministic audit categories)
                                             │
                                             ▼
                         [ 5-Factor Confidence Scoring ]
           (Source 30%, Agreement 15%, Period 20%, Unit/Dimensions 10%, Mapping 25%)
                                             │
                                             ▼
                       [ Financial Validation Engine (14 Rules) ]
                    (Accounting Eq, YoY Variance, Cross-Statement)
                                             │
                                             ▼
                         [ LangGraph Agentic Workflow ]
                     (Durable SQLite checkpointing & routing)
                                             │
                          ┌──────────────────┴──────────────────┐
                          ▼                                     ▼
                  [ Auto-Pass Gate ]                   [ Human Review Gate ]
                 (All checks passed)                (Auditor APPROVE/CORRECT/REJECT)
                          │                                     │
                          └──────────────────┬──────────────────┘
                                             ▼
                      [ Tamper-Evident Audit Ledger ]
               (Canonical JSON, SHA-256 hash chain, HMAC export)
                                             │
                                             ▼
                    ┌────────────────────────┴────────────────────────┐
                    ▼                                                 ▼
          [ FastAPI REST API ]                             [ Streamlit Dashboard ]
           (Swagger docs at /docs)                         (Interactive Auditor UI)
```

---

## 10 Canonical Financial Metrics

FilingGuard AI extracts and reconciles 10 canonical GAAP financial metrics across financial statements:

1. **Revenue** (`RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`)
2. **Gross Profit** (`GrossProfit`)
3. **Operating Income** (`OperatingIncomeLoss`)
4. **Net Income** (`NetIncomeLoss`)
5. **Total Assets** (`Assets`)
6. **Total Liabilities** (`Liabilities`, `LiabilitiesCurrentAndNoncurrent`)
7. **Stockholders' Equity** (`StockholdersEquity`)
8. **Cash & Cash Equivalents** (`CashAndCashEquivalentsAtCarryingValue`)
9. **Operating Cash Flow** (`NetCashProvidedByUsedInOperatingActivities`)
10. **Capital Expenditure** (`PaymentsToAcquirePropertyPlantAndEquipment`)

---

## 14 Deterministic Accounting Rules

The engine evaluates 14 mathematical rules with zero hallucination:

1. **Balance Sheet Equation**: $\text{Assets} = \text{Liabilities} + \text{Stockholders' Equity}$ (with tolerance).
2. **Operating Income Presentation**: $\text{Gross Profit} - \text{Operating Expenses} = \text{Operating Income}$.
3. **YoY Revenue Variance**: Threshold $\pm 30\%$.
4. **YoY Net Income Variance**: Threshold $\pm 40\%$.
5. **YoY Gross Profit Variance**: Threshold $\pm 30\%$.
6. **YoY Operating Income Variance**: Threshold $\pm 35\%$.
7. **YoY Total Assets Variance**: Threshold $\pm 25\%$.
8. **YoY Total Liabilities Variance**: Threshold $\pm 30\%$.
9. **YoY Stockholders' Equity Variance**: Threshold $\pm 40\%$ (Auditor warning trigger).
10. **YoY Cash & Cash Equivalents Variance**: Threshold $\pm 50\%$.
11. **YoY Operating Cash Flow Variance**: Threshold $\pm 35\%$.
12. **YoY Capital Expenditure Variance**: Threshold $\pm 40\%$.
13. **Cross-Statement Net Income Consistency**: Income Statement Net Income vs Cash Flow Statement starting figure.
14. **Cross-Statement Cash Balance Consistency**: Balance Sheet Cash vs Cash Flow Statement ending figure.

---

## Quickstart Guide

### 1. Prerequisites & Environment Setup

```powershell
# Clone or navigate to the repository
cd d:\filingguard-ai

# Activate Python virtual environment
.venv\Scripts\Activate.ps1
```

### 2. Launch the full Streamlit dashboard

Configure `SEC_USER_AGENT` in `.env` with a descriptive application name and a real, monitored contact address before making SEC requests. Do not use the example placeholder from `.env.example`.

```powershell
.venv\Scripts\python.exe -m streamlit run dashboard\Home.py --server.port 8501
```

Open **`http://localhost:8501`**. This multipage dashboard provides company selection, extraction, validation, human review, benchmark reporting, and audit history.

### 3. Launch the FastAPI backend and lightweight HTML + Tailwind page

Start the FastAPI app first:

```powershell
.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **`http://localhost:8000/ui`** for the lightweight filing-status and confidence-scoring page. It is not a replacement for the full multipage Streamlit workflow.

The HTML page includes:
- Live health and database status cards
- Recent filing table with selection and detail inspection
- One-click scoring actions against the backend APIs
- Fast access to Swagger docs at `http://localhost:8000/docs`

- **Interactive API Documentation (Swagger)**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Modern UI**: `http://localhost:8000/ui`

---

## CLI Utilities

```powershell
# 1. Verify cryptographic audit chain integrity
.venv\Scripts\python.exe scripts\verify_audit_chain.py

# 2. Run the 3-baseline benchmark and print comparative metrics
.venv\Scripts\python.exe scripts\run_benchmark.py --persist

# 3. Preload and verify demo company filings in SQLite
.venv\Scripts\python.exe scripts\preload_demo_data.py
```

---

## Benchmark status

The local reference JSON contains 52 records across six companies. Its
`reviewer_verified` flags are dataset claims, not independently audited by the
benchmark loader; the current records do not include source URLs, exact fact
locators, or a documented verification method. The report therefore identifies
this provenance gap instead of presenting the reference sample as independently
verified ground truth.

In the observed local-database run, FilingGuard returned 28 exact matches out
of 52 reference cases; 24 predictions were missing because the corresponding
filing facts were not present in the local database. Of the 28 returned
predictions, 17 had a matching Inline XBRL locator linked to bytes whose local
SHA-256 matched the stored filing record. This local benchmark is not a live SEC
retrieval test.

The simple-tag baseline returned 10 exact matches out of the three-company
28-case cached subset, with 11 missing predictions. LLM and regex/table
baselines are marked **not evaluated**; the former had no execution path and
the previous regex simulation used reference values to generate predictions,
so those synthetic results have been disabled. Values above are an observed
local snapshot, not a performance guarantee.

---

## Test Suite Execution

To run all unit and live integration tests:

```powershell
.venv\Scripts\python.exe -m pytest -v
```

**Status**: **148 / 148 Tests Passing** across all 11 phases.
