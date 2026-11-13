from app.audit.hashing import (
    GENESIS_PREVIOUS_HASH,
    calculate_event_hash,
    canonical_json,
    sign_checkpoint,
)


def test_canonical_json_key_ordering():
    """Test 1: Dictionaries with different key insertion orders produce identical canonical strings."""
    dict1 = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    dict2 = {"a": 1, "c": {"x": 10, "y": 20}, "b": 2}

    json1 = canonical_json(dict1)
    json2 = canonical_json(dict2)

    assert json1 == json2
    assert json1 == '{"a":1,"b":2,"c":{"x":10,"y":20}}'


def test_canonical_json_data_types():
    """Test 2: Explicit handling of None, booleans, floats, and Unicode characters."""
    payload = {
        "is_audited": True,
        "notes": None,
        "amount": 1000000.5,
        "symbol": "€ / ¥ / $",
    }
    serialized = canonical_json(payload)
    assert '"is_audited":true' in serialized
    assert '"notes":null' in serialized
    assert '"symbol":"€ / ¥ / $"' in serialized
    assert " " not in serialized.replace("€ / ¥ / $", "")  # No extra whitespace


def test_event_hash_calculation_determinism():
    """Test 3: Event hash calculation is strictly deterministic."""
    prev_hash = GENESIS_PREVIOUS_HASH
    payload = {"metric": "revenue", "value": 391035000000.0}
    timestamp = "2026-01-01T00:00:00Z"

    hash1 = calculate_event_hash(prev_hash, payload, timestamp)
    hash2 = calculate_event_hash(prev_hash, payload, timestamp)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert isinstance(hash1, str)

    # Any change alters the hash
    altered_hash = calculate_event_hash(prev_hash, {"metric": "revenue", "value": 391035000001.0}, timestamp)
    assert altered_hash != hash1


def test_checkpoint_signature_generation():
    """Test 4: Signed checkpoint HMAC signature is deterministic and tamper-evident."""
    h = "a" * 64
    sig1 = sign_checkpoint(h, secret_key="test_key")
    sig2 = sign_checkpoint(h, secret_key="test_key")

    assert sig1 == sig2
    assert len(sig1) == 64

    # Different hash produces different signature
    sig_diff = sign_checkpoint("b" * 64, secret_key="test_key")
    assert sig_diff != sig1

