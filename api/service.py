"""SQLite persistence adapter for the canonical E1-E9 ledger.

SQLite stores durable projections and transport records; all loop state and
closure decisions are created and validated by ``CareLoopLedger`` in
``careloop.loop_engine.ledger``.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from careloop.loop_engine.ledger import (
    CareLoopLedger,
    ClosureCode,
    ClosureError,
    HumanAuthorization,
    LoopEvent,
    LoopRecord,
    Patient,
    Urgency,
    LoopStatus,
    canonical_loop_id,
)
from careloop.loop_engine.errors import CareLoopError, NotFoundError, ValidationError

from .models import Appointment, AuditEvent, ConsentRecord, Escalation, EvidenceRecord, Handoff, User

SMALL_CELL_THRESHOLD = 10
ROLES = {"navigator", "clinician", "program_manager", "patient"}
STAFF_ROLES = {"navigator", "clinician", "program_manager"}


class AuthorizationError(CareLoopError):
    """The actor does not have access to the requested resource/action."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return value


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class CareLoopService:
    """Role-aware SQLite adapter backed by one canonical ledger instance."""

    def __init__(self, db_path: str = ":memory:", *, clock: Any = _now) -> None:
        self.db_path = db_path
        self.clock = clock
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        self.ledger = CareLoopLedger(clock=clock)
        self.loop = self.ledger
        self._restore_ledger()

    def close(self) -> None:
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None  # type: ignore[assignment]

    def __enter__(self) -> "CareLoopService":
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter cleanup fallback
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
                patient_id TEXT, CHECK(role IN ('navigator','clinician','program_manager','patient'))
            );
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY, loop_id TEXT NOT NULL UNIQUE, patient_id TEXT NOT NULL,
                title TEXT NOT NULL, reporter_org TEXT NOT NULL, owner_next TEXT NOT NULL,
                urgency TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
                high_risk INTEGER NOT NULL, opened_at TEXT NOT NULL, due_at TEXT NOT NULL,
                closed_at TEXT, closure_code TEXT, evidence_refs TEXT NOT NULL DEFAULT '[]',
                authorization_id TEXT
            );
            CREATE TABLE IF NOT EXISTS ledger_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, loop_id TEXT NOT NULL,
                event_type TEXT NOT NULL, timestamp TEXT NOT NULL, reporter_org TEXT NOT NULL,
                owner_next TEXT NOT NULL, due_at TEXT NOT NULL, evidence_ref TEXT
            );
            CREATE TABLE IF NOT EXISTS authorizations (
                id TEXT PRIMARY KEY, loop_id TEXT NOT NULL, authorized_by TEXT NOT NULL,
                rationale TEXT NOT NULL, authorized_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, actor_id TEXT NOT NULL,
                action TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS consents (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, patient_id TEXT NOT NULL,
                scope TEXT NOT NULL, granted INTEGER NOT NULL, recorded_by TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL,
                summary TEXT NOT NULL, recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS escalations (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, reason TEXT NOT NULL,
                target_role TEXT NOT NULL, level INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, from_user TEXT NOT NULL,
                to_user TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id TEXT PRIMARY KEY, case_id TEXT NOT NULL, scheduled_for TEXT NOT NULL,
                created_by TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teach_back (
                id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, outcome TEXT NOT NULL, answers TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def _restore_ledger(self) -> None:
        for row in self.db.execute("SELECT id,name,patient_id FROM users WHERE role = 'patient' ORDER BY id"):
            self.ledger.register_patient(Patient(row["id"], row["name"]))
        for row in self.db.execute("SELECT * FROM cases ORDER BY opened_at, id"):
            record = LoopRecord(
                loop_id=row["loop_id"],
                patient_id=row["patient_id"],
                reporter_org=row["reporter_org"],
                owner_next=row["owner_next"],
                urgency=Urgency(row["urgency"]),
                stage=row["stage"],
                created_at=_dt(row["opened_at"]) or self.clock(),
                due_at=_dt(row["due_at"]) or self.clock(),
                status=LoopStatus(row["status"]),
                high_risk=bool(row["high_risk"]),
                closure_code=ClosureCode(row["closure_code"]) if row["closure_code"] else None,
                evidence_refs=tuple(json.loads(row["evidence_refs"] or "[]")),
                authorization_id=row["authorization_id"],
                closed_at=_dt(row["closed_at"]),
            )
            self.ledger.restore_loop(record)
        for row in self.db.execute("SELECT * FROM ledger_events ORDER BY id"):
            self.ledger.restore_event(LoopEvent(
                row["loop_id"], row["event_type"], _dt(row["timestamp"]) or self.clock(),
                row["reporter_org"], row["owner_next"], _dt(row["due_at"]) or self.clock(), row["evidence_ref"],
            ))
        for row in self.db.execute("SELECT * FROM authorizations ORDER BY authorized_at"):
            self.ledger.restore_authorization(HumanAuthorization(
                row["id"], row["loop_id"], row["authorized_by"], row["rationale"],
                _dt(row["authorized_at"]) or self.clock(),
            ))

    def _user_row(self, actor_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM users WHERE id = ?", (actor_id,)).fetchone()
        if row is None:
            raise AuthorizationError(f"unknown actor: {actor_id}")
        return row

    def _user(self, actor_id: str) -> User:
        row = self._user_row(actor_id)
        return User(row["id"], row["name"], row["role"], row["patient_id"])

    def _case_row(self, case_id: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"case not found: {case_id}")
        return row

    def case_id_for_loop(self, loop_id: str) -> str:
        row = self.db.execute("SELECT id FROM cases WHERE loop_id = ?", (loop_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"case for loop not found: {loop_id}")
        return str(row["id"])

    def _record(self, case_id: str) -> LoopRecord:
        row = self._case_row(case_id)
        return self.ledger.get_loop(row["loop_id"])

    @staticmethod
    def _case_payload(case_id: str, title: str, record: LoopRecord) -> dict[str, Any]:
        value = record.to_dict()
        value.update({
            "id": case_id,
            "title": title,
            "owner_id": record.owner_next,
            "opened_at": value["created_at"],
            "closed_at": value["closed_at"],
            "closure_basis": "evidence" if record.evidence_refs else None,
        })
        return value

    def _allowed_case(self, actor_id: str, case_id: str, *, write: bool = False) -> tuple[User, LoopRecord]:
        user = self._user(actor_id)
        record = self._record(case_id)
        if user.role == "patient" and user.patient_id != record.patient_id:
            raise AuthorizationError("patient may only access their own case")
        if write and user.role == "patient" and user.patient_id != record.patient_id:
            raise AuthorizationError("patient may only change their own case")
        return user, record

    @staticmethod
    def _ensure_open(record: LoopRecord) -> None:
        if record.status is LoopStatus.CLOSED:
            raise ValidationError("closed case cannot be modified")

    def _audit(self, case_id: str | None, actor_id: str, action: str, payload: dict[str, Any] | None = None) -> AuditEvent:
        created = _iso(self.clock())
        cursor = self.db.execute(
            "INSERT INTO audit_log(case_id,actor_id,action,payload,created_at) VALUES(?,?,?,?,?)",
            (case_id, actor_id, action, json.dumps(payload or {}, sort_keys=True), created),
        )
        self.db.commit()
        return AuditEvent(cursor.lastrowid or 0, case_id, actor_id, action, payload or {}, _dt(created))

    def _persist_record(self, case_id: str, record: LoopRecord) -> None:
        self.db.execute(
            """UPDATE cases SET owner_next=?, urgency=?, stage=?, status=?, high_risk=?,
               due_at=?, closed_at=?, closure_code=?, evidence_refs=?, authorization_id=? WHERE id=?""",
            (
                record.owner_next, record.urgency.value, record.stage, record.status.value,
                int(record.high_risk), _iso(record.due_at), _iso(record.closed_at),
                record.closure_code.value if record.closure_code else None, json.dumps(list(record.evidence_refs)),
                record.authorization_id, case_id,
            ),
        )
        self.db.commit()

    def _store_event(self, event: LoopEvent) -> None:
        self.db.execute(
            "INSERT INTO ledger_events(loop_id,event_type,timestamp,reporter_org,owner_next,due_at,evidence_ref) VALUES(?,?,?,?,?,?,?)",
            (event.loop_id, event.event_type, _iso(event.timestamp), event.reporter_org, event.owner_next, _iso(event.due_at), event.evidence_ref),
        )
        self.db.commit()

    def register_user(self, user_id: str, name: str, role: str, *, patient_id: str | None = None) -> User:
        if role not in ROLES:
            raise ValidationError(f"unsupported role: {role}")
        if role == "patient" and not patient_id:
            patient_id = user_id
        try:
            self.db.execute("INSERT INTO users(id,name,role,patient_id) VALUES(?,?,?,?)", (user_id, name, role, patient_id))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"user already exists: {user_id}") from exc
        if role == "patient":
            self.ledger.register_patient(Patient(patient_id or user_id, name))
        return User(user_id, name, role, patient_id)

    def create_case(
        self, case_id: str, patient_id: str, title: str, owner_id: str, *, actor_id: str | None = None,
        stage: str = "result_issued", high_risk: bool = False, urgency: Urgency | str = Urgency.ROUTINE,
    ) -> LoopRecord:
        actor = actor_id or owner_id
        user = self._user(actor)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("only care-team roles can create cases")
        owner = self._user(owner_id)
        if owner.role not in STAFF_ROLES:
            raise ValidationError("owner must be a care-team user")
        patient = self.db.execute("SELECT 1 FROM users WHERE id = ? AND role = 'patient'", (patient_id,)).fetchone()
        if patient is None:
            raise NotFoundError(f"patient not found: {patient_id}")
        if stage not in {item.stage for item in self.ledger.stages}:
            raise ValidationError(f"unknown canonical stage: {stage}")
        if stage != "result_issued":
            raise ValidationError("new cases must start at result_issued")
        if self.db.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone() is not None:
            raise ValidationError(f"case already exists: {case_id}")
        loop_id = canonical_loop_id(case_id, namespace="api-loop")
        record = self.ledger.create_loop(patient_id, f"api:{owner_id}", owner_id, urgency=urgency, loop_id=loop_id, high_risk=high_risk)
        opened = _iso(record.created_at)
        self.db.execute(
            "INSERT INTO cases(id,loop_id,patient_id,title,reporter_org,owner_next,urgency,stage,status,high_risk,opened_at,due_at,closed_at,closure_code,evidence_refs,authorization_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, record.loop_id, patient_id, title, record.reporter_org, record.owner_next, record.urgency.value, record.stage, record.status.value, int(record.high_risk), opened, _iso(record.due_at), None, None, "[]", None),
        )
        self.db.commit()
        self._audit(case_id, actor, "case_created", {"owner_id": owner_id, "stage": record.stage, "loop_id": record.loop_id})
        return record

    def list_cases(self, actor_id: str, *, status: str | None = None, patient_id: str | None = None) -> list[LoopRecord]:
        user = self._user(actor_id)
        query = "SELECT id FROM cases WHERE 1=1"
        params: list[Any] = []
        if user.role == "patient":
            query += " AND patient_id = ?"
            params.append(user.patient_id)
        elif patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at, id"
        return [self._record(row["id"]) for row in self.db.execute(query, params)]

    def list_case_summaries(self, actor_id: str, *, status: str | None = None, patient_id: str | None = None) -> list[dict[str, Any]]:
        user = self._user(actor_id)
        query = "SELECT id, title, loop_id FROM cases WHERE 1=1"
        params: list[Any] = []
        if user.role == "patient":
            query += " AND patient_id = ?"
            params.append(user.patient_id)
        elif patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY opened_at, id"
        return [
            self._case_payload(str(row["id"]), row["title"], self.ledger.get_loop(row["loop_id"]))
            for row in self.db.execute(query, params)
        ]

    def get_case(self, actor_id: str, case_id: str) -> dict[str, Any]:
        _, record = self._allowed_case(actor_id, case_id)
        row = self._case_row(case_id)
        return self._detail(case_id, row["title"], record)

    def _detail(self, case_id: str, title: str, record: LoopRecord) -> dict[str, Any]:
        detail = self._case_payload(case_id, title, record)
        detail["events"] = [
            {**dict(item.to_dict()), "timestamp": item.timestamp.isoformat(), "due_at": item.due_at.isoformat()}
            for item in self.ledger.events(record.loop_id)
        ]
        detail["consents"] = [self._consent(row).model_dump() for row in self.db.execute("SELECT * FROM consents WHERE case_id = ? ORDER BY recorded_at", (case_id,))]
        detail["evidence"] = [self._evidence(row).model_dump() for row in self.db.execute("SELECT * FROM evidence WHERE case_id = ? ORDER BY recorded_at", (case_id,))]
        detail["escalations"] = [self._escalation(row).model_dump() for row in self.db.execute("SELECT * FROM escalations WHERE case_id = ? ORDER BY created_at", (case_id,))]
        detail["handoffs"] = [self._handoff(row).model_dump() for row in self.db.execute("SELECT * FROM handoffs WHERE case_id = ? ORDER BY created_at", (case_id,))]
        detail["appointments"] = [self._appointment(row).model_dump() for row in self.db.execute("SELECT * FROM appointments WHERE case_id = ? ORDER BY scheduled_for", (case_id,))]
        return detail

    @staticmethod
    def _consent(row: sqlite3.Row) -> ConsentRecord:
        return ConsentRecord(row["id"], row["case_id"], row["patient_id"], row["scope"], bool(row["granted"]), row["recorded_by"], _dt(row["recorded_at"]))

    @staticmethod
    def _evidence(row: sqlite3.Row) -> EvidenceRecord:
        return EvidenceRecord(row["id"], row["case_id"], row["kind"], row["summary"], row["recorded_by"], _dt(row["recorded_at"]))

    @staticmethod
    def _escalation(row: sqlite3.Row) -> Escalation:
        return Escalation(row["id"], row["case_id"], row["reason"], row["target_role"], row["level"], _dt(row["created_at"]))

    @staticmethod
    def _handoff(row: sqlite3.Row) -> Handoff:
        return Handoff(row["id"], row["case_id"], row["from_user"], row["to_user"], row["note"], _dt(row["created_at"]))

    @staticmethod
    def _appointment(row: sqlite3.Row) -> Appointment:
        return Appointment(row["id"], row["case_id"], row["scheduled_for"], row["created_by"])

    def record_consent(self, case_id: str, actor_id: str, scope: str, granted: bool, *, consent_id: str | None = None) -> ConsentRecord:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in ROLES:
            raise AuthorizationError("role cannot record consent")
        item = ConsentRecord(consent_id or f"consent-{case_id}-{scope}", case_id, record.patient_id, scope, bool(granted), actor_id, self.clock())
        try:
            self.db.execute("INSERT INTO consents VALUES(?,?,?,?,?,?,?)", (item.id, item.case_id, item.patient_id, item.scope, int(item.granted), item.recorded_by, _iso(item.recorded_at)))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"consent already exists: {item.id}") from exc
        self._audit(case_id, actor_id, "consent_recorded", {"scope": scope, "granted": bool(granted)})
        return item

    def record_evidence(self, case_id: str, actor_id: str, kind: str, summary: str, *, evidence_id: str | None = None) -> EvidenceRecord:
        user, _ = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot record evidence")
        item = EvidenceRecord(evidence_id or f"evidence-{case_id}-{uuid4().hex[:12]}", case_id, kind, summary, actor_id, self.clock())
        try:
            self.db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?)", (item.id, item.case_id, item.kind, item.summary, item.recorded_by, _iso(item.recorded_at)))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"evidence already exists: {item.id}") from exc
        self._audit(case_id, actor_id, "evidence_recorded", {"evidence_id": item.id, "kind": kind})
        return item

    def transition_case(self, case_id: str, actor_id: str, stage: str) -> LoopRecord:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot transition cases")
        if record.status is LoopStatus.CLOSED:
            raise ValidationError("closed cases cannot transition")
        mapping = next((item for item in self.ledger.stages if item.stage == record.stage), None)
        if mapping is None or mapping.next_stage != stage:
            raise ValidationError(f"invalid canonical transition {record.stage} -> {stage}")
        event = self.ledger.record_event(record.loop_id, mapping.expected_event_type, reporter_org=record.reporter_org, owner_next=record.owner_next)
        self._store_event(event)
        updated = self.ledger.get_loop(record.loop_id)
        self._persist_record(case_id, updated)
        self._audit(case_id, actor_id, "stage_changed", {"from": record.stage, "to": stage, "event_type": event.event_type})
        return updated

    def escalate_case(self, case_id: str, actor_id: str, reason: str, *, target_role: str = "program_manager", level: int = 1) -> Escalation:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot escalate cases")
        self._ensure_open(record)
        if target_role not in STAFF_ROLES or level < 1:
            raise ValidationError("invalid escalation target or level")
        item = Escalation(f"escalation-{case_id}-{uuid4().hex[:12]}", case_id, reason or "case stalled", target_role, level, self.clock())
        self.db.execute("INSERT INTO escalations VALUES(?,?,?,?,?,?)", (item.id, item.case_id, item.reason, item.target_role, item.level, _iso(item.created_at)))
        self.db.commit()
        self._audit(case_id, actor_id, "case_escalated", {"reason": item.reason, "target_role": target_role, "level": level})
        return item

    def handoff_case(self, case_id: str, actor_id: str, to_user: str, note: str = "") -> Handoff:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in {"navigator", "program_manager"}:
            raise AuthorizationError("only navigator or program manager can hand off")
        self._ensure_open(record)
        recipient = self._user(to_user)
        if recipient.role not in STAFF_ROLES:
            raise ValidationError("handoff recipient must be on the care team")
        item = Handoff(f"handoff-{case_id}-{uuid4().hex[:12]}", case_id, actor_id, to_user, note, self.clock())
        self.db.execute("INSERT INTO handoffs VALUES(?,?,?,?,?,?)", (item.id, item.case_id, item.from_user, item.to_user, item.note, _iso(item.created_at)))
        row = self._case_row(case_id)
        self.db.execute("UPDATE cases SET owner_next = ? WHERE id = ?", (to_user, case_id))
        self.db.commit()
        current = self._record(case_id)
        updated = self.ledger.assign_owner(current.loop_id, to_user)
        self._audit(case_id, actor_id, "case_handed_off", {"from_user": actor_id, "to_user": to_user, "note": note})
        return item

    def schedule_appointment(self, case_id: str, actor_id: str, scheduled_for: str, *, appointment_id: str | None = None) -> Appointment:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot schedule appointments")
        self._ensure_open(record)
        item = Appointment(appointment_id or f"appointment-{case_id}-{uuid4().hex[:12]}", case_id, scheduled_for, actor_id)
        try:
            self.db.execute("INSERT INTO appointments VALUES(?,?,?,?)", (item.id, case_id, scheduled_for, actor_id))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"appointment already exists: {item.id}") from exc
        self._audit(case_id, actor_id, "appointment_scheduled", {"appointment_id": item.id, "scheduled_for": scheduled_for})
        return item

    def teach_back(self, case_id: str, actor_id: str, outcome: str, answers: Iterable[Any] = ()) -> dict[str, Any]:
        user, _ = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in {"patient", *STAFF_ROLES}:
            raise AuthorizationError("role cannot record teach-back")
        created = _iso(self.clock())
        values = list(answers)
        self.db.execute("INSERT INTO teach_back(case_id,actor_id,outcome,answers,created_at) VALUES(?,?,?,?,?)", (case_id, actor_id, outcome, json.dumps(values), created))
        self.db.commit()
        self._audit(case_id, actor_id, "teach_back_recorded", {"outcome": outcome})
        return {"case_id": case_id, "actor_id": actor_id, "outcome": outcome, "answers": values, "created_at": created}

    def authorize_closure(self, case_id: str, actor_id: str, *, authorization_id: str, authorized_by: str, rationale: str) -> HumanAuthorization:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("only care-team roles can authorize closure")
        self._ensure_open(record)
        authorizer = self._user(authorized_by)
        if authorizer.role not in STAFF_ROLES:
            raise AuthorizationError("closure authorization must be human care-team authorization")
        authorization = self.ledger.authorize_high_risk(record.loop_id, authorization_id=authorization_id, authorized_by=authorized_by, rationale=rationale)
        try:
            self.db.execute("INSERT INTO authorizations VALUES(?,?,?,?,?)", (authorization.authorization_id, authorization.loop_id, authorization.authorized_by, authorization.rationale, _iso(authorization.authorized_at)))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"authorization already exists: {authorization_id}") from exc
        self._audit(case_id, actor_id, "closure_authorized", {"authorization_id": authorization_id, "authorized_by": authorized_by})
        return authorization

    def close_case(self, case_id: str, actor_id: str, *, evidence_id: str | None = None, closure_code: ClosureCode | str | None = None, authorization_id: str | None = None, authorized_by: str | None = None, rationale: str | None = None, closure_basis: str | None = None) -> LoopRecord:
        user, record = self._allowed_case(actor_id, case_id, write=True)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot close cases")
        if record.status is not LoopStatus.OPEN:
            raise ValidationError("case is already closed")
        if closure_basis:
            raise ClosureError("free-text closure basis cannot close a case; use closure_code and evidence_id")
        if not evidence_id:
            raise ClosureError("closure requires a mandatory evidence reference")
        evidence = self.db.execute("SELECT 1 FROM evidence WHERE id = ? AND case_id = ?", (evidence_id, case_id)).fetchone()
        if evidence is None:
            raise ClosureError("evidence reference does not belong to case")
        if closure_code is None:
            raise ClosureError("closure requires a typed closure code")
        if record.high_risk and not record.authorization_id:
            if not authorization_id or not authorized_by or not rationale:
                raise ClosureError("high-risk closure requires human authorization")
            self.authorize_closure(case_id, actor_id, authorization_id=authorization_id, authorized_by=authorized_by, rationale=rationale)
            record = self._record(case_id)
        contract = self.ledger.check_closure_contract(record.loop_id, closure_code=closure_code, evidence_refs=(evidence_id,))
        now = self.clock()
        event = self.ledger.record_closure_event(record.loop_id, reporter_org=record.reporter_org, owner_next=record.owner_next, evidence_ref=evidence_id, timestamp=now, due_at=now)
        self._store_event(event)
        closed = self.ledger.close_loop(record.loop_id, closure_code=contract.closure_code, evidence_refs=contract.evidence_refs)
        self._persist_record(case_id, closed)
        self._audit(case_id, actor_id, "case_closed", {"evidence_id": evidence_id, "closure_code": closed.closure_code.value if closed.closure_code else None})
        return closed

    def action(self, case_id: str, actor_id: str, action: str, payload: dict[str, Any] | None = None) -> Any:
        data = payload or {}
        if action == "acknowledge":
            user, _ = self._allowed_case(actor_id, case_id, write=True)
            if user.role not in {"patient", *STAFF_ROLES}:
                raise AuthorizationError("role cannot acknowledge")
            return self._audit(case_id, actor_id, "case_acknowledged", data).model_dump()
        if action == "transition":
            return self._case_payload(case_id, self._case_row(case_id)["title"], self.transition_case(case_id, actor_id, str(data.get("stage", ""))))
        if action == "escalate":
            return self.escalate_case(case_id, actor_id, str(data.get("reason", "case stalled")), target_role=str(data.get("target_role", "program_manager")), level=int(data.get("level", 1))).model_dump()
        if action == "handoff":
            return self.handoff_case(case_id, actor_id, str(data.get("to_user", "")), str(data.get("note", ""))).model_dump()
        if action == "evidence":
            return self.record_evidence(case_id, actor_id, str(data.get("kind", "documentation")), str(data.get("summary", "")), evidence_id=data.get("evidence_id")).model_dump()
        if action == "consent":
            return self.record_consent(case_id, actor_id, str(data.get("scope", "care_coordination")), bool(data.get("granted", False)), consent_id=data.get("consent_id")).model_dump()
        if action == "appointment":
            return self.schedule_appointment(case_id, actor_id, str(data.get("scheduled_for", "")), appointment_id=data.get("appointment_id")).model_dump()
        if action == "teach_back":
            return self.teach_back(case_id, actor_id, str(data.get("outcome", "needs_human_follow_up")), data.get("answers", []))
        if action == "authorize_closure":
            authorization = self.authorize_closure(case_id, actor_id, authorization_id=str(data["authorization_id"]), authorized_by=str(data["authorized_by"]), rationale=str(data["rationale"]))
            return {"authorization_id": authorization.authorization_id, "loop_id": authorization.loop_id, "authorized_by": authorization.authorized_by, "rationale": authorization.rationale, "authorized_at": authorization.authorized_at.isoformat()}
        if action == "close":
            closed = self.close_case(case_id, actor_id, evidence_id=data.get("evidence_id"), closure_code=data.get("closure_code"), authorization_id=data.get("authorization_id"), authorized_by=data.get("authorized_by"), rationale=data.get("rationale"), closure_basis=data.get("closure_basis"))
            return self._case_payload(case_id, self._case_row(case_id)["title"], closed)
        raise ValidationError(f"unknown case action: {action}")

    def audit(self, actor_id: str, *, case_id: str | None = None) -> list[AuditEvent]:
        user = self._user(actor_id)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot view audit log")
        if case_id:
            self._allowed_case(actor_id, case_id)
            rows = self.db.execute("SELECT * FROM audit_log WHERE case_id = ? ORDER BY id", (case_id,))
        else:
            rows = self.db.execute("SELECT * FROM audit_log ORDER BY id")
        return [AuditEvent(row["id"], row["case_id"], row["actor_id"], row["action"], json.loads(row["payload"]), _dt(row["created_at"])) for row in rows]

    def analytics(self, actor_id: str, *, group_by: str = "stage") -> dict[str, Any]:
        user = self._user(actor_id)
        if user.role not in STAFF_ROLES:
            raise AuthorizationError("patients cannot view aggregate analytics")
        if group_by not in {"stage", "status", "owner_next"}:
            raise ValidationError("group_by must be stage, status, or owner_next")
        counts: dict[str, int] = {}
        for row in self.db.execute(f"SELECT {group_by} AS bucket, COUNT(*) AS count FROM cases GROUP BY {group_by} ORDER BY {group_by}"):
            counts[str(row["bucket"])] = int(row["count"])
        return {"group_by": group_by, "threshold": SMALL_CELL_THRESHOLD, "groups": [{"key": key, "count": value if value >= SMALL_CELL_THRESHOLD else None, "suppressed": value < SMALL_CELL_THRESHOLD} for key, value in counts.items()]}

    def fhir_export(self, actor_id: str, case_id: str) -> dict[str, Any]:
        _, record = self._allowed_case(actor_id, case_id)
        row = self._case_row(case_id)
        detail = self._detail(case_id, row["title"], record)
        patient_ref = {"reference": f"Patient/{record.patient_id}"}
        task_ref = {"reference": f"Task/{case_id}-task"}
        entries: list[dict[str, Any]] = [
            {"resource": {"resourceType": "Task", "id": f"{case_id}-task", "status": "completed" if record.status is LoopStatus.CLOSED else "in-progress", "intent": "order", "for": patient_ref, "description": row["title"]}},
            {"resource": {"resourceType": "Communication", "id": f"{case_id}-communication", "status": "completed", "subject": patient_ref, "basedOn": [task_ref], "payload": [{"contentString": "CareLoop patient communication reference"}]}},
            {"resource": {"resourceType": "ServiceRequest", "id": f"{case_id}-service-request", "status": "completed" if record.status is LoopStatus.CLOSED else "active", "intent": "order", "subject": patient_ref, "basedOn": [task_ref]}},
        ]
        for appointment in detail["appointments"]:
            entries.append({"resource": {"resourceType": "Appointment", "id": appointment["id"], "status": "fulfilled" if record.status is LoopStatus.CLOSED else "booked", "participant": [{"actor": patient_ref}], "start": appointment["scheduled_for"], "basedOn": [task_ref]}})
        for evidence in detail["evidence"]:
            entries.append({"resource": {"resourceType": "DiagnosticReport", "id": evidence["id"], "status": "final", "code": {"text": evidence["kind"]}, "subject": patient_ref, "conclusion": evidence["summary"], "basedOn": [task_ref]}})
        return {"resourceType": "Bundle", "type": "collection", "meta": {"tag": [{"code": "not-conformance-tested"}]}, "conformance_tested": False, "label": "R4-like export; not conformance-tested", "entry": entries}

    def load_demo_data(self, *, seed: int = 20261019, case_count: int = 12) -> dict[str, Any]:
        if isinstance(case_count, bool) or not isinstance(case_count, int) or not 1 <= case_count <= 100:
            raise ValidationError("case_count must be an integer between 1 and 100")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValidationError("seed must be an integer")
        rng = random.Random(seed)
        users = [("navigator-1", "Nadia Navigator", "navigator", None), ("clinician-1", "Dr. Casey Clinician", "clinician", None), ("manager-1", "Morgan Program Manager", "program_manager", None)] + [(f"patient-{index:02d}", f"Synthetic Patient {index:02d}", "patient", f"patient-{index:02d}") for index in range(1, case_count + 1)]
        for row in users:
            if self.db.execute("SELECT 1 FROM users WHERE id = ?", (row[0],)).fetchone() is None:
                self.register_user(row[0], row[1], row[2], patient_id=row[3])
        for index in range(1, case_count + 1):
            case_id = f"demo-case-{index:02d}"
            if self.db.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone() is None:
                self.create_case(case_id, f"patient-{index:02d}", f"Synthetic screening follow-up {index:02d}", "navigator-1", actor_id="manager-1")
                if index % 4 == 0:
                    self.record_consent(case_id, f"patient-{index:02d}", "care_coordination", True)
                if index % 4 == 0:
                    self.transition_case(case_id, "navigator-1", "notification")
        return {"seed": seed, "users": len(users), "cases": len(self.list_cases("manager-1")), "sampled_value": rng.randrange(1000)}

    def run_stalled_case_scenario(self, *, actor_id: str = "manager-1") -> dict[str, Any]:
        self.load_demo_data()
        case_id = "demo-stalled-case"
        existing = self.db.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone()
        if existing is not None:
            record = self._record(case_id)
            if record.status is LoopStatus.CLOSED:
                return {"case": self._case_payload(case_id, self._case_row(case_id)["title"], record), "steps": ["already_closed"], "audit": [event.model_dump() for event in self.audit(actor_id, case_id=case_id)]}
        else:
            self.create_case(case_id, "patient-01", "Synthetic stalled screening case", "navigator-1", actor_id=actor_id)
        self._audit(case_id, actor_id, "stall_detected", {"reason": "follow-up acknowledgement overdue"})
        escalation = self.escalate_case(case_id, actor_id, "follow-up acknowledgement overdue", target_role="program_manager")
        handoff = self.handoff_case(case_id, actor_id, "clinician-1", "Escalation accepted for clinical handoff")
        evidence = self.record_evidence(case_id, "clinician-1", "confirmatory_result", "Synthetic evidence reviewed by clinician")
        # The scripted scenario advances the same E1-E9 graph used by the API
        # before recording the terminal E9 evidence event.
        for _ in range(10):
            current = self._record(case_id)
            mapping = next(item for item in self.ledger.stages if item.stage == current.stage)
            if mapping.next_stage is None:
                break
            event = self.ledger.record_event(
                current.loop_id,
                mapping.expected_event_type,
                reporter_org=current.reporter_org,
                owner_next=current.owner_next,
            )
            self._store_event(event)
            self._persist_record(case_id, self.ledger.get_loop(current.loop_id))
        closed = self.close_case(case_id, "clinician-1", evidence_id=evidence.id, closure_code=ClosureCode.COMPLETED)
        return {"case": self._case_payload(case_id, self._case_row(case_id)["title"], closed), "steps": ["stall_detected", escalation.model_dump(), handoff.model_dump(), evidence.model_dump(), "evidence_closure"], "audit": [event.model_dump() for event in self.audit(actor_id, case_id=case_id)]}

    # The legacy URL prefix remains an alias for the same canonical ledger,
    # rather than a second API service or a second domain model.
    def create_transport_loop(self, payload: dict[str, Any]) -> dict[str, Any]:
        patient_id = str(payload["patient_id"])
        if patient_id not in self.ledger._patients:
            self.ledger.register_patient(Patient(patient_id, patient_id, str(payload.get("language", "English")), str(payload.get("distance", "unknown")), str(payload.get("barrier", "none")), str(payload.get("companion", "no")), str(payload.get("payer", "unknown"))))
        record = self.ledger.create_loop(patient_id, str(payload.get("reporter_org", "screening-org")), str(payload["owner_next"]), urgency=Urgency(str(payload.get("urgency", "routine"))), loop_id=payload.get("loop_id"), high_risk=bool(payload.get("high_risk", False)))
        return record.to_dict()

    def get_transport_loop(self, loop_id: str) -> dict[str, Any]:
        return self.ledger.get_loop(loop_id).to_dict()

    def record_transport_event(self, loop_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = payload.get("timestamp")
        due_at = payload.get("due_at")
        event = self.ledger.record_event(loop_id, str(payload["event_type"]), reporter_org=str(payload["reporter_org"]), owner_next=str(payload["owner_next"]), timestamp=datetime.fromisoformat(str(timestamp)) if timestamp else None, due_at=datetime.fromisoformat(str(due_at)) if due_at else None, evidence_ref=payload.get("evidence_ref"))
        return {**event.to_dict(), "timestamp": event.timestamp.isoformat(), "due_at": event.due_at.isoformat()}

    def transport_absence(self, loop_id: str) -> list[dict[str, Any]]:
        self.ledger.get_loop(loop_id)
        return [{"loop_id": item.loop_id, "expected_next_event": item.expected_next_event, "deadline": item.deadline.isoformat(), "urgency": item.urgency.value, "reported_at": item.reported_at.isoformat(), "visibility": item.visibility} for item in self.ledger.daily_absence_report() if item.loop_id == loop_id]

    def close_transport_loop(self, loop_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.ledger.get_loop(loop_id)
        if record.status is LoopStatus.CLOSED:
            raise ValidationError("closed loops cannot receive closure events")
        if payload.get("authorized_by"):
            self.ledger.authorize_high_risk(loop_id, authorization_id=str(payload.get("authorization_id", f"auth-{loop_id}")), authorized_by=str(payload["authorized_by"]), rationale=str(payload.get("rationale", "authorized human decision")))
        evidence_refs = tuple(str(item) for item in payload.get("evidence_refs", []))
        contract = self.ledger.check_closure_contract(loop_id, closure_code=payload.get("closure_code"), evidence_refs=evidence_refs)
        now = self.clock()
        self.ledger.record_closure_event(loop_id, reporter_org=record.reporter_org, owner_next=record.owner_next, evidence_ref=contract.evidence_refs[0], timestamp=now, due_at=now)
        return self.ledger.close_loop(loop_id, closure_code=contract.closure_code, evidence_refs=contract.evidence_refs).to_dict()


__all__ = ["AuthorizationError", "CareLoopError", "CareLoopService", "ClosureError", "NotFoundError", "ValidationError"]
