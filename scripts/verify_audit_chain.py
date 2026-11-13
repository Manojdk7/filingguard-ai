"""
CLI script to cryptographically verify the audit ledger hash chain.
Usage: python scripts/verify_audit_chain.py [--accession <accession_number>]
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.audit.verification import AuditVerifier
from app.database.connection import check_db_health


def main():
    parser = argparse.ArgumentParser(description="Cryptographically verify FilingGuard audit ledger hash chain.")
    parser.add_argument("--accession", type=str, default=None, help="Filter verification to specific filing accession.")
    args = parser.parse_args()

    if not check_db_health():
        print("ERROR: Database connection offline.", file=sys.stderr)
        sys.exit(1)

    verifier = AuditVerifier()
    res = verifier.verify_chain(accession_number=args.accession)

    print("=" * 60)
    print(" FILINGGUARD AI — AUDIT LEDGER CHAIN VERIFICATION")
    print("=" * 60)
    print(f"Scope:          {'All Events' if not args.accession else args.accession}")
    print(f"Events Checked: {res.total_events}")
    print(f"Chain Status:   {'VALID' if res.is_valid else 'TAMPERED!'}")
    print(f"Latest Hash:    {res.latest_event_hash or 'None'}")

    if not res.is_valid:
        print(f"\nALERT! Tampering detected at sequence #{res.first_tampered_sequence}")
        print(f"Reason: {res.failure_reason}")
        sys.exit(2)
    else:
        print("\nSUCCESS: All cryptographic event hashes and linear pointer links verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()

