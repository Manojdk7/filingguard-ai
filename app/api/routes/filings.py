"""
API routes for SEC Filing Retrieval and Metadata.
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas.filing import FilingResponse, RetrieveFilingRequest
from app.database.repositories.filing_repository import FilingRecord, FilingRepository
from app.sec.client import SECClient, InvalidCIKError, SECClientError
from app.sec.filing_index import FilingIndexResolver
from app.sec.submissions import SubmissionsManager, UnknownTickerError

logger = logging.getLogger("filingguard.api.routes.filings")

router = APIRouter(prefix="/filings", tags=["SEC Filings"])

_filing_repo = FilingRepository()


@router.get("", response_model=List[FilingResponse])
def list_filings(limit: int = Query(50, ge=1, le=200)):
    """List recent SEC filings recorded in the database."""
    try:
        filings = _filing_repo.get_recent_filings(limit=limit)
        return [
            FilingResponse(
                accession_number=f.accession_number,
                cik=f.cik,
                company_name=f.company_name,
                ticker=f.ticker,
                form_type=f.form_type,
                filing_date=f.filing_date,
                report_period=f.report_period,
                primary_document=f.primary_document,
                primary_doc_url=f.primary_doc_url,
                is_amendment=f.is_amendment,
                amends_accession=f.amends_accession,
                retrieved_at=f.retrieved_at,
            )
            for f in filings
        ]
    except Exception as e:
        logger.error(f"Error fetching filings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{accession_number}", response_model=FilingResponse)
def get_filing(accession_number: str):
    """Retrieve metadata for a specific filing by accession number."""
    clean_accn = accession_number.strip()
    filing = _filing_repo.get_by_accession(clean_accn)
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filing with accession number '{clean_accn}' not found.",
        )
    return FilingResponse(
        accession_number=filing.accession_number,
        cik=filing.cik,
        company_name=filing.company_name,
        ticker=filing.ticker,
        form_type=filing.form_type,
        filing_date=filing.filing_date,
        report_period=filing.report_period,
        primary_document=filing.primary_document,
        primary_doc_url=filing.primary_doc_url,
        is_amendment=filing.is_amendment,
        amends_accession=filing.amends_accession,
        retrieved_at=filing.retrieved_at,
    )


@router.post("/ingest", response_model=FilingResponse, status_code=status.HTTP_201_CREATED)
def ingest_filing_from_sec(request: RetrieveFilingRequest):
    """Retrieve and store official 10-K filing metadata from SEC EDGAR by CIK or ticker."""
    target = request.cik_or_ticker.strip().upper()
    if not target:
        raise HTTPException(status_code=400, detail="CIK or ticker is required.")
    if request.form_type.strip().upper() != "10-K":
        raise HTTPException(status_code=400, detail="Only 10-K filings are currently supported.")

    try:
        sec_client = SECClient()
        sub_mgr = SubmissionsManager(client=sec_client)
        resolver = FilingIndexResolver(client=sec_client)

        cik = sub_mgr.resolve_cik(target)
        submissions_data = sub_mgr.fetch_submissions(cik)
        filing = sub_mgr.select_latest_10k(submissions_data)

        if not filing:
            raise HTTPException(
                status_code=404,
                detail=f"No eligible {request.form_type} filing found for CIK '{cik}'.",
            )

        filing = resolver.resolve_primary_document_url(filing)
        _filing_repo.save(filing)

        return FilingResponse(
            accession_number=filing.accession_number,
            cik=filing.cik,
            company_name=filing.company_name,
            ticker=filing.ticker,
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            report_period=filing.report_period,
            primary_document=filing.primary_document,
            primary_doc_url=filing.primary_doc_url,
            is_amendment=filing.is_amendment,
            amends_accession=filing.amends_accession,
            retrieved_at=filing.retrieved_at,
        )
    except HTTPException:
        raise
    except InvalidCIKError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnknownTickerError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SECClientError as e:
        logger.error(f"SEC upstream request failed for {target}: {e}")
        raise HTTPException(status_code=502, detail=f"SEC retrieval failed: {str(e)}")
    except Exception as e:
        logger.error(f"Error ingesting filing from SEC for {target}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"SEC retrieval failed: {str(e)}",
        )
