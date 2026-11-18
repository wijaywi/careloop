"""Canonical E1-E9 transport ledger and care-loop domain model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Optional

from .errors import ClosureError, DuplicateEntityError, NotFoundError, ValidationError


class Urgency(str, Enum):
    """The SLA lane used for a loop."""

    URGENT = "urgent"
    ROUTINE = "routine"


class LoopStatus(str, Enum):
    """Lifecycle status of a care loop."""

    OPEN = "open"
    CLOSED = "closed"


class ClosureCode(str, Enum):
    """Typed, auditable reasons for closing a loop."""

    COMPLETED = "Completed"
    DECLINED_INFORMED = "Declined-informed"
    UNREACHABLE_DOCUMENTED = "Unreachable-documented"
    MOVED_PROVIDER = "Moved-provider"
    NO_ACTION_NEEDED = "No-action-needed"
    DECEASED = "Deceased"


class HandoffStatus(str, Enum):
    """State of a positive handoff."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Patient:
    """Minimal non-clinical patient context held by the canonical ledger."""

    patient_id: str
    name: str
    language: str = ""
    distance: str = ""
    barrier: str = ""
    companion: str = ""
    payer: str = ""


class EConsultStatus(str, Enum):
    """State of an e-consult request."""

    REQUESTED = "requested"
    RESOLVED_WITHOUT_REFERRAL = "resolved-without-referral"
    REFERRAL_REQUIRED = "referral-required"


EVENT_TYPES = tuple(f"E{number}" for number in range(1, 10))
EVENT_FIELDS = (
    "loop_id",
    "event_type",
    "timestamp",
    "reporter_org",
    "owner_next",
    "due_at",
    "evidence_ref",
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("timestamps must be timezone-aware")
    return value


def canonical_loop_id(patient_reference: str, *, namespace: str = "careloop", salt: str = "") -> str:
    """Create a deterministic pseudonymous identifier without exposing identity."""

    if not patient_reference:
        raise ValidationError("patient reference is required")
    material = f"{namespace}\x1f{salt}\x1f{patient_reference}".encode("utf-8")
    return f"loop_{hashlib.sha256(material).hexdigest()[:32]}"


# Friendly aliases used by integrations that describe the operation as a factory.
generate_loop_id = canonical_loop_id
pseudonymous_loop_id = canonical_loop_id


@dataclass(frozen=True, slots=True)
class LoopEvent:
    """The complete E1-E9 transport event; it has no clinical-content field."""

    loop_id: str
    event_type: str
    timestamp: datetime
    reporter_org: str
    owner_next: str
    due_at: datetime
    evidence_ref: Optional[str]

    def __post_init__(self) -> None:
        if not self.loop_id or self.event_type not in EVENT_TYPES:
            raise ValidationError("loop_id and an E1-E9 event_type are required")
        if not self.reporter_org or not self.owner_next:
            raise ValidationError("reporter_org and owner_next are required")
        if self.event_type == "E9" and not self.evidence_ref:
            raise ValidationError("E9 closure events require evidence_ref")
        _aware(self.timestamp)
        _aware(self.due_at)

    def to_dict(self) -> dict[str, object]:
        """Serialize exactly the seven exchange fields."""

        return {name: getattr(self, name) for name in EVENT_FIELDS}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "LoopEvent":
        """Parse an event and reject fields that could carry clinical content."""

        if set(value) != set(EVENT_FIELDS):
            raise ValidationError("an event must contain exactly the seven V2 event fields")
        return cls(**{name: value[name] for name in EVENT_FIELDS})  # type: ignore[arg-type]


EventV2 = LoopEvent


@dataclass(frozen=True, slots=True)
class VisibilityGap:
    """An explicit unknown state caused by a partner reporting failure."""

    loop_id: str
    expected_event_type: str
    detected_at: datetime
    deadline: datetime
    urgency: Urgency
    reporter_org: str
    reason: str = "partner reporting failure"
    status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.expected_event_type not in EVENT_TYPES:
            raise ValidationError("expected_event_type must be E1-E9")
        if self.status != "UNKNOWN":
            raise ValidationError("visibility gaps must remain explicitly UNKNOWN")
        _aware(self.detected_at)
        _aware(self.deadline)


VisibilityGapV2 = VisibilityGap


@dataclass(frozen=True, slots=True)
class StageMapping:
    """One row in the eleven-stage operational mapping."""

    stage: str
    expected_event_type: str
    next_stage: Optional[str]


_STAGES = (
    "result_issued",
    "notification",
    "acknowledgement",
    "confirmatory_test",
    "e_consult",
    "referral",
    "referral_acceptance",
    "appointment",
    "attendance",
    "treatment",
    "closure",
)
_STAGE_EVENTS = ("E1", "E2", "E3", "E4", "E5", "E5", "E6", "E6", "E7", "E8", "E9")
ELEVEN_STAGE_MAPPING = tuple(
    StageMapping(stage, event, _STAGES[index + 1] if index + 1 < len(_STAGES) else None)
    for index, (stage, event) in enumerate(zip(_STAGES, _STAGE_EVENTS))
)
STAGE_MAPPING = MappingProxyType({item.stage: item.expected_event_type for item in ELEVEN_STAGE_MAPPING})
DEFAULT_STAGE_MAPPING = STAGE_MAPPING
STAGE_NAMES = _STAGES


def _parse_duration(value: object) -> timedelta:
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        hours = float(value)
    elif isinstance(value, str):
        text = value.strip().lower()
        units = (("days", 24.0), ("day", 24.0), ("d", 24.0), ("hours", 1.0), ("hour", 1.0), ("h", 1.0))
        for suffix, factor in units:
            if text.endswith(suffix):
                hours = float(text[: -len(suffix)].strip()) * factor
                break
        else:
            hours = float(text)
    else:
        raise ValidationError("SLA values must be hours or duration strings")
    if hours <= 0:
        raise ValidationError("SLA durations must be positive")
    return timedelta(hours=hours)


@dataclass(frozen=True, slots=True)
class SLATable:
    """Urgent and routine stage deadlines loaded from JSON-compatible YAML."""

    values: Mapping[str, Mapping[str, timedelta]]

    def __post_init__(self) -> None:
        normalized: dict[str, dict[str, timedelta]] = {}
        for urgency in Urgency:
            source = self.values.get(urgency.value, {})
            if not source:
                raise ValidationError(f"missing {urgency.value} SLA table")
            row = {str(stage): _parse_duration(duration) for stage, duration in source.items()}
            if "default" not in row and not set(_STAGES).issubset(row):
                raise ValidationError("SLA table needs every stage or a default")
            normalized[urgency.value] = row
        object.__setattr__(self, "values", MappingProxyType({key: MappingProxyType(row) for key, row in normalized.items()}))

    def duration(self, urgency: Urgency | str, stage: str) -> timedelta:
        row = self.values[Urgency(urgency).value]
        return row.get(stage, row.get("default", timedelta(hours=24)))


SlaTable = SLATable


def _minimal_yaml(text: str) -> dict[str, dict[str, object]]:
    """Parse the small mapping-only YAML subset used by SLA configuration."""

    result: dict[str, dict[str, object]] = {}
    section: Optional[str] = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            section = line[:-1].strip()
            result[section] = {}
            continue
        if section is None or ":" not in line:
            raise ValidationError("SLA text is not valid JSON-compatible YAML")
        key, raw_value = line.strip().split(":", 1)
        value = raw_value.strip().strip('"\'')
        try:
            parsed: object = float(value) if "." in value else int(value)
        except ValueError:
            parsed = value
        result[section][key.strip()] = parsed
    return result


def load_sla_table(source: Mapping[str, Mapping[str, object]] | str | Path) -> SLATable:
    """Load urgent/routine SLAs from a mapping, JSON text, or a YAML file."""

    if isinstance(source, Path):
        source = source.read_text(encoding="utf-8")
    if isinstance(source, str) and Path(source).is_file():
        source = Path(source).read_text(encoding="utf-8")
    if isinstance(source, str):
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            data = _minimal_yaml(source)
    else:
        data = source
    if not isinstance(data, Mapping):
        raise ValidationError("SLA configuration must be a mapping")
    return SLATable(data)  # type: ignore[arg-type]


DEFAULT_SLA_TABLE = load_sla_table(
    {
        "urgent": {
            "result_issued": 1,
            "notification": 24,
            "acknowledgement": 48,
            "confirmatory_test": 168,
            "e_consult": 24,
            "referral": 48,
            "referral_acceptance": 24,
            "appointment": 72,
            "attendance": 24,
            "treatment": 168,
            "closure": 168,
        },
        "routine": {
            "result_issued": 1,
            "notification": 168,
            "acknowledgement": 336,
            "confirmatory_test": 720,
            "e_consult": 48,
            "referral": 336,
            "referral_acceptance": 48,
            "appointment": 336,
            "attendance": 72,
            "treatment": 336,
            "closure": 336,
        },
    }
)


@dataclass(frozen=True, slots=True)
class LoopRecord:
    """Current operational state of a loop."""

    loop_id: str
    patient_id: str
    reporter_org: str
    owner_next: str
    urgency: Urgency
    stage: str
    created_at: datetime
    due_at: datetime
    status: LoopStatus = LoopStatus.OPEN
    high_risk: bool = False
    closure_code: Optional[ClosureCode] = None
    evidence_refs: tuple[str, ...] = ()
    authorization_id: Optional[str] = None
    closed_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly snapshot of the canonical loop record."""

        return {
            "loop_id": self.loop_id,
            "patient_id": self.patient_id,
            "reporter_org": self.reporter_org,
            "owner_next": self.owner_next,
            "urgency": self.urgency.value,
            "stage": self.stage,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "status": self.status.value,
            "high_risk": self.high_risk,
            "closure_code": self.closure_code.value if self.closure_code else None,
            "evidence_refs": list(self.evidence_refs),
            "authorization_id": self.authorization_id,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }

    model_dump = to_dict


@dataclass(frozen=True, slots=True)
class AbsenceReport:
    """A daily report row for an expected event that has not arrived."""

    loop_id: str
    expected_next_event: str
    deadline: datetime
    urgency: Urgency
    reported_at: datetime
    visibility: str = "ABSENT"


@dataclass(frozen=True, slots=True)
class Handoff:
    """A handoff whose sender owns the loop until explicit acceptance."""

    handoff_id: str
    loop_id: str
    sender_owner: str
    destination: str
    status: HandoffStatus = HandoffStatus.PROPOSED
    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    alternative_destination: Optional[str] = None


@dataclass(frozen=True, slots=True)
class EConsult:
    """An e-consult with a mandatory question and minimal data package."""

    consult_id: str
    loop_id: str
    requester_org: str
    destination_org: str
    clinical_question: str
    minimal_data_package: Mapping[str, object]
    status: EConsultStatus = EConsultStatus.REQUESTED
    resolution: Optional[str] = None
    referral_destination: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.clinical_question.strip() or not self.minimal_data_package:
            raise ValidationError("e-consult requires a clinical question and minimal data package")


@dataclass(frozen=True, slots=True)
class PatientPassport:
    """The minimum patient context available to a pull contact."""

    patient_id: str
    language: str
    distance: str
    barrier: str
    companion: str
    payer: str


@dataclass(frozen=True, slots=True)
class PatientContact:
    """A documented pull-contact attempt."""

    loop_id: str
    patient_id: str
    contact_method: str
    contacted_at: datetime
    reporter_org: str


@dataclass(frozen=True, slots=True)
class ResultPassport:
    """A one-page operational passport for patient-facing follow-up."""

    loop_id: str
    meaning: str
    urgency: Urgency
    next_step_owner: str
    no_contact_instruction: str
    teach_back_required: bool = True


@dataclass(frozen=True, slots=True)
class HumanAuthorization:
    """Human authorization required before a high-risk closure."""

    authorization_id: str
    loop_id: str
    authorized_by: str
    rationale: str
    authorized_at: datetime


@dataclass(frozen=True, slots=True)
class ClosureContract:
    """Closure prerequisites evaluated by the contract gate."""

    loop_id: str
    closure_code: ClosureCode
    evidence_refs: tuple[str, ...]
    human_authorization: Optional[HumanAuthorization] = None


@dataclass(frozen=True, slots=True)
class EscalationAssessment:
    """A hook result for the likelihood that escalation succeeds."""

    loop_id: str
    probability: float
    urgency: Urgency
    level: int


EscalationProbabilityHook = Callable[[LoopRecord, int], float]


class CareLoopLedger:
    """In-memory service implementing the canonical E1-E9 domain contract."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        sla_table: SLATable | Mapping[str, Mapping[str, object]] | str | Path = DEFAULT_SLA_TABLE,
        escalation_probability_hook: Optional[EscalationProbabilityHook] = None,
    ) -> None:
        self._clock = clock
        self._sla = sla_table if isinstance(sla_table, SLATable) else load_sla_table(sla_table)
        self._probability_hook = escalation_probability_hook
        self._patients: dict[str, Patient] = {}
        self._loops: dict[str, LoopRecord] = {}
        self._events: list[LoopEvent] = []
        self._gaps: list[VisibilityGap] = []
        self._handoffs: dict[str, Handoff] = {}
        self._consults: dict[str, EConsult] = {}
        self._contacts: list[PatientContact] = []
        self._passports: dict[str, ResultPassport] = {}
        self._authorizations: dict[str, HumanAuthorization] = {}

    @property
    def stages(self) -> tuple[StageMapping, ...]:
        """Return the configured eleven-stage mapping."""

        return ELEVEN_STAGE_MAPPING

    def _now(self) -> datetime:
        return _aware(self._clock())

    def register_patient(self, patient: Patient) -> Patient:
        if patient.patient_id in self._patients:
            raise DuplicateEntityError(patient.patient_id)
        self._patients[patient.patient_id] = patient
        return patient

    def _loop(self, loop_id: str) -> LoopRecord:
        try:
            return self._loops[loop_id]
        except KeyError as exc:
            raise NotFoundError(f"loop {loop_id!r} not found") from exc

    def create_loop(
        self,
        patient_id: str,
        reporter_org: str,
        owner_next: str,
        *,
        urgency: Urgency | str = Urgency.ROUTINE,
        loop_id: Optional[str] = None,
        high_risk: bool = False,
    ) -> LoopRecord:
        """Open a loop with a canonical pseudonymous identifier."""

        if patient_id not in self._patients:
            raise NotFoundError(f"patient {patient_id!r} not found")
        if not reporter_org or not owner_next:
            raise ValidationError("reporter_org and owner_next are required")
        canonical = loop_id or canonical_loop_id(patient_id)
        if not (
            canonical.startswith("loop_")
            and len(canonical) == 37
            and all(char in "0123456789abcdef" for char in canonical[5:])
        ):
            raise ValidationError("loop_id must be a canonical pseudonymous loop identifier")
        if canonical in self._loops:
            raise DuplicateEntityError(canonical)
        lane = Urgency(urgency)
        now = self._now()
        record = LoopRecord(canonical, patient_id, reporter_org, owner_next, lane, _STAGES[0], now, now + self._sla.duration(lane, _STAGES[0]), high_risk=high_risk)
        self._loops[canonical] = record
        return record

    def record_event(
        self,
        loop_id: str,
        event_type: str,
        *,
        reporter_org: str,
        owner_next: Optional[str] = None,
        due_at: Optional[datetime] = None,
        evidence_ref: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> LoopEvent:
        """Record an E1-E9 event and move the operational stage forward."""

        loop = self._loop(loop_id)
        if loop.status is LoopStatus.CLOSED:
            raise ValidationError("closed loops cannot receive events")
        event = LoopEvent(loop_id, event_type, _aware(timestamp or self._now()), reporter_org, owner_next or loop.owner_next, _aware(due_at or loop.due_at), evidence_ref)
        mapping = ELEVEN_STAGE_MAPPING[next(index for index, item in enumerate(ELEVEN_STAGE_MAPPING) if item.stage == loop.stage)]
        if event_type != mapping.expected_event_type:
            raise ValidationError(
                f"{loop.stage} requires {mapping.expected_event_type}, received {event_type}"
            )
        self._events.append(event)
        if mapping.next_stage is not None:
            next_stage = mapping.next_stage
            now = event.timestamp
            self._loops[loop_id] = replace(loop, stage=next_stage, owner_next=event.owner_next, due_at=now + self._sla.duration(loop.urgency, next_stage))
        return event

    def record_closure_event(
        self,
        loop_id: str,
        *,
        reporter_org: str,
        owner_next: Optional[str] = None,
        due_at: Optional[datetime] = None,
        evidence_ref: str,
        timestamp: Optional[datetime] = None,
    ) -> LoopEvent:
        """Append a validated E9 event for the explicit closure command.

        The closure command may be issued against a locally projected case
        before every partner checkpoint is visible. E9 still remains a typed,
        evidence-referenced ledger event; it does not silently invent the
        preceding E1-E8 events.
        """

        loop = self._loop(loop_id)
        if loop.status is LoopStatus.CLOSED:
            raise ValidationError("closed loops cannot receive events")
        if not evidence_ref or not evidence_ref.strip():
            raise ClosureError("E9 closure events require evidence_ref")
        event = LoopEvent(
            loop_id,
            "E9",
            _aware(timestamp or self._now()),
            reporter_org,
            owner_next or loop.owner_next,
            _aware(due_at or loop.due_at),
            evidence_ref.strip(),
        )
        self._events.append(event)
        return event

    append_event = record_event

    def events(self, loop_id: Optional[str] = None) -> tuple[LoopEvent, ...]:
        """Return immutable V2 events."""

        if loop_id is not None:
            self._loop(loop_id)
        return tuple(event for event in self._events if loop_id is None or event.loop_id == loop_id)

    def report_partner_failure(
        self,
        loop_id: str,
        expected_event_type: str,
        *,
        reporter_org: str,
        deadline: Optional[datetime] = None,
        urgency: Optional[Urgency | str] = None,
        reason: str = "partner reporting failure",
    ) -> VisibilityGap:
        """Create UNKNOWN visibility instead of treating an event as absent."""

        loop = self._loop(loop_id)
        gap = VisibilityGap(loop_id, expected_event_type, self._now(), _aware(deadline or loop.due_at), Urgency(urgency or loop.urgency), reporter_org, reason)
        self._gaps.append(gap)
        return gap

    def visibility_gaps(self, loop_id: Optional[str] = None) -> tuple[VisibilityGap, ...]:
        """Return explicit partner-reporting visibility gaps."""

        if loop_id is not None:
            self._loop(loop_id)
        return tuple(gap for gap in self._gaps if loop_id is None or gap.loop_id == loop_id)

    def daily_absence_report(self, *, at: Optional[datetime] = None) -> tuple[AbsenceReport, ...]:
        """Report each open loop's expected next event, deadline, and urgency."""

        observed = _aware(at or self._now())
        rows: list[AbsenceReport] = []
        for loop in self._loops.values():
            if loop.status is LoopStatus.CLOSED:
                continue
            mapping = next(item for item in ELEVEN_STAGE_MAPPING if item.stage == loop.stage)
            visibility = "UNKNOWN" if any(g.loop_id == loop.loop_id and g.expected_event_type == mapping.expected_event_type for g in self._gaps) else "ABSENT"
            rows.append(AbsenceReport(loop.loop_id, mapping.expected_event_type, loop.due_at, loop.urgency, observed, visibility))
        return tuple(sorted(rows, key=lambda row: row.loop_id))

    def propose_handoff(self, loop_id: str, handoff_id: str, destination: str) -> Handoff:
        """Propose a handoff while the sender remains the current owner."""

        loop = self._loop(loop_id)
        if not destination:
            raise ValidationError("handoff destination is required")
        if handoff_id in self._handoffs:
            raise DuplicateEntityError(handoff_id)
        handoff = Handoff(handoff_id, loop_id, loop.owner_next, destination)
        self._handoffs[handoff_id] = handoff
        return handoff

    def accept_handoff(self, handoff_id: str, *, accepted_by: str) -> Handoff:
        handoff = self._handoffs.get(handoff_id)
        if handoff is None:
            raise NotFoundError(f"handoff {handoff_id!r} not found")
        if handoff.status is HandoffStatus.ACCEPTED:
            return handoff
        if handoff.status is HandoffStatus.REJECTED:
            raise ValidationError("a rejected handoff cannot be accepted")
        accepted = replace(handoff, status=HandoffStatus.ACCEPTED, accepted_by=accepted_by, accepted_at=self._now())
        self._handoffs[handoff_id] = accepted
        loop = self._loop(handoff.loop_id)
        self._loops[handoff.loop_id] = replace(loop, owner_next=handoff.destination)
        return accepted

    def reject_handoff(self, handoff_id: str, *, reason: str, alternative_destination: str) -> Handoff:
        """Reject a handoff only with a reason and an alternative destination."""

        handoff = self._handoffs.get(handoff_id)
        if handoff is None:
            raise NotFoundError(f"handoff {handoff_id!r} not found")
        if not reason or not alternative_destination:
            raise ValidationError("rejection reason and alternative destination are required")
        rejected = replace(handoff, status=HandoffStatus.REJECTED, rejection_reason=reason, alternative_destination=alternative_destination)
        self._handoffs[handoff_id] = rejected
        return rejected

    def request_econsult(
        self,
        loop_id: str,
        consult_id: str,
        *,
        requester_org: str,
        destination_org: str,
        clinical_question: str,
        minimal_data_package: Mapping[str, object],
    ) -> EConsult:
        self._loop(loop_id)
        if consult_id in self._consults:
            raise DuplicateEntityError(consult_id)
        consult = EConsult(consult_id, loop_id, requester_org, destination_org, clinical_question, MappingProxyType(dict(minimal_data_package)))
        self._consults[consult_id] = consult
        return consult

    def resolve_econsult(
        self,
        consult_id: str,
        *,
        resolution: str,
        resolved_without_referral: bool = False,
        referral_destination: Optional[str] = None,
    ) -> EConsult:
        consult = self._consults.get(consult_id)
        if consult is None:
            raise NotFoundError(f"e-consult {consult_id!r} not found")
        if not resolution:
            raise ValidationError("e-consult resolution is required")
        if resolved_without_referral and referral_destination:
            raise ValidationError("resolved-without-referral cannot include a referral destination")
        if not resolved_without_referral and not referral_destination:
            raise ValidationError("a referral destination is required when referral remains necessary")
        updated = replace(consult, status=EConsultStatus.RESOLVED_WITHOUT_REFERRAL if resolved_without_referral else EConsultStatus.REFERRAL_REQUIRED, resolution=resolution, referral_destination=referral_destination)
        self._consults[consult_id] = updated
        return updated

    def pull_patient_passport(self, loop_id: str) -> PatientPassport:
        """Pull the non-clinical contact context needed for outreach."""

        patient = self._patients[self._loop(loop_id).patient_id]
        return PatientPassport(patient.patient_id, patient.language, patient.distance, patient.barrier, patient.companion, patient.payer)

    get_patient_passport = pull_patient_passport

    def issue_result_passport(
        self,
        loop_id: str,
        *,
        meaning: str,
        next_step_owner: str,
        no_contact_instruction: str,
    ) -> ResultPassport:
        """Issue the operational passport used for a patient pull contact."""

        loop = self._loop(loop_id)
        if not meaning or not next_step_owner or not no_contact_instruction:
            raise ValidationError("result passport requires meaning, owner, and no-contact instruction")
        passport = ResultPassport(loop_id, meaning, loop.urgency, next_step_owner, no_contact_instruction)
        self._passports[loop_id] = passport
        return passport

    def pull_result_passport(self, loop_id: str) -> ResultPassport:
        self._loop(loop_id)
        try:
            return self._passports[loop_id]
        except KeyError as exc:
            raise NotFoundError(f"result passport for loop {loop_id!r} not found") from exc

    def record_patient_contact(self, loop_id: str, *, contact_method: str, reporter_org: str) -> PatientContact:
        loop = self._loop(loop_id)
        if not contact_method or not reporter_org:
            raise ValidationError("contact method and reporter organization are required")
        contact = PatientContact(loop_id, loop.patient_id, contact_method, self._now(), reporter_org)
        self._contacts.append(contact)
        return contact

    pull_contact = record_patient_contact

    def authorize_high_risk(self, loop_id: str, *, authorization_id: str, authorized_by: str, rationale: str) -> HumanAuthorization:
        self._loop(loop_id)
        if not authorized_by or not rationale:
            raise ValidationError("high-risk authorization needs an authorizer and rationale")
        if authorization_id in self._authorizations:
            raise DuplicateEntityError(authorization_id)
        authorization = HumanAuthorization(authorization_id, loop_id, authorized_by, rationale, self._now())
        self._authorizations[authorization_id] = authorization
        return authorization

    def check_closure_contract(self, loop_id: str, *, closure_code: ClosureCode | str, evidence_refs: tuple[str, ...] = ()) -> ClosureContract:
        loop = self._loop(loop_id)
        try:
            code = ClosureCode(closure_code)
        except (TypeError, ValueError) as exc:
            raise ClosureError("closure requires a supported typed closure code") from exc
        authorization = next((item for item in self._authorizations.values() if item.loop_id == loop_id), None)
        if not evidence_refs:
            raise ClosureError("closure requires at least one evidence reference")
        if loop.high_risk and authorization is None:
            raise ClosureError("high-risk closure requires human authorization")
        refs = tuple(str(reference).strip() for reference in evidence_refs if str(reference).strip())
        if not refs:
            raise ClosureError("closure requires at least one evidence reference")
        return ClosureContract(loop_id, code, refs, authorization)

    def close_loop(self, loop_id: str, *, closure_code: ClosureCode | str, evidence_refs: tuple[str, ...] = ()) -> LoopRecord:
        loop = self._loop(loop_id)
        if loop.status is LoopStatus.CLOSED:
            return loop
        contract = self.check_closure_contract(loop_id, closure_code=closure_code, evidence_refs=evidence_refs)
        updated = replace(
            loop,
            status=LoopStatus.CLOSED,
            stage="closure",
            due_at=self._now(),
            closure_code=contract.closure_code,
            evidence_refs=contract.evidence_refs,
            authorization_id=contract.human_authorization.authorization_id if contract.human_authorization else None,
            closed_at=self._now(),
        )
        self._loops[loop_id] = updated
        return updated

    def restore_loop(self, record: LoopRecord) -> LoopRecord:
        """Restore a persisted canonical record without creating a second model."""

        if record.patient_id not in self._patients:
            raise NotFoundError(f"patient {record.patient_id!r} not found")
        if record.loop_id in self._loops:
            raise DuplicateEntityError(record.loop_id)
        self._loops[record.loop_id] = record
        return record

    def restore_event(self, event: LoopEvent) -> LoopEvent:
        """Restore an append-only transport event from persistence."""

        self._loop(event.loop_id)
        self._events.append(event)
        return event

    def restore_authorization(self, authorization: HumanAuthorization) -> HumanAuthorization:
        """Restore a persisted human authorization."""

        self._loop(authorization.loop_id)
        self._authorizations[authorization.authorization_id] = authorization
        return authorization

    def escalation_success_probability(self, loop_id: str, *, level: int = 1) -> EscalationAssessment:
        loop = self._loop(loop_id)
        probability = self._probability_hook(loop, level) if self._probability_hook else 0.0
        if not 0.0 <= probability <= 1.0:
            raise ValidationError("escalation success probability must be between 0 and 1")
        return EscalationAssessment(loop_id, probability, loop.urgency, level)

    def set_escalation_probability_hook(self, hook: Optional[EscalationProbabilityHook]) -> None:
        self._probability_hook = hook

    def get_loop(self, loop_id: str) -> LoopRecord:
        return self._loop(loop_id)

    def assign_owner(self, loop_id: str, owner_next: str) -> LoopRecord:
        """Update the next owner on the immutable canonical loop record."""

        if not owner_next:
            raise ValidationError("owner_next is required")
        updated = replace(self._loop(loop_id), owner_next=owner_next)
        self._loops[loop_id] = updated
        return updated


__all__ = [
    "AbsenceReport", "CareLoopLedger", "ClosureCode", "ClosureContract", "DEFAULT_SLA_TABLE",
    "DEFAULT_STAGE_MAPPING", "EConsult", "EConsultStatus", "ELEVEN_STAGE_MAPPING", "EVENT_FIELDS",
    "EVENT_TYPES", "EscalationAssessment", "EscalationProbabilityHook", "EventV2", "Handoff",
    "HandoffStatus", "HumanAuthorization", "LoopEvent", "LoopRecord", "PatientContact", "PatientPassport",
    "ResultPassport", "SLATable", "SlaTable", "STAGE_MAPPING", "STAGE_NAMES", "StageMapping", "Urgency", "LoopStatus",
    "VisibilityGap", "VisibilityGapV2", "canonical_loop_id", "generate_loop_id", "load_sla_table",
    "pseudonymous_loop_id", "utc_now", "Patient",
]
