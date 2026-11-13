import logging
import re
import threading
import time
from typing import Any, Dict, Optional
import httpx
from app.config import settings
from app.sec.cache import SECCache

logger = logging.getLogger("filingguard.sec.client")


class SECClientError(Exception):
    """Base exception for SEC Client operations."""
    pass


class InvalidCIKError(SECClientError):
    """Raised when an invalid CIK is provided."""
    pass


class SECRequestError(SECClientError):
    """Raised when an HTTP or network error occurs communicating with SEC."""
    pass


class SECRateLimiter:
    """Enforces fair access rate limiting (SEC maximum is 10 requests per second)."""

    def __init__(self, min_interval_seconds: float = 0.15):
        self.min_interval = min_interval_seconds
        self.last_request_time = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.monotonic()


# Global rate limiter instance across calls
_global_rate_limiter = SECRateLimiter()


def normalize_cik(cik: Any) -> str:
    """
    Normalizes a CIK to exactly 10 digits with leading zeroes.
    Rejects strings/integers with non-digits or empty inputs.
    """
    if cik is None:
        raise InvalidCIKError("CIK cannot be None")

    cik_str = str(cik).strip()
    if not cik_str:
        raise InvalidCIKError("CIK cannot be empty")

    if not re.match(r"^\d+$", cik_str):
        raise InvalidCIKError(f"Invalid CIK '{cik}': must contain only numeric digits")

    if len(cik_str) > 10:
        raise InvalidCIKError(f"Invalid CIK '{cik}': exceeds maximum 10 digits")

    return cik_str.zfill(10)


def normalize_accession_number(accession_number: Any) -> str:
    """Validate the structure of an SEC accession number."""
    if accession_number is None:
        raise ValueError("Accession number cannot be None")
    value = str(accession_number).strip()
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", value):
        raise ValueError(f"Invalid SEC accession number '{value}'")
    return value


class SECClient:
    """
    Official SEC EDGAR API client with rate limiting, retries with exponential backoff,
    and automatic caching.
    """

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: Optional[int] = None,
        cache: Optional[SECCache] = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.user_agent = user_agent or settings.SEC_USER_AGENT
        if not self.user_agent or "example.com" in self.user_agent:
            logger.warning(
                "SEC_USER_AGENT appears to be unset or using example.com. "
                "SEC requires a descriptive User-Agent with valid contact info."
            )
        self.timeout = timeout or settings.SEC_REQUEST_TIMEOUT
        self.cache = cache or SECCache()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limiter = _global_rate_limiter

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov"
        }

    def _headers_for_url(self, url: str) -> Dict[str, str]:
        headers = self.get_headers()
        if "www.sec.gov" in url:
            headers["Host"] = "www.sec.gov"
        return headers

    def get_json(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Fetches JSON from the specified SEC endpoint with caching and retry logic.
        """
        if use_cache:
            cached_data = self.cache.get(url)
            if cached_data is not None:
                return cached_data

        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait()
                logger.debug(f"Fetching SEC URL: {url} (attempt {attempt + 1})")
                
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=self._headers_for_url(url))

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise SECRequestError(
                            f"SEC returned malformed JSON for {url}"
                        ) from exc
                    if not isinstance(data, dict):
                        raise SECRequestError(
                            f"SEC returned an unexpected JSON shape for {url}"
                        )
                    if use_cache:
                        self.cache.set(url, data)
                    return data
                elif response.status_code in (429, 500, 502, 503, 504):
                    last_exception = SECRequestError(
                        f"SEC returned temporary HTTP {response.status_code} for {url}"
                    )
                    logger.warning(
                        f"Temporary SEC HTTP {response.status_code} for {url}. "
                        f"Retrying in {self.backoff_factor * (2 ** attempt):.2f}s..."
                    )
                    if attempt < self.max_retries:
                        time.sleep(self.backoff_factor * (2 ** attempt))
                    continue
                elif response.status_code == 404:
                    raise SECRequestError(f"SEC Resource not found (404) at {url}")
                else:
                    raise SECRequestError(f"SEC returned unexpected status {response.status_code} for {url}")

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exception = exc
                wait_time = self.backoff_factor * (2 ** attempt)
                logger.warning(f"Network error accessing {url}: {exc}. Retrying in {wait_time:.2f}s...")
                if attempt < self.max_retries:
                    time.sleep(wait_time)

        raise SECRequestError(
            f"Failed to fetch SEC resource after {self.max_retries + 1} attempts for {url}: {last_exception}"
        )

    def get_bytes(self, url: str) -> bytes:
        """Fetch a non-JSON SEC resource with the same rate limit and retry policy."""
        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait()
                logger.debug(f"Fetching SEC document: {url} (attempt {attempt + 1})")
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=self._headers_for_url(url))

                if response.status_code == 200:
                    return response.content
                if response.status_code in (429, 500, 502, 503, 504):
                    last_exception = SECRequestError(
                        f"SEC returned temporary HTTP {response.status_code} for {url}"
                    )
                    delay = self.backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Temporary SEC HTTP %s for %s. Retrying in %.2fs...",
                        response.status_code,
                        url,
                        delay,
                    )
                    if attempt < self.max_retries:
                        time.sleep(delay)
                    continue
                raise SECRequestError(
                    f"SEC returned HTTP {response.status_code} for {url}"
                )
            except httpx.RequestError as exc:
                last_exception = exc
                delay = self.backoff_factor * (2 ** attempt)
                logger.warning(
                    "Network error downloading SEC resource %s: %s. Retrying in %.2fs...",
                    url,
                    exc,
                    delay,
                )
                if attempt < self.max_retries:
                    time.sleep(delay)

        raise SECRequestError(
            f"Failed to fetch SEC document after {self.max_retries + 1} attempts "
            f"for {url}: {last_exception}"
        )
