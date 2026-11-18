"""Transport models for the API's ancillary records.

Case/loop state is intentionally not duplicated here: the canonical
``careloop.loop_engine.ledger.LoopRecord`` is the API case model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


class Model:
    def model_dump(self) -> dict[str, Any]:
        result = asdict(self)
        for key, value in list(result.items()):
            if isinstance(value, datetime):
                result[key] = utc_iso(value)
        return result

    def dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass(frozen=True)
class User(Model):
    id: str
    name: str
    role: str
    patient_id: str | None = None


@dataclass(frozen=True)
class AuditEvent(Model):
    id: int
    case_id: str | None
    actor_id: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class ConsentRecord(Model):
    id: str
    case_id: str
    patient_id: str
    scope: str
    granted: bool
    recorded_by: str
    recorded_at: datetime


@dataclass(frozen=True)
class EvidenceRecord(Model):
    id: str
    case_id: str
    kind: str
    summary: str
    recorded_by: str
    recorded_at: datetime


@dataclass(frozen=True)
class Escalation(Model):
    id: str
    case_id: str
    reason: str
    target_role: str
    level: int
    created_at: datetime


@dataclass(frozen=True)
class Handoff(Model):
    id: str
    case_id: str
    from_user: str
    to_user: str
    note: str
    created_at: datetime


@dataclass(frozen=True)
class Appointment(Model):
    id: str
    case_id: str
    scheduled_for: str
    created_by: str
