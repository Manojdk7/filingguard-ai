import logging
import sqlite3
from typing import Optional
from app.config import settings

logger = logging.getLogger("filingguard.database.models")

CREATE_FILINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filings (
    accession_number TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    company_name TEXT,
    ticker TEXT,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    report_period TEXT,
    primary_document TEXT,
    primary_doc_url TEXT,
    is_amendment INTEGER NOT NULL DEFAULT 0,
    amends_accession TEXT,
    retrieved_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_filings_cik_form ON filings(cik, form_type);
"""

CREATE_FACTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS company_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cik TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    raw_value REAL NOT NULL,
    normalized_value REAL NOT NULL,
    unit TEXT NOT NULL,
    taxonomy TEXT NOT NULL,
    concept TEXT NOT NULL,
    period_type TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_period TEXT NOT NULL,
    form TEXT NOT NULL,
    filed_date TEXT,
    frame TEXT,
    status TEXT NOT NULL, -- 'selected', 'ambiguous', 'candidate', 'rejected'
    selection_explanation TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_facts_accn_metric ON company_facts(accession_number, metric_id);
CREATE INDEX IF NOT EXISTS idx_facts_cik_fy ON company_facts(cik, fiscal_year);
"""

CREATE_DOWNLOADED_DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS downloaded_documents (
    accession_number TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    primary_document TEXT NOT NULL,
    source_url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);
"""

CREATE_XBRL_FACTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS xbrl_parsed_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    namespace TEXT NOT NULL,
    is_custom INTEGER NOT NULL DEFAULT 0,
    value TEXT,
    numeric_value REAL,
    unit TEXT,
    context_id TEXT NOT NULL,
    period_type TEXT NOT NULL, -- 'instant' or 'duration'
    start_date TEXT,
    end_date TEXT NOT NULL,
    is_segment INTEGER NOT NULL DEFAULT 0,
    dimensions_json TEXT, -- JSON map of dimensions and members
    source_locator TEXT,
    source_doc_hash TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_xbrl_facts_accn ON xbrl_parsed_facts(accession_number);
CREATE INDEX IF NOT EXISTS idx_xbrl_facts_concept ON xbrl_parsed_facts(concept_name);
CREATE INDEX IF NOT EXISTS idx_xbrl_facts_segment ON xbrl_parsed_facts(accession_number, is_segment);
"""

CREATE_RECONCILIATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cross_source_reconciliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    cik TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    status TEXT NOT NULL, -- e.g., 'exact_match', 'value_mismatch', 'missing_company_facts', etc.
    company_facts_value REAL,
    ixbrl_value REAL,
    difference REAL,
    company_facts_concept TEXT,
    ixbrl_concept TEXT,
    company_facts_unit TEXT,
    ixbrl_unit TEXT,
    company_facts_period TEXT,
    ixbrl_period TEXT,
    is_segment_mismatch INTEGER NOT NULL DEFAULT 0,
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_recon_accn ON cross_source_reconciliations(accession_number);
CREATE INDEX IF NOT EXISTS idx_recon_metric ON cross_source_reconciliations(accession_number, metric_id);
"""

CREATE_CUSTOM_CONCEPT_CANDIDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS custom_concept_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    custom_concept TEXT NOT NULL,
    namespace TEXT NOT NULL,
    candidate_metric_id TEXT,
    candidate_metric_name TEXT,
    confidence_level TEXT NOT NULL, -- 'candidate_for_review', 'unresolved'
    reason TEXT NOT NULL,
    is_reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_custom_concept_accn ON custom_concept_candidates(accession_number);
"""

CREATE_METRIC_CONFIDENCE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metric_confidence_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    cik TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    quality_score_100 REAL NOT NULL,
    status TEXT NOT NULL,
    review_category TEXT NOT NULL,
    factors_json TEXT NOT NULL,
    positive_factors_json TEXT NOT NULL,
    negative_factors_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    explanation TEXT NOT NULL,
    review_recommendations_json TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_metric_scores_accn_metric ON metric_confidence_scores(accession_number, metric_id);
"""

CREATE_FILING_CONFIDENCE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS filing_confidence_scores (
    accession_number TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    overall_score REAL NOT NULL,
    quality_score_100 REAL NOT NULL,
    overall_status TEXT NOT NULL,
    overall_review_category TEXT NOT NULL,
    metrics_assessed_count INTEGER NOT NULL,
    metrics_missing_count INTEGER NOT NULL,
    critical_metrics_present INTEGER NOT NULL DEFAULT 1,
    score_factors_json TEXT NOT NULL,
    reduction_reasons_json TEXT NOT NULL,
    summary_explanation TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);
"""

CREATE_FINANCIAL_VALIDATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS financial_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accession_number TEXT NOT NULL,
    cik TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    validation_category TEXT NOT NULL,
    status TEXT NOT NULL, -- 'PASS', 'FAIL', 'WARNING', 'NOT_EVALUATED'
    expected_value REAL,
    actual_value REAL,
    absolute_difference REAL,
    relative_difference REAL,
    configured_tolerance REAL,
    input_metrics_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    explanation TEXT NOT NULL,
    failure_reason TEXT,
    recommendation TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_validations_accn_rule ON financial_validations(accession_number, rule_id);
CREATE INDEX IF NOT EXISTS idx_validations_status ON financial_validations(status);
"""

CREATE_HUMAN_REVIEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS human_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT UNIQUE NOT NULL,
    accession_number TEXT NOT NULL,
    thread_id TEXT,
    metric_id TEXT,
    canonical_name TEXT,
    review_round INTEGER NOT NULL DEFAULT 1,
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL, -- 'APPROVED', 'CORRECTED', 'REJECTED'
    original_value REAL,
    corrected_value REAL,
    unit TEXT,
    comment TEXT NOT NULL,
    evidence_used TEXT,
    idempotency_key TEXT UNIQUE,
    previous_validation_status TEXT,
    new_validation_status TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(accession_number) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_human_reviews_accn ON human_reviews(accession_number);
CREATE INDEX IF NOT EXISTS idx_human_reviews_metric ON human_reviews(accession_number, metric_id);
CREATE INDEX IF NOT EXISTS idx_human_reviews_idemp ON human_reviews(idempotency_key);
"""

CREATE_AUDIT_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    sequence_num INTEGER UNIQUE NOT NULL,
    workflow_id TEXT,
    accession_number TEXT,
    metric_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    signature TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_events_seq ON audit_events(sequence_num);
CREATE INDEX IF NOT EXISTS idx_audit_events_accn ON audit_events(accession_number);
CREATE INDEX IF NOT EXISTS idx_audit_events_wf ON audit_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_hash ON audit_events(event_hash);
"""


CREATE_BENCHMARK_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_id TEXT UNIQUE NOT NULL,
    filing_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    method TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    expected_value REAL,
    expected_unit TEXT,
    expected_period TEXT,
    predicted_value REAL,
    predicted_unit TEXT,
    predicted_period TEXT,
    result TEXT NOT NULL,
    reviewer_reference TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    FOREIGN KEY(filing_id) REFERENCES filings(accession_number)
);

CREATE INDEX IF NOT EXISTS idx_bench_accn ON benchmark_results(filing_id);
CREATE INDEX IF NOT EXISTS idx_bench_case ON benchmark_results(test_case_id);
CREATE INDEX IF NOT EXISTS idx_bench_method ON benchmark_results(method);
"""


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables and indexes."""
    target_path = db_path or str(settings.sqlite_db_path)
    with sqlite3.connect(target_path) as conn:
        conn.executescript(CREATE_FILINGS_TABLE_SQL)
        conn.executescript(CREATE_FACTS_TABLE_SQL)
        conn.executescript(CREATE_DOWNLOADED_DOCUMENTS_TABLE_SQL)
        conn.executescript(CREATE_XBRL_FACTS_TABLE_SQL)
        conn.executescript(CREATE_RECONCILIATION_TABLE_SQL)
        conn.executescript(CREATE_CUSTOM_CONCEPT_CANDIDATES_TABLE_SQL)
        conn.executescript(CREATE_METRIC_CONFIDENCE_TABLE_SQL)
        conn.executescript(CREATE_FILING_CONFIDENCE_TABLE_SQL)
        conn.executescript(CREATE_FINANCIAL_VALIDATIONS_TABLE_SQL)
        conn.executescript(CREATE_HUMAN_REVIEWS_TABLE_SQL)
        conn.executescript(CREATE_AUDIT_EVENTS_TABLE_SQL)
        conn.executescript(CREATE_BENCHMARK_RESULTS_TABLE_SQL)
        conn.commit()
    logger.info("Database schemas initialized.")
