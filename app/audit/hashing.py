import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

GENESIS_PREVIOUS_HASH = "0" * 64


def canonical_json(data: Any) -> str:
    """Serialize data to a deterministic, canonical JSON string.

    Guarantees:
    - Stable, sorted dictionary keys.
    - Compact representation with no superfluous whitespace (separators=(',', ':')).
    - Explicit handling of None / null.
    - Preserves Unicode without escaping.
    - Fallback conversion of non-serializable objects (e.g. Decimal, datetime) via default=str.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def calculate_event_hash(previous_hash: str, payload: Any, created_at: str) -> str:
    """Calculate the cryptographic SHA-256 hash for an audit ledger event.

    Formula:
        event_hash = sha256(previous_hash + canonical_json(payload) + created_at).hexdigest()
    """
    serialized_payload = canonical_json(payload)
    raw_bytes = f"{previous_hash}{serialized_payload}{created_at}".encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def sign_checkpoint(payload_hash: str, secret_key: Optional[str] = None) -> str:
    """Cryptographic HMAC-SHA256 signature for exportable audit checkpoints and ledger verification."""
    import hmac
    from app.config import settings
    key = secret_key or settings.AUDIT_SIGNING_SECRET
    return hmac.new(key.encode("utf-8"), payload_hash.encode("utf-8"), hashlib.sha256).hexdigest()

