"""
Pydantic schemas for SEC filing retrieval and metadata endpoints.
"""
from typing import List, Optional
from pydantic import BaseModel


class FilingResponse(BaseModel):
    accession_number: str
    cik: str
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    form_type: str
    filing_date: str
    report_period: Optional[str] = None
    primary_document: Optional[str] = None
    primary_doc_url: Optional[str] = None
    is_amendment: bool = False
    amends_accession: Optional[str] = None
    retrieved_at: Optional[str] = None


class RetrieveFilingRequest(BaseModel):
    cik_or_ticker: str
    form_type: str = "10-K"

