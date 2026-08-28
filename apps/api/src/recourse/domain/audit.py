import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recourse.domain.models import AuditEvent
from recourse.persistence.tables import AuditRow


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def append_audit(session: Session, *, case_id: str, event_type: str, payload: dict,
                 actor_id: str = "deterministic-engine-v1", input_hash: str | None = None,
                 output_hash: str | None = None) -> AuditEvent:
    previous = session.scalar(select(AuditRow).where(AuditRow.case_id == case_id).order_by(AuditRow.sequence.desc()))
    sequence = (previous.sequence + 1) if previous else 1
    created_at = datetime.now(timezone.utc)
    core = {
        "case_id": case_id, "sequence": sequence, "event_type": event_type,
        "actor_type": "SYSTEM", "actor_id": actor_id, "input_hash": input_hash,
        "output_hash": output_hash, "payload_redacted": payload,
        "previous_event_hash": previous.event_hash if previous else None,
        "created_at": created_at.isoformat(),
    }
    event_hash = sha256_json(core)
    model = AuditEvent(audit_id=f"aud_{uuid.uuid4().hex}", event_hash=event_hash, **core)
    session.add(AuditRow(
        id=model.audit_id, case_id=case_id, sequence=sequence, event_type=event_type,
        actor_type=model.actor_type, actor_id=actor_id, input_hash=input_hash,
        output_hash=output_hash, payload_redacted_json=canonical_json(payload),
        previous_event_hash=model.previous_event_hash, event_hash=event_hash, created_at=created_at,
    ))
    session.flush()
    return model


def verify_chain(rows: list[AuditRow]) -> bool:
    previous_hash = None
    for row in rows:
        core = {
            "case_id": row.case_id, "sequence": row.sequence, "event_type": row.event_type,
            "actor_type": row.actor_type, "actor_id": row.actor_id, "input_hash": row.input_hash,
            "output_hash": row.output_hash, "payload_redacted": json.loads(row.payload_redacted_json),
            "previous_event_hash": row.previous_event_hash, "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        }
        if row.previous_event_hash != previous_hash or sha256_json(core) != row.event_hash:
            return False
        previous_hash = row.event_hash
    return True
