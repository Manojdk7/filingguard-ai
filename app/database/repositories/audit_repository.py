import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.database.connection import get_db_connection

logger = logging.getLogger("filingguard.database.repositories.audit")


class AuditEventRecord(BaseModel):
    id: Optional[int] = None
    event_id: str
    sequence_num: int
    workflow_id: Optional[str] = None
    accession_number: Optional[str] = None
    metric_id: Optional[str] = None
    event_type: str
    actor: str
    payload: Dict[str, Any]
    previous_hash: str
    event_hash: str
    created_at: str
    signature: Optional[str] = None


class AuditRepository:
    """Repository for persisting and querying tamper-evident hash-chained audit events.

    This repository is strictly INSERT-ONLY: there are no UPDATE or DELETE methods.
    """

    def append_event(self, event: AuditEventRecord) -> AuditEventRecord:
        """Atomically append an audit event into the immutable ledger."""
        sql = """
        INSERT INTO audit_events (
            event_id, sequence_num, workflow_id, accession_number, metric_id,
            event_type, actor, payload_json, previous_hash, event_hash,
            created_at, signature
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        payload_str = json.dumps(event.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                sql,
                (
                    event.event_id,
                    event.sequence_num,
                    event.workflow_id,
                    event.accession_number,
                    event.metric_id,
                    event.event_type,
                    event.actor,
                    payload_str,
                    event.previous_hash,
                    event.event_hash,
                    event.created_at,
                    event.signature,
                ),
            )
            event.id = cursor.lastrowid
            conn.commit()
        logger.info(
            f"Appended audit event #{event.sequence_num} [{event.event_type}] "
            f"by {event.actor} (Hash: {event.event_hash[:12]}...)"
        )
        return event

    def get_latest_event(self) -> Optional[AuditEventRecord]:
        """Fetch the most recent event in the hash chain."""
        sql = "SELECT * FROM audit_events ORDER BY sequence_num DESC LIMIT 1;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_all_events(
        self,
        accession_number: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> List[AuditEventRecord]:
        """Fetch audit events in chronological sequence."""
        conditions = []
        params = []
        if accession_number:
            conditions.append("accession_number = ?")
            params.append(accession_number)
        if workflow_id:
            conditions.append("workflow_id = ?")
            params.append(workflow_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM audit_events {where_clause} ORDER BY sequence_num ASC;"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_event_by_id(self, event_id: str) -> Optional[AuditEventRecord]:
        """Fetch audit event by its unique event ID."""
        sql = "SELECT * FROM audit_events WHERE event_id = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_event_by_sequence(self, sequence_num: int) -> Optional[AuditEventRecord]:
        """Fetch audit event by its exact sequence number."""
        sql = "SELECT * FROM audit_events WHERE sequence_num = ?;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (sequence_num,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def count_events(self) -> int:
        """Count total audit events recorded."""
        sql = "SELECT COUNT(*) as total FROM audit_events;"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return int(row["total"]) if row else 0

    def find_duplicate(
        self,
        event_type: str,
        actor: str,
        accession_number: Optional[str],
        metric_id: Optional[str],
        payload: Dict[str, Any],
    ) -> Optional[AuditEventRecord]:
        """Check for existing event with identical type, actor, accession, metric, and payload."""
        payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        sql = """
        SELECT * FROM audit_events 
        WHERE event_type = ? AND actor = ? AND payload_json = ? 
        AND (accession_number IS ? OR accession_number = ?)
        AND (metric_id IS ? OR metric_id = ?)
        LIMIT 1;
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (event_type, actor, payload_str, accession_number, accession_number, metric_id, metric_id))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def _row_to_record(self, row: Any) -> AuditEventRecord:
        return AuditEventRecord(
            id=row["id"],
            event_id=row["event_id"],
            sequence_num=row["sequence_num"],
            workflow_id=row["workflow_id"],
            accession_number=row["accession_number"],
            metric_id=row["metric_id"],
            event_type=row["event_type"],
            actor=row["actor"],
            payload=json.loads(row["payload_json"] or "{}"),
            previous_hash=row["previous_hash"],
            event_hash=row["event_hash"],
            created_at=row["created_at"],
            signature=row["signature"],
        )

