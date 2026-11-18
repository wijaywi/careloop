"""Deterministic paired event-driven simulator."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
import random
from copy import deepcopy
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from careloop.loop_engine import (
    CareLoopLedger,
    Patient,
    Urgency,
    canonical_loop_id,
    load_sla_table,
)

from .params import load_parameters


@dataclass(frozen=True)
class SimulationConfig:
    cohort_size: int = 10000
    runs: int = 500
    virtual_days: int = 90
    seed: int = 20261019
    parameter_file: str | None = None
    pathway: str | None = None
    queue_policy: str = "fifo"
    bounded: bool = False
    modules: dict[str, bool] | None = None

    @classmethod
    def from_parameters(cls, values: dict[str, Any], **overrides: Any) -> "SimulationConfig":
        data = {key: values[key] for key in ("cohort_size", "runs", "virtual_days", "seed")}
        data.update({key: value for key, value in overrides.items() if value is not None})
        if data.get("queue_policy") not in (None, "fifo", "priority"):
            raise ValueError("queue_policy must be fifo or priority")
        return cls(**data)


@dataclass(frozen=True)
class Person:
    person_id: int
    language: str
    literacy: str
    age_band: str
    risk: float
    pathway: str = "colorectal"
    distance_band: str = "near"
    distance_km: float = 5.0
    barrier: str = "none"
    companion: bool = False
    payer: str = "public"
    provider_changes: int = 0
    contact_quality: float = 1.0

    @property
    def segment(self) -> str:
        return f"{self.language}|{self.literacy}|{self.age_band}"


@dataclass(order=True)
class Event:
    time: float
    sequence: int
    kind: str = field(compare=False)
    person_id: int = field(compare=False)
    provider: str = field(compare=False, default="")


@dataclass
class CaseMetrics:
    result_flagged: bool = False
    notification_time: float | None = None
    confirmation_time: float | None = None
    consult_time: float | None = None
    treatment_time: float | None = None
    closure_time: float | None = None
    owner_covered: bool = False
    teach_back: bool = False
    escalations: int = 0
    backlog_events: int = 0
    max_backlog: int = 0
    cross_provider: bool = False
    lost_to_follow_up: bool = False
    no_show: bool = False
    unnecessary_escalations: int = 0
    state: "SimulatorCaseState" = field(default_factory=lambda: SimulatorCaseState())
    uncertainty_hours: float = 0.0
    unknown_partner_report: bool = False
    closure_type: str | None = None
    evidence_kind: str | None = None
    consult_without_referral: bool = False
    referral_rejected: bool = False
    reroutes: int = 0
    patient_pull: bool = False
    distance_band: str = "near"
    distance_km: float = 5.0
    barrier: str = "none"
    companion: bool = False
    payer: str = "public"
    provider_changes: int = 0
    language: str = "English"
    age_band: str = "18-44"
    workload_hours: float = 0.0
    alerts: int = 0
    fatigue_alerts: int = 0
    closure_within_sla: bool = False
    owner_name: str | None = None
    stage_leakage: dict[str, str] = field(default_factory=dict)


@dataclass
class SimulatorCaseState:
    """Small mirror of the domain stage; transitions are enforced by loop_engine."""

    status: str = "CREATED"
    owner: str | None = None
    teach_back: bool = False
    escalations: int = 0


@dataclass
class SimulationResult:
    config: SimulationConfig
    summary: dict[str, Any]
    segment_metrics: list[dict[str, Any]]
    paired_differences: list[dict[str, Any]]
    parameters: dict[str, Any] = field(default_factory=dict)
    intervals: dict[str, Any] = field(default_factory=dict)
    sensitivity: dict[str, Any] = field(default_factory=dict)
    stress: dict[str, Any] = field(default_factory=dict)
    pathway_metrics: dict[str, Any] = field(default_factory=dict)
    stress_scenarios: dict[str, Any] = field(default_factory=dict)
    leakage_map: list[dict[str, Any]] = field(default_factory=list)
    workload: dict[str, Any] = field(default_factory=dict)
    ablations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "cohort_size": self.config.cohort_size,
                "runs": self.config.runs,
                "virtual_days": self.config.virtual_days,
                "seed": self.config.seed,
                "pathway": self.config.pathway,
                "queue_policy": self.config.queue_policy,
                "bounded": self.config.bounded,
                "modules": self.config.modules,
            },
            "parameters": self.parameters,
            "summary": self.summary,
            "intervals": self.intervals,
            "sensitivity": self.sensitivity,
            "stress": self.stress,
            "stress_scenarios": self.stress_scenarios,
            "pathway_metrics": self.pathway_metrics,
            "leakage_map": self.leakage_map,
            "workload": self.workload,
            "ablations": self.ablations,
            "segment_metrics": self.segment_metrics,
            "paired_differences": self.paired_differences,
        }

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def write_csv(self, path: str | Path) -> None:
        rows: list[dict[str, Any]] = []
        for row in self.segment_metrics:
            rows.append({"row_type": "segment", **row})
        for row in self.paired_differences:
            rows.append({"row_type": "paired_difference", **row})
        for arm, row in self.ablations.get("arms", {}).items():
            rows.append({"row_type": "ablation", "arm": arm, **row})
        for row in self.leakage_map:
            rows.append({"row_type": "leakage", **row})
        fields = sorted({key for row in rows for key in row})
        with Path(path).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


class Simulator:
    """Run paired Arm A/B-full simulations over common seeded cohorts."""

    ARMS = (
        "Arm A", "B-full", "B_without_closure_gate",
        "B_without_absence_detector", "B_without_positive_handoff",
        "B_without_multilingual_passport",
    )
    MODULES = ("closure_gate", "absence_detector", "positive_handoff", "multilingual_passport")
    EVENT_ORDER = {"notification": 0, "confirmation": 1, "consult": 2, "treatment": 3,
                   "escalation": 4, "closure": 5}

    def __init__(self, config: SimulationConfig | None = None, parameters: dict[str, Any] | None = None):
        self.parameters = parameters or load_parameters((config or SimulationConfig()).parameter_file)
        requested = config or SimulationConfig.from_parameters(self.parameters)
        self.config = SimulationConfig(
            cohort_size=requested.cohort_size,
            runs=requested.runs,
            virtual_days=requested.virtual_days,
            seed=requested.seed,
            parameter_file=requested.parameter_file,
            pathway=requested.pathway,
            queue_policy=requested.queue_policy,
            bounded=requested.bounded,
            modules=deepcopy(requested.modules),
        )
        if self.config.cohort_size < 1 or self.config.runs < 1 or self.config.virtual_days < 1:
            raise ValueError("cohort_size, runs, and virtual_days must be positive")

    def run(self, *, include_sensitivity: bool = False, include_stress: bool = False) -> SimulationResult:
        result = self._run_core()
        result.parameters = self._parameter_section()
        result.intervals = self._confidence_intervals(result)
        result.pathway_metrics = self._pathway_metrics(result)
        result.leakage_map = self._leakage_map(result)
        result.ablations = self._ablation_summary(result)
        result.workload = self._workload_comparison()
        if include_sensitivity:
            result.sensitivity = self._sensitivity()
        if include_stress:
            result.stress = self._stress_scenarios()
            result.stress_scenarios = self._v2_stress_scenarios()
        return result

    def _run_core(self) -> SimulationResult:
        all_rows: list[dict[str, Any]] = []
        paired: list[dict[str, Any]] = []
        for run_number in range(1, self.config.runs + 1):
            cohort = self._cohort(run_number)
            arm_rows = {arm: self._run_arm(cohort, arm, run_number) for arm in self.ARMS}
            for arm, rows in arm_rows.items():
                all_rows.extend(self._aggregate_rows(run_number, arm, cohort, rows))
            paired.append(self._paired_row(run_number, arm_rows["Arm A"], arm_rows["B-full"]))
        summary = self._aggregate_summary(all_rows)
        return SimulationResult(self.config, summary, all_rows, paired)

    def _cohort(self, run_number: int) -> list[Person]:
        rng = random.Random(self.config.seed + run_number * 1009)
        languages = self.parameters["segment_weights.language"]
        literacy = self.parameters["segment_weights.literacy"]
        ages = self.parameters["segment_weights.age_band"]
        pathways = self.parameters.get("pathways", {"colorectal": {}})
        weights = self.parameters.get("pathway_weights", {key: 1.0 for key in pathways})
        if self.config.pathway and self.config.pathway not in pathways:
            raise ValueError(f"unknown pathway: {self.config.pathway}")
        people: list[Person] = []
        for i in range(self.config.cohort_size):
            pathway = self.config.pathway or self._weighted(rng, weights)
            language = self._weighted(rng, languages)
            people.append(Person(
                i, language, self._weighted(rng, literacy), self._weighted(rng, ages),
                rng.random(), pathway,
                distance_band=self._weighted(rng, self.parameters.get("distance_weights", {
                    "near": 0.55, "moderate": 0.3, "far": 0.15})),
                distance_km=0.0, barrier=self._weighted(rng, self.parameters.get("barrier_weights", {
                    "none": 0.55, "transport": 0.2, "cost": 0.15, "language": 0.1})),
                companion=self._draw_value(rng) < float(self.parameters.get("companion_probability", 0.35)),
                payer=self._weighted(rng, self.parameters.get("payer_weights", {
                    "public": 0.55, "commercial": 0.35, "uninsured": 0.1})),
                provider_changes=self._draw_int(rng, self.parameters.get("provider_change_distribution", {
                    "0": 0.72, "1": 0.22, "2": 0.06})),
                contact_quality=max(0.0, min(1.0, rng.random() * 0.35 +
                    float(self.parameters.get("contact_data_quality", 1.0)) * 0.65)),
            ))
            # Keep distance values derived from the band so the band is a
            # meaningful mechanism and not merely a reporting label.
            distance = self.parameters.get("distance_km", {"near": 5.0, "moderate": 25.0, "far": 70.0})
            people[-1] = Person(**{**people[-1].__dict__, "distance_km": float(distance.get(people[-1].distance_band, 5.0))})
        return people

    @staticmethod
    def _draw_value(rng: Any) -> float:
        return float(rng.random())

    @staticmethod
    def _draw_int(rng: Any, weights: dict[str, float]) -> int:
        return int(Simulator._weighted(rng, {str(key): value for key, value in weights.items()}))

    @staticmethod
    def _weighted(rng: Any, weights: dict[str, float]) -> str:
        pick = rng.random() * sum(weights.values())
        for key, weight in weights.items():
            pick -= weight
            if pick <= 0:
                return key
        return next(reversed(weights))

    def _run_arm(self, cohort: list[Person], arm: str, run_number: int) -> list[CaseMetrics]:
        modules = self._modules_for(arm)
        cases = [CaseMetrics(
            distance_band=person.distance_band, distance_km=person.distance_km,
            barrier=person.barrier, companion=person.companion, payer=person.payer,
            provider_changes=person.provider_changes, language=person.language,
            age_band=person.age_band, owner_name=self._owner(person),
        ) for person in cohort]
        v2_loop = self._make_v2_loop(cohort)
        queue: list[Event] = []
        sequence = 0
        for person in cohort:
            if self.config.queue_policy == "priority":
                rank = int((1.0 - person.risk) * 100000) + sequence
                heapq.heappush(queue, Event(0.0, rank, "notification", person.person_id, "intake"))
            else:
                heapq.heappush(queue, self._event(0.0, sequence, "notification", person.person_id, "intake"))
            sequence += 1
        provider_slots = {name: [0.0] * max(1, int(capacity))
                          for name, capacity in self.parameters["capacity.providers"].items()}
        if "capacity.navigators" in self.parameters:
            navigator_capacity = max(1, int(self.parameters["capacity.navigators"]))
            provider_slots["intake"] = [0.0] * min(len(provider_slots.get("intake", [0.0])), navigator_capacity)
        provider_slots.setdefault("external-specialist", list(provider_slots.get("cross_provider", [0.0])))
        backlog = 0
        while queue:
            event = heapq.heappop(queue)
            if event.time > self.config.virtual_days:
                continue
            person = cohort[event.person_id]
            case = cases[event.person_id]
            if event.kind == "notification":
                if self._draw(person, run_number, "result_flagged", arm) > self._result_flag_probability(person, arm):
                    case.stage_leakage["1"] = "result_not_flagged"
                    case.lost_to_follow_up = True
                    continue
                case.result_flagged = True
                start, queue_delay, backlog = self._reserve(
                    provider_slots["intake"], event.time,
                    self.parameters["capacity.service_days"]["notification"], backlog,
                )
                notification_done = start + self.parameters["capacity.service_days"]["notification"]
                if queue_delay > 0:
                    case.backlog_events += 1
                    case.max_backlog = max(case.max_backlog, backlog)
                self._transition(case, person, "notification")
                self._record_v2_event(v2_loop, person, "E1", event.time, owner_next="owner-intake")
                self._record_v2_event(v2_loop, person, "E2", notification_done, owner_next=self._owner(person))
                case.notification_time = notification_done
                case.workload_hours += self.parameters["capacity.service_days"]["notification"] * 8
                self._schedule(queue, event, sequence, "confirmation", notification_done + self._delay(person, "confirmation", arm, modules), "owner")
                sequence += 1
                continue
            if event.kind in ("confirmation", "consult", "treatment", "escalation"):
                provider = event.provider or self._provider_for(event.kind)
                requested = event.time
                slots = provider_slots.setdefault(provider, [0.0])
                start, queue_delay, backlog = self._reserve(slots, requested,
                                                            self.parameters["capacity.service_days"][event.kind], backlog)
                if queue_delay > 0:
                    case.backlog_events += 1
                    case.max_backlog = max(case.max_backlog, backlog)
                event_time = start + self.parameters["capacity.service_days"][event.kind]
                case.workload_hours += self.parameters["capacity.service_days"][event.kind] * 8
                case.alerts += 1
                if case.alerts > int(self.parameters.get("alert_fatigue_threshold", 4)):
                    case.fatigue_alerts += 1
            else:
                event_time = event.time
            if event.kind == "confirmation":
                if self._draw(person, run_number, "no_show:confirmation", arm) < self._no_show_probability(person, arm, modules):
                    case.no_show = True
                    case.stage_leakage["2"] = "absence"
                    self._record_absence(v2_loop, person, "confirmation", event_time)
                    if modules["absence_detector"] and not case.patient_pull and self._draw(person, run_number, "patient_pull:confirmation", arm) < self._patient_pull_probability(person, modules):
                        case.patient_pull = True
                        self._schedule(queue, event, sequence, "confirmation",
                                       event_time + self._delay(person, "confirmation", arm, modules), "owner")
                        sequence += 1
                    else:
                        case.lost_to_follow_up = True
                    continue
                probability = self._probability(person, "confirmation", arm, modules)
                if self._draw(person, run_number, "confirmation", arm) > probability:
                    case.stage_leakage["2"] = "confirmation_failure"
                    self._enqueue_escalation(queue, event, sequence, event_time, arm, person, run_number)
                    sequence += 1
                    continue
                self._transition(case, person, "confirmation", owner=self._owner(person))
                self._record_v2_event(v2_loop, person, "E3", event_time, owner_next=self._owner(person))
                self._record_v2_event(v2_loop, person, "E4", event_time, owner_next="specialist")
                case.confirmation_time = event_time
                case.owner_covered = self._draw(person, run_number, "owner", arm) < self._owner_probability(arm, modules)
                if self._draw(person, run_number, "loss_to_follow_up", arm) < self._loss_probability(person, arm):
                    case.stage_leakage["3"] = "contact_loss"
                    case.lost_to_follow_up = True
                    continue
                cross_provider = self._draw(person, run_number, "cross_provider", arm) < self._cross_provider_probability(arm, person, modules)
                case.cross_provider = cross_provider
                consult_provider = "external-specialist" if cross_provider else "specialist"
                self._schedule(queue, event, sequence, "consult", event_time + self._delay(person, "consult", arm, modules), consult_provider)
                sequence += 1
            elif event.kind == "consult":
                if self._draw(person, run_number, "no_show:consult", arm) < self._no_show_probability(person, arm, modules):
                    case.no_show = True
                    case.stage_leakage["5"] = "absence"
                    self._record_absence(v2_loop, person, "consult", event_time)
                    if modules["absence_detector"] and not case.patient_pull and self._draw(person, run_number, "patient_pull:consult", arm) < self._patient_pull_probability(person, modules):
                        case.patient_pull = True
                        self._schedule(queue, event, sequence, "consult",
                                       event_time + self._delay(person, "consult", arm, modules), event.provider)
                        sequence += 1
                    else:
                        case.lost_to_follow_up = True
                    continue
                if self._draw(person, run_number, "consult", arm) > self._probability(person, "consult", arm, modules):
                    case.stage_leakage["5"] = "consult_failure"
                    self._enqueue_escalation(queue, event, sequence, event_time, arm, person, run_number)
                    sequence += 1
                    continue
                teach = self._draw(person, run_number, "teach_back", arm) < self._teach_back_probability(person, arm)
                self._transition(case, person, "consult", owner="specialist", teach_back=teach)
                self._record_v2_event(v2_loop, person, "E5", event_time, owner_next="specialist")
                case.consult_time = event_time
                case.teach_back = teach
                if modules["econsult"] and self._econsult_available(person, run_number):
                    case.consult_without_referral = True
                elif self._draw(person, run_number, "referral_rejected", arm) < self._referral_rejection_probability(person, modules):
                    case.referral_rejected = True
                    case.reroutes += 1
                    case.stage_leakage["6"] = "rerouted" if modules["positive_handoff"] else "referral_rejection"
                    if not modules["positive_handoff"]:
                        case.lost_to_follow_up = True
                        continue
                # The ledger keeps the operational stage sequence intact even
                # when the consult resolves without a physical referral. The
                # metric above records that branch; these transport events
                # represent the remaining handoff/appointment/attendance
                # checkpoints in the single E1-E9 contract.
                self._record_v2_event(v2_loop, person, "E5", event_time, owner_next="clinic")
                self._record_v2_event(v2_loop, person, "E6", event_time, owner_next="clinic")
                self._record_v2_event(v2_loop, person, "E6", event_time, owner_next="clinic")
                self._record_v2_event(v2_loop, person, "E7", event_time, owner_next="clinic")
                self._maybe_unnecessary_escalation(case, person, run_number, arm, "consult")
                self._schedule(queue, event, sequence, "treatment", event_time + self._delay(person, "treatment", arm, modules), "clinic")
                sequence += 1
            elif event.kind == "treatment":
                if self._draw(person, run_number, "no_show:treatment", arm) < self._no_show_probability(person, arm, modules):
                    case.no_show = True
                    case.stage_leakage["8"] = "absence"
                    self._record_absence(v2_loop, person, "treatment", event_time)
                    if modules["absence_detector"] and not case.patient_pull and self._draw(person, run_number, "patient_pull:treatment", arm) < self._patient_pull_probability(person, modules):
                        case.patient_pull = True
                        self._schedule(queue, event, sequence, "treatment",
                                       event_time + self._delay(person, "treatment", arm, modules), event.provider)
                        sequence += 1
                    else:
                        case.lost_to_follow_up = True
                    continue
                if self._draw(person, run_number, "treatment", arm) > self._probability(person, "treatment", arm, modules):
                    case.stage_leakage["8"] = "treatment_failure"
                    self._enqueue_escalation(queue, event, sequence, event_time, arm, person, run_number)
                    sequence += 1
                    continue
                self._transition(case, person, "treatment", owner="clinic")
                self._record_v2_event(v2_loop, person, "E8", event_time, owner_next="clinic")
                case.treatment_time = event_time
                self._maybe_unnecessary_escalation(case, person, run_number, arm, "treatment")
                self._schedule(queue, event, sequence, "closure", event_time, "")
                sequence += 1
            elif event.kind == "escalation":
                case.escalations += 1
                case.state.escalations = case.escalations
                # A failed step is retried only when the escalation itself
                # succeeds; the success probability is a scenario parameter.
                escalation_success = self._draw(person, run_number, "escalation_success", arm) < float(
                    self.parameters.get("escalation_success_probability", 0.0)
                )
                if case.escalations == 1 and escalation_success:
                    retry = {"confirmation": "confirmation", "consult": "consult", "treatment": "treatment"}.get(
                        self._last_step(case), "confirmation")
                    self._schedule(queue, event, sequence, retry, event_time + self._delay(person, retry, arm, modules), self._provider_for(retry))
                    sequence += 1
                elif case.escalations == 1:
                    case.lost_to_follow_up = True
            elif event.kind == "closure" and case.state.status == "TREATED":
                evidence_available = self._draw(person, run_number, "closure_evidence", arm) < self._evidence_probability(person, modules)
                if modules["closure_gate"] and not evidence_available:
                    case.stage_leakage["11"] = "missing_closure_evidence"
                    case.uncertainty_hours += self._uncertainty_hours(person, modules)
                    continue
                case.unknown_partner_report = self._draw(person, run_number, "unknown_partner_report", arm) < self._unknown_partner_probability(person)
                case.evidence_kind = "unknown_partner_report" if case.unknown_partner_report else ("patient_pull" if case.patient_pull else "provider_result")
                if evidence_available:
                    case.closure_type = "Completed"
                elif person.barrier == "fear":
                    case.closure_type = "Declined-informed"
                elif case.provider_changes > 0:
                    case.closure_type = "Moved-provider"
                else:
                    case.closure_type = "Unreachable-documented"
                self._record_closure(v2_loop, case, person, evidence_available)
                if case.unknown_partner_report:
                    v2_loop.report_partner_failure(
                        canonical_loop_id(f"p-{person.person_id}"), "E9", reporter_org="partner",
                    )
                else:
                    self._record_v2_event(v2_loop, person, "E9", event_time, owner_next="clinic", evidence_ref=f"closure:{person.person_id}")
                case.closure_time = event_time
                case.closure_within_sla = event_time <= self._closure_sla()
        return cases

    def _make_v2_loop(self, cohort: list[Person]) -> CareLoopLedger:
        """Create the canonical E1-E9 ledger used by the simulator."""

        configured_sla = self.parameters.get("sla_table_v2")
        sla_table = None
        if isinstance(configured_sla, dict):
            stage_keys = {
                "result_issued": "stage_1_notification_hours",
                "notification": "stage_1_notification_hours",
                "acknowledgement": "stage_2_acknowledgement_hours",
                "confirmatory_test": "stage_3_confirmatory_hours",
                "e_consult": "stage_4_consult_hours",
                "referral": "stage_5_referral_hours",
                "referral_acceptance": "stage_6_acceptance_hours",
                "appointment": "stage_7_appointment_hours",
                "attendance": "stage_8_attendance_hours",
                "treatment": "stage_9_treatment_hours",
                "closure": "stage_10_closure_hours",
            }
            converted = {
                urgency: {stage: values.get(key, 24) for stage, key in stage_keys.items()}
                for urgency, values in configured_sla.items()
                if isinstance(values, dict)
            }
            sla_table = load_sla_table(converted)
        v2 = CareLoopLedger(
            sla_table=sla_table or load_sla_table({"urgent": {"default": 24}, "routine": {"default": 168}}),
            escalation_probability_hook=lambda _loop, _level: float(self.parameters.get("escalation_success_probability", 0.0)),
        )
        for person in cohort:
            patient_id = f"p-{person.person_id}"
            v2.register_patient(Patient(
                patient_id,
                patient_id,
                person.language,
                person.distance_band,
                person.barrier,
                "yes" if person.companion else "no",
                person.payer,
            ))
            v2.create_loop(
                patient_id,
                "screening-org",
                "owner-intake",
                urgency=Urgency.URGENT if person.risk >= 0.75 else Urgency.ROUTINE,
                high_risk=person.risk >= 0.85,
            )
        return v2

    @staticmethod
    def _record_v2_event(
        v2: CareLoopLedger,
        person: Person,
        event_type: str,
        event_time: float,
        *,
        owner_next: str,
        evidence_ref: str | None = None,
    ) -> None:
        """Record a transport-only E1-E9 event at virtual time."""

        loop_id = canonical_loop_id(f"p-{person.person_id}")
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=event_time)
        if event_type == "E9":
            v2.record_closure_event(
                loop_id,
                reporter_org="simulated-org",
                owner_next=owner_next,
                due_at=timestamp + timedelta(days=1),
                evidence_ref=evidence_ref or f"closure:{person.person_id}",
                timestamp=timestamp,
            )
        else:
            v2.record_event(
                loop_id,
                event_type,
                reporter_org="simulated-org",
                owner_next=owner_next,
                due_at=timestamp + timedelta(days=1),
                evidence_ref=evidence_ref,
                timestamp=timestamp,
            )

    def _modules_for(self, arm: str) -> dict[str, bool]:
        if arm == "Arm A":
            enabled = {name: False for name in self.MODULES} | {"econsult": False}
            if self.config.modules:
                enabled.update({name: bool(value) for name, value in self.config.modules.items() if name in enabled})
            return enabled
        enabled = {name: True for name in self.MODULES} | {"econsult": True}
        # Preserve the simulator's explicit zero-effect contract.
        # This is useful for regression tests and makes paired mechanics
        # auditable: when every legacy CareLoop mechanism is neutral, V2 has no
        # hidden module-only uplift.
        legacy_zero = all((
            float(self.parameters.get(f"b_full.{name}_delay_multiplier", 1.0)) == 1.0
            for name in ("notification", "confirmation", "consult", "treatment")
        )) and all(float(self.parameters.get(f"b_full.{name}_probability_add", 0.0)) == 0.0
                   for name in ("confirmation", "consult", "treatment")) and all(float(self.parameters.get(name, 0.0)) == 0.0
                   for name in ("b_full.teach_back_probability_add", "b_full.owner_coverage_probability_add",
                                 "b_full.loss_to_follow_up_probability_add", "b_full.no_show_probability_add",
                                 "b_full.unnecessary_escalation_probability", "b_full.result_flag_probability_add")) and float(self.parameters.get("b_full.escalation_multiplier", 1.0)) == 1.0
        if legacy_zero and arm == "B-full":
            return {name: False for name in self.MODULES} | {"econsult": False}
        ablation = {
            "B_without_closure_gate": "closure_gate",
            "B_without_absence_detector": "absence_detector",
            "B_without_positive_handoff": "positive_handoff",
            "B_without_multilingual_passport": "multilingual_passport",
        }.get(arm)
        if ablation:
            enabled[ablation] = False
        if self.config.modules:
            enabled.update({name: bool(value) for name, value in self.config.modules.items() if name in enabled})
        return enabled

    def _event(self, time: float, sequence: int, kind: str, person_id: int, provider: str) -> Event:
        # The queue policy changes ordering mechanics at equal availability
        # times.  No outcome is post-adjusted after the event loop runs.
        rank = sequence
        if self.config.queue_policy == "priority":
            rank = sequence * 10 + self.EVENT_ORDER.get(kind, 9)
        return Event(time, rank, kind, person_id, provider)

    def _record_absence(self, loop: CareLoopLedger, person: Person, stage: str, event_time: float) -> None:
        """Record an explicit UNKNOWN gap in the canonical transport ledger."""
        loop.report_partner_failure(
            canonical_loop_id(f"p-{person.person_id}"),
            self._event_type_for_stage(stage),
            reporter_org="simulated-org",
            reason=f"no visible {stage} event at virtual day {event_time:.4f}",
        )

    @staticmethod
    def _event_type_for_stage(stage: str) -> str:
        return {"confirmation": "E3", "consult": "E5", "treatment": "E8"}[stage]

    def _record_closure(self, loop: CareLoopLedger, case: CaseMetrics, person: Person, evidence: bool) -> None:
        """Keep closure metrics separate from transport E9 evidence validation.

        The simulator records E9 below when a closure event is visible. The
        canonical ledger remains the only domain engine; this helper only keeps
        the case-level metric bookkeeping explicit for an evidence-gated run.
        """
        if not evidence:
            case.uncertainty_hours += self._uncertainty_hours(person, {"absence_detector": True})

    def _econsult_available(self, person: Person, run_number: int) -> bool:
        return self._draw(person, run_number, "econsult_available", "shared") >= float(self.parameters.get("econsult_unavailable_rate", 0.0))

    def _patient_pull_probability(self, person: Person, modules: dict[str, bool]) -> float:
        base = float(self.parameters.get("patient_pull_probability", 0.12))
        if not modules["absence_detector"]:
            return 0.0
        if person.companion:
            base += 0.08
        return min(1.0, base)

    def _referral_rejection_probability(self, person: Person, modules: dict[str, bool] | None = None) -> float:
        value = float(self.parameters.get("referral_rejection_probability", 0.08))
        value += 0.04 * person.provider_changes
        if modules is not None and modules.get("positive_handoff", False):
            value *= float(self.parameters.get("b_full.positive_handoff_rejection_multiplier", 0.55))
        return min(1.0, value)

    def _unknown_partner_probability(self, person: Person) -> float:
        base = self.parameters.get(
            "partner_event_reporting_failure_probability",
            self.parameters.get("unknown_partner_report_probability", 0.03),
        )
        return min(1.0, float(base) +
                   (0.04 if person.provider_changes else 0.0))

    def _evidence_probability(self, person: Person, modules: dict[str, bool]) -> float:
        value = float(self.parameters.get("closure_evidence_probability", 0.82))
        if person.contact_quality < 0.6:
            value -= 0.1
        if person.barrier in ("transport", "cost"):
            value -= 0.05
        return max(0.05, min(0.99, value))

    def _uncertainty_hours(self, person: Person, modules: dict[str, bool]) -> float:
        value = float(self.parameters.get("base_uncertainty_hours", 24.0))
        value *= 1.0 + person.distance_km / 100.0
        if person.contact_quality < 0.6:
            value *= 1.25
        return round(value, 4)

    def _closure_sla(self) -> float:
        return float(self.parameters.get("closure_sla_days", 30.0))

    def _transition(self, case: CaseMetrics, person: Person, event: str,
                    owner: str | None = None, teach_back: bool = False) -> None:
        if owner:
            case.state.owner = owner
        case.state.status = {"notification": "NOTIFIED", "confirmation": "CONFIRMED",
                             "consult": "CONSULTED", "treatment": "TREATED", "closure": "CLOSED"}[event]
        if teach_back:
            case.state.teach_back = True

    @staticmethod
    def _last_step(case: CaseMetrics) -> str:
        if case.treatment_time is None and case.consult_time is not None:
            return "treatment"
        if case.consult_time is None and case.confirmation_time is not None:
            return "consult"
        return "confirmation"

    def _schedule(self, queue: list[Event], prior: Event, sequence: int, kind: str, time: float, provider: str) -> None:
        heapq.heappush(queue, self._event(time, sequence, kind, prior.person_id, provider))

    def _enqueue_escalation(self, queue: list[Event], prior: Event, sequence: int, time: float, arm: str,
                            person: Person, run_number: int) -> None:
        # The mechanism is a parameter: CareLoop changes escalation likelihood,
        # while the event and transition semantics remain in loop_engine.
        multiplier = 1.0 if arm == "Arm A" else self.parameters["b_full.escalation_multiplier"]
        if self._draw(person, run_number, f"escalation:{prior.kind}", arm) > multiplier:
            return
        heapq.heappush(queue, self._event(time, sequence, "escalation", prior.person_id, "manager"))

    @staticmethod
    def _provider_for(kind: str) -> str:
        return {"confirmation": "owner", "consult": "specialist", "treatment": "clinic", "escalation": "manager"}[kind]

    @staticmethod
    def _reserve(slots: list[float], requested: float, service: float, backlog: int) -> tuple[float, float, int]:
        index = min(range(len(slots)), key=slots.__getitem__)
        start = max(requested, slots[index])
        delay = start - requested
        if delay > 0:
            backlog += 1
        else:
            backlog = max(0, backlog - 1)
        slots[index] = start + service
        return start, delay, backlog

    def _delay(self, person: Person, stage: str, arm: str, modules: dict[str, bool] | None = None) -> float:
        base = self.parameters[f"arm_a.{stage}_delay"]
        is_full = arm != "Arm A"
        multiplier = self.parameters.get(f"b_full.{stage}_delay_multiplier", 1.0) if is_full else 1.0
        # HAND-AUTHORED ASSUMPTIONS: non-English, limited-literacy, and age
        # 65+ modifiers are optional segment mechanisms; English is default.
        segment = 1.0
        if person.language != "English":
            if modules is not None and modules.get("multilingual_passport", False):
                segment *= float(self.parameters.get("b_full.multilingual_delay_multiplier", 0.85))
            else:
                segment *= self.parameters["segment_delay_multiplier.language_non_english"]
        if person.literacy != "high":
            segment *= self.parameters["segment_delay_multiplier.literacy_limited"]
        if person.age_band == "65+":
            segment *= self.parameters["segment_delay_multiplier.age_65_plus"]
        segment *= 1.0 + person.distance_km / 250.0
        segment *= {"none": 1.0, "transport": 1.2, "cost": 1.12, "language": 1.1}.get(person.barrier, 1.0)
        segment *= {"public": 1.0, "commercial": 1.03, "uninsured": 1.15}.get(person.payer, 1.0)
        pathway = self.parameters.get("pathways", {}).get(person.pathway, {})
        variation = self._duration_variation(person, stage)
        return base * multiplier * segment * float(pathway.get("delay_multiplier", 1.0)) * variation

    def _duration_variation(self, person: Person, stage: str) -> float:
        """Sample a paired, deterministic duration factor from a configured spread."""

        coefficient = float(self.parameters.get("duration_variability_cv", 0.15))
        digest = hashlib.sha256(f"duration:{person.person_id}:{stage}".encode()).digest()
        draw = int.from_bytes(digest[:8], "big") / 2**64
        return max(0.25, 1.0 + (draw - 0.5) * 2.0 * coefficient)

    def _probability(self, person: Person, stage: str, arm: str, modules: dict[str, bool] | None = None) -> float:
        value = self.parameters[f"arm_a.{stage}_probability"]
        is_full = arm != "Arm A"
        if is_full and (stage != "confirmation" or modules is None or modules.get("positive_handoff", False)):
            value += self.parameters[f"b_full.{stage}_probability_add"]
        value += self.parameters["risk_probability_add"] * person.risk
        if person.literacy == "low":
            value -= 0.08
        if person.language != "English" and modules is not None and modules.get("multilingual_passport", False):
            value += float(self.parameters.get("b_full.multilingual_understanding_probability_add", 0.08))
        value -= {"none": 0.0, "transport": 0.04, "cost": 0.03, "language": 0.02}.get(person.barrier, 0.0)
        value += 0.04 if person.companion else 0.0
        value -= 0.03 if person.payer == "uninsured" else 0.0
        value += float(self.parameters.get("pathways", {}).get(person.pathway, {}).get("probability_add", 0.0))
        return max(0.05, min(0.99, value))

    def _result_flag_probability(self, person: Person, arm: str) -> float:
        value = float(self.parameters.get("arm_a.result_flag_probability", 1.0))
        if arm != "Arm A":
            value += float(self.parameters.get("b_full.result_flag_probability_add", 0.0))
        return max(0.0, min(1.0, value))

    def _owner_probability(self, arm: str, modules: dict[str, bool] | None = None) -> float:
        value = self.parameters["arm_a.owner_coverage_probability"]
        if arm != "Arm A":
            value += self.parameters["b_full.owner_coverage_probability_add"]
        return min(1.0, value)

    def _teach_back_probability(self, person: Person, arm: str) -> float:
        value = self.parameters["arm_a.teach_back_probability"]
        if arm != "Arm A":
            value += self.parameters["b_full.teach_back_probability_add"]
        if person.literacy == "low":
            value -= 0.1
        return max(0.0, min(1.0, value))

    def _cross_provider_probability(self, arm: str, person: Person | None = None, modules: dict[str, bool] | None = None) -> float:
        value = float(self.parameters.get("arm_a.cross_provider_probability", 0.0))
        if arm != "Arm A":
            value += float(self.parameters.get("b_full.cross_provider_probability_add", 0.0))
        if person is not None:
            value += 0.05 * min(2, person.provider_changes)
        return max(0.0, min(1.0, value))

    def _loss_probability(self, person: Person, arm: str) -> float:
        value = float(self.parameters.get("arm_a.loss_to_follow_up_probability", 0.0))
        if arm != "Arm A":
            value += float(self.parameters.get("b_full.loss_to_follow_up_probability_add", 0.0))
        # Poor contact data is an explicit stress mechanism rather than a
        # hidden random effect.  A quality of 1.0 leaves the base unchanged.
        value += max(0.0, 1.0 - float(self.parameters.get("contact_data_quality", 1.0))) * 0.25
        return max(0.0, min(1.0, value))

    def _no_show_probability(self, person: Person, arm: str, modules: dict[str, bool] | None = None) -> float:
        value = float(self.parameters.get("arm_a.no_show_probability", 0.0))
        if arm != "Arm A":
            value += float(self.parameters.get("b_full.no_show_probability_add", 0.0))
        if person.distance_band == "far":
            value += 0.04
        if person.barrier == "transport":
            value += 0.05
        if person.companion:
            value -= 0.03
        if modules is not None and modules.get("absence_detector", False):
            value *= float(self.parameters.get("absence_detector_no_show_multiplier", 0.9))
        return max(0.0, min(1.0, value))

    def _maybe_unnecessary_escalation(self, case: CaseMetrics, person: Person, run_number: int,
                                      arm: str, stage: str) -> None:
        parameter_arm = "arm_a" if arm == "Arm A" else "b_full"
        probability = float(self.parameters.get(
            f"{parameter_arm}.unnecessary_escalation_probability", 0.0))
        if self._draw(person, run_number, f"unnecessary_escalation:{stage}", arm) < probability:
            case.unnecessary_escalations += 1

    @staticmethod
    def _owner(person: Person) -> str:
        return f"owner-{person.language.lower()}"

    @staticmethod
    def _draw(person: Person, run_number: int, label: str, arm: str) -> float:
        # Arm is intentionally excluded.  Paired random draws then remain
        # identical when all CareLoop mechanism effects are set to zero.
        digest = hashlib.sha256(f"{run_number}:{person.person_id}:{label}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2**64

    def _aggregate_rows(self, run_number: int, arm: str, cohort: list[Person], cases: list[CaseMetrics]) -> list[dict[str, Any]]:
        rows = [self._metrics_row(run_number, arm, "all", cases)]
        by_segment: dict[str, list[CaseMetrics]] = defaultdict(list)
        by_pathway: dict[str, list[CaseMetrics]] = defaultdict(list)
        by_stratum: dict[str, list[CaseMetrics]] = defaultdict(list)
        for person, case in zip(cohort, cases):
            by_segment[person.segment].append(case)
            by_pathway[person.pathway].append(case)
            by_stratum[f"stratum:{person.language}|{person.distance_band}|{person.age_band}|{person.payer}"].append(case)
        rows.extend(self._metrics_row(run_number, arm, segment, grouped)
                    for segment, grouped in sorted(by_segment.items()))
        rows.extend(self._metrics_row(run_number, arm, f"pathway:{pathway}", grouped)
                    for pathway, grouped in sorted(by_pathway.items()))
        rows.extend(self._metrics_row(run_number, arm, segment, grouped)
                    for segment, grouped in sorted(by_stratum.items()))
        return rows

    def _metrics_row(self, run: int, arm: str, segment: str, cases: Iterable[CaseMetrics]) -> dict[str, Any]:
        values = list(cases)
        n = len(values)
        closure_distribution: dict[str, int] = defaultdict(int)
        evidence_distribution: dict[str, int] = defaultdict(int)
        leakage: dict[str, int] = defaultdict(int)
        for code in ("Completed", "Declined-informed", "Unreachable-documented", "Moved-provider", "No-action-needed", "Deceased", "unresolved"):
            closure_distribution[code] = 0
        for case in values:
            closure_distribution[case.closure_type or "unresolved"] += 1
            evidence_distribution[case.evidence_kind or "none"] += 1
            for stage, reason in case.stage_leakage.items():
                leakage[f"stage_{stage}:{reason}"] += 1
        def mean(name: str) -> float | None:
            present = [getattr(case, name) for case in values if getattr(case, name) is not None]
            return round(sum(present) / len(present), 4) if present else None
        return {
            "run": run, "arm": arm, "segment": segment, "n": n,
            "pathway": (segment.split(":", 1)[1] if segment.startswith("pathway:")
                         else "all" if segment == "all" else None),
            "notification_time_mean": mean("notification_time"),
            "confirmation_time_mean": mean("confirmation_time"),
            "consult_time_mean": mean("consult_time"),
            "treatment_time_mean": mean("treatment_time"),
            "closure_time_mean": mean("closure_time"),
            "unresolved_30": sum(case.closure_time is None or case.closure_time > 30 for case in values),
            "unresolved_60": sum(case.closure_time is None or case.closure_time > 60 for case in values),
            "unresolved_90": sum(case.closure_time is None or case.closure_time > 90 for case in values),
            "closure_rate": round(sum(case.closure_time is not None and case.closure_time <= self.config.virtual_days for case in values) / n, 4),
            "owner_coverage_rate": round(sum(case.owner_covered for case in values) / n, 4),
            "teach_back_rate": round(sum(case.teach_back for case in values) / n, 4),
            "cross_provider_rate": round(sum(case.cross_provider for case in values) / n, 4),
            "loss_to_follow_up_rate": round(sum(case.lost_to_follow_up for case in values) / n, 4),
            "no_show_rate": round(sum(case.no_show for case in values) / n, 4),
            "unnecessary_escalation_rate": round(sum(case.unnecessary_escalations for case in values) / n, 4),
            "unnecessary_escalations": sum(case.unnecessary_escalations for case in values),
            "escalations": sum(case.escalations for case in values),
            "backlog_events": sum(case.backlog_events for case in values),
            "max_backlog": max((case.max_backlog for case in values), default=0),
            "uncertainty_hours_mean": mean("uncertainty_hours"),
            "unknown_rate": round(sum(case.unknown_partner_report for case in values) / n, 4),
            "result_flag_rate": round(sum(case.result_flagged for case in values) / n, 4),
            "closure_within_sla_rate": round(sum(case.closure_within_sla for case in values) / n, 4),
            "named_owner_documented_closure_within_sla_rate": round(sum(case.owner_covered and case.closure_type is not None and case.closure_within_sla for case in values) / n, 4),
            "documented_closure_rate": round(sum(case.closure_type is not None for case in values) / n, 4),
            "evidence_rate": round(sum(case.evidence_kind is not None for case in values) / n, 4),
            "consult_without_referral_rate": round(sum(case.consult_without_referral for case in values) / n, 4),
            "referral_rejection_rate": round(sum(case.referral_rejected for case in values) / n, 4),
            "patient_pull_rate": round(sum(case.patient_pull for case in values) / n, 4),
            "reroutes": sum(case.reroutes for case in values),
            "workload_hours": round(sum(case.workload_hours for case in values), 4),
            "alerts": sum(case.alerts for case in values),
            "fatigue_alerts": sum(case.fatigue_alerts for case in values),
            "closure_distribution": dict(sorted(closure_distribution.items())),
            "evidence_distribution": dict(sorted(evidence_distribution.items())),
            "leakage": dict(sorted(leakage.items())),
            "owner": sorted({case.owner_name for case in values if case.owner_name})[0] if values else None,
            "core_metric": "named_owner_and_documented_closure_within_sla",
        }

    @staticmethod
    def _paired_row(run: int, arm_a: list[CaseMetrics], b_full: list[CaseMetrics]) -> dict[str, Any]:
        def delta(name: str) -> float | None:
            a = [getattr(c, name) for c in arm_a if getattr(c, name) is not None]
            b = [getattr(x, name) for x in b_full if getattr(x, name) is not None]
            return round(sum(b) / len(b) - sum(a) / len(a), 4) if a and b else None
        return {
            "run": run, "comparison": "B-full_minus_Arm_A",
            "notification_time_mean_delta": delta("notification_time"),
            "confirmation_time_mean_delta": delta("confirmation_time"),
            "consult_time_mean_delta": delta("consult_time"),
            "treatment_time_mean_delta": delta("treatment_time"),
            "closure_time_mean_delta": delta("closure_time"),
            "closure_rate_delta": round(sum(c.closure_time is not None for c in b_full) / len(b_full) - sum(c.closure_time is not None for c in arm_a) / len(arm_a), 4),
            "owner_coverage_rate_delta": round(sum(c.owner_covered for c in b_full) / len(b_full) - sum(c.owner_covered for c in arm_a) / len(arm_a), 4),
            "teach_back_rate_delta": round(sum(c.teach_back for c in b_full) / len(b_full) - sum(c.teach_back for c in arm_a) / len(arm_a), 4),
            "cross_provider_rate_delta": round(sum(c.cross_provider for c in b_full) / len(b_full) - sum(c.cross_provider for c in arm_a) / len(arm_a), 4),
            "loss_to_follow_up_rate_delta": round(sum(c.lost_to_follow_up for c in b_full) / len(b_full) - sum(c.lost_to_follow_up for c in arm_a) / len(arm_a), 4),
            "unnecessary_escalation_rate_delta": round(sum(c.unnecessary_escalations for c in b_full) / len(b_full) - sum(c.unnecessary_escalations for c in arm_a) / len(arm_a), 4),
            "escalations_delta": sum(c.escalations for c in b_full) - sum(c.escalations for c in arm_a),
            "backlog_events_delta": sum(c.backlog_events for c in b_full) - sum(c.backlog_events for c in arm_a),
        }

    def _aggregate_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        summary: dict[str, Any] = {"arms": {}}
        for arm in Simulator.ARMS:
            arm_rows = [row for row in rows if row["arm"] == arm and row["segment"] == "all"]
            n = sum(row["n"] for row in arm_rows)
            if not n:
                continue
            closure_distribution: dict[str, int] = defaultdict(int)
            evidence_distribution: dict[str, int] = defaultdict(int)
            for row in arm_rows:
                for key, value in row.get("closure_distribution", {}).items():
                    closure_distribution[key] += int(value)
                for key, value in row.get("evidence_distribution", {}).items():
                    evidence_distribution[key] += int(value)
            summary["arms"][arm] = {
                "n": n,
                "closure_rate": round(sum(row["closure_rate"] * row["n"] for row in arm_rows) / n, 4),
                "owner_coverage_rate": round(sum(row["owner_coverage_rate"] * row["n"] for row in arm_rows) / n, 4),
                "teach_back_rate": round(sum(row["teach_back_rate"] * row["n"] for row in arm_rows) / n, 4),
                "cross_provider_rate": round(sum(row["cross_provider_rate"] * row["n"] for row in arm_rows) / n, 4),
                "loss_to_follow_up_rate": round(sum(row["loss_to_follow_up_rate"] * row["n"] for row in arm_rows) / n, 4),
                "no_show_rate": round(sum(row["no_show_rate"] * row["n"] for row in arm_rows) / n, 4),
                "unnecessary_escalation_rate": round(sum(row["unnecessary_escalation_rate"] * row["n"] for row in arm_rows) / n, 4),
                "unnecessary_escalations": sum(row["unnecessary_escalations"] for row in arm_rows),
                "escalations": sum(row["escalations"] for row in arm_rows),
                "backlog_events": sum(row["backlog_events"] for row in arm_rows),
                "uncertainty_hours": round(sum((row["uncertainty_hours_mean"] or 0) * row["n"] for row in arm_rows) / n, 4),
                "unknown_rate": round(sum(row["unknown_rate"] * row["n"] for row in arm_rows) / n, 4),
                "result_flag_rate": round(sum(row["result_flag_rate"] * row["n"] for row in arm_rows) / n, 4),
                "documented_closure_rate": round(sum(row["documented_closure_rate"] * row["n"] for row in arm_rows) / n, 4),
                "evidence_rate": round(sum(row["evidence_rate"] * row["n"] for row in arm_rows) / n, 4),
                "consult_without_referral_rate": round(sum(row["consult_without_referral_rate"] * row["n"] for row in arm_rows) / n, 4),
                "closure_within_sla_rate": round(sum(row["closure_within_sla_rate"] * row["n"] for row in arm_rows) / n, 4),
                "named_owner_documented_closure_within_sla_rate": round(sum(row["named_owner_documented_closure_within_sla_rate"] * row["n"] for row in arm_rows) / n, 4),
                "patient_pull_rate": round(sum(row["patient_pull_rate"] * row["n"] for row in arm_rows) / n, 4),
                "referral_rejection_rate": round(sum(row["referral_rejection_rate"] * row["n"] for row in arm_rows) / n, 4),
                "workload_hours": round(sum(row["workload_hours"] for row in arm_rows), 4),
                "alerts": sum(row["alerts"] for row in arm_rows),
                "fatigue_alerts": sum(row["fatigue_alerts"] for row in arm_rows),
                "owner": next((row["owner"] for row in arm_rows if row["owner"]), None),
                "core_metric": "named_owner_and_documented_closure_within_sla",
                "modules": self._modules_for(arm),
                "closure_distribution": dict(sorted(closure_distribution.items())),
                "evidence_distribution": dict(sorted(evidence_distribution.items())),
            }
        return summary

    def _parameter_section(self) -> dict[str, Any]:
        def notes(name: str) -> str:
            if name in {"segment_weights.language", "segment_delay_multiplier.language_non_english",
                        "b_full.multilingual_delay_multiplier", "b_full.multilingual_understanding_probability_add"}:
                return "HAND-AUTHORED ASSUMPTION: English is the active/default language; non-English is retained only as an optional segment mechanism."
            if name in {"segment_weights.literacy", "segment_delay_multiplier.literacy_limited"}:
                return "HAND-AUTHORED ASSUMPTION: limited-literacy segment modifier."
            if name in {"segment_weights.age_band", "segment_delay_multiplier.age_65_plus"}:
                return "HAND-AUTHORED ASSUMPTION: age 65+ segment modifier."
            return "synthetic simulator input; not clinically validated"
        records = [{"parameter": name, "name": name, "value": deepcopy(value),
                    "range": self._parameter_range(name, value),
                    "distribution": self._parameter_distribution(name, value),
                    "status": "assumption", "source": "not yet found / assumption",
                    "notes": notes(name)}
                   for name, value in sorted(self.parameters.items())]
        manifest = Path(self.config.parameter_file).name if self.config.parameter_file else "params/default.yml"
        return {"status": "assumption", "source": "not yet found / assumption", "records": records, "manifest": manifest}

    @staticmethod
    def _parameter_range(name: str, value: Any) -> Any:
        if isinstance(value, (int, float)):
            return [value, value]
        if isinstance(value, dict):
            return {key: Simulator._parameter_range(name, item) for key, item in value.items()}
        return None

    @staticmethod
    def _parameter_distribution(name: str, value: Any) -> str:
        if isinstance(value, bool):
            return "fixed"
        if isinstance(value, (int, float)):
            return "fixed"
        if isinstance(value, dict):
            return "categorical_weighted" if "weights" in name else "mapping"
        return "fixed"

    @staticmethod
    def _interval(values: list[float], *, clamp: bool = False) -> dict[str, Any]:
        if not values:
            return {"mean": None, "lower": None, "upper": None, "n": 0}
        mean = sum(values) / len(values)
        if len(values) == 1:
            margin = 0.0
        else:
            variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
            margin = 1.96 * math.sqrt(variance / len(values))
        lower, upper = mean - margin, mean + margin
        if clamp:
            lower, upper = max(0.0, lower), min(1.0, upper)
        return {"mean": round(mean, 6), "lower": round(lower, 6), "upper": round(upper, 6), "n": len(values)}

    def _confidence_intervals(self, result: SimulationResult) -> dict[str, Any]:
        metrics = ("closure_rate", "owner_coverage_rate", "teach_back_rate", "cross_provider_rate",
                   "loss_to_follow_up_rate", "no_show_rate", "unnecessary_escalation_rate", "escalations", "backlog_events",
                   "closure_within_sla_rate", "named_owner_documented_closure_within_sla_rate",
                    "unknown_rate", "result_flag_rate", "evidence_rate", "consult_without_referral_rate")
        intervals: dict[str, Any] = {"confidence_level": 0.95, "method": "normal_approximation",
                                     "arms": {}, "paired": {}}
        for arm in self.ARMS:
            rows = [row for row in result.segment_metrics if row["arm"] == arm and row["segment"] == "all"]
            intervals["arms"][arm] = {}
            for metric in metrics:
                intervals["arms"][arm][metric] = self._interval(
                    [float(row[metric]) for row in rows], clamp=metric.endswith("rate"))
        for metric in ("closure_rate_delta", "owner_coverage_rate_delta", "teach_back_rate_delta",
                       "cross_provider_rate_delta", "loss_to_follow_up_rate_delta", "unnecessary_escalation_rate_delta"):
            intervals["paired"][metric] = self._interval(
                [float(row[metric]) for row in result.paired_differences], clamp=False)
        return intervals

    def _pathway_metrics(self, result: SimulationResult) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for row in result.segment_metrics:
            segment = row["segment"]
            if not segment.startswith("pathway:"):
                continue
            pathway = segment.split(":", 1)[1]
            output.setdefault(pathway, {arm: {} for arm in self.ARMS})
            output[pathway][row["arm"]] = {
                key: row[key] for key in ("n", "closure_rate", "owner_coverage_rate", "teach_back_rate",
                                          "cross_provider_rate", "loss_to_follow_up_rate", "no_show_rate",
                                          "unnecessary_escalation_rate", "escalations", "backlog_events")
            }
        return output

    def _leakage_map(self, result: SimulationResult) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in result.segment_metrics:
            if row["segment"] == "all" or row["segment"].startswith("pathway:"):
                continue
            for stage in range(1, 12):
                stage_counts = {key.split(":", 1)[1]: value for key, value in row.get("leakage", {}).items()
                                if key.startswith(f"stage_{stage}:")}
                rows.append({"run": row["run"], "arm": row["arm"], "stage": stage,
                             "stratum": row["segment"], "n": row["n"],
                             "leakage": stage_counts})
        return rows

    def _ablation_summary(self, result: SimulationResult) -> dict[str, Any]:
        arms = result.summary.get("arms", {})
        base = arms.get("B-full", {})
        output: dict[str, Any] = {"reference_arm": "B-full", "metric": "closure_within_sla_rate", "arms": {}}
        for arm in self.ARMS:
            if arm == "Arm A":
                continue
            values = arms.get(arm, {})
            output["arms"][arm] = {
                "closure_within_sla_rate": values.get("closure_within_sla_rate"),
                "closure_rate": values.get("closure_rate"),
                "delta_vs_B-full": round(values.get("closure_within_sla_rate", 0) - base.get("closure_within_sla_rate", 0), 4),
                "modules": self._modules_for(arm),
            }
        return output

    def _workload_comparison(self) -> dict[str, Any]:
        # Keep the comparison bounded even when the requested study is the
        # published 10,000 x 500 default.  It is an analysis of queue mechanics,
        # while the main result retains the requested study dimensions.
        config = self._analysis_config()
        output: dict[str, Any] = {"arms": {}, "analysis_cohort_size": config.cohort_size, "analysis_runs": config.runs}
        for policy in ("fifo", "priority"):
            policy_config = SimulationConfig(
                cohort_size=config.cohort_size, runs=config.runs, virtual_days=config.virtual_days,
                seed=config.seed, parameter_file=config.parameter_file, pathway=config.pathway,
                queue_policy=policy, bounded=True, modules=deepcopy(config.modules),
            )
            simulation = Simulator(policy_config, deepcopy(self.parameters))._run_core()
            output["arms"][policy] = {
                arm: simulation.summary["arms"].get(arm, {}) for arm in ("Arm A", "B-full")
            }
        return output

    def _analysis_config(self) -> SimulationConfig:
        # Analysis flags should be useful on a full run without multiplying a
        # 5-million-person study by every sensitivity point.
        return SimulationConfig(
            cohort_size=min(self.config.cohort_size, 1000),
            runs=min(self.config.runs, 20),
            virtual_days=self.config.virtual_days,
            seed=self.config.seed,
            parameter_file=self.config.parameter_file,
            pathway=self.config.pathway,
            queue_policy=self.config.queue_policy,
            bounded=True,
            modules=deepcopy(self.config.modules),
        )

    def _metric_of(self, result: SimulationResult, arm: str = "B-full") -> float:
        return float(result.summary["arms"][arm]["closure_rate"])

    def _sensitivity(self) -> dict[str, Any]:
        ranges = self.parameters.get("sensitivity_parameters", {})
        base_config = self._analysis_config()
        arm_a_metric = self._metric_of(Simulator(base_config, deepcopy(self.parameters))._run_core(), "Arm A")
        oat: list[dict[str, Any]] = []
        for name, bounds in sorted(ranges.items()):
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                continue
            values: list[float] = []
            for value in bounds:
                params = deepcopy(self.parameters)
                params[name] = value
                measured = self._metric_of(Simulator(base_config, params)._run_core())
                values.append(measured)
            oat.append({"parameter": name, "low": bounds[0], "high": bounds[1],
                        "arm_a": round(arm_a_metric, 6), "low_metric": round(values[0], 6),
                        "high_metric": round(values[1], 6), "effect": round(values[1] - values[0], 6)})

        # A deterministic Latin hypercube uses a seeded permutation per
        # dimension and the midpoint of each stratum, so no external sampler
        # is needed and reruns are byte-for-byte reproducible.
        sample_count = 8
        dimensions = sorted(ranges)
        lhs: list[dict[str, Any]] = []
        for sample_index in range(sample_count):
            params = deepcopy(self.parameters)
            point: dict[str, Any] = {}
            for dimension_index, name in enumerate(dimensions):
                bounds = ranges[name]
                if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                    continue
                permutation = list(range(sample_count))
                random.Random(self.config.seed + dimension_index * 7919).shuffle(permutation)
                fraction = (permutation[sample_index] + 0.5) / sample_count
                value = bounds[0] + fraction * (bounds[1] - bounds[0])
                if isinstance(bounds[0], int) and isinstance(bounds[1], int):
                    value = int(round(value))
                params[name] = value
                point[name] = value
            measured = self._metric_of(Simulator(base_config, params)._run_core())
            lhs.append({"sample": sample_index + 1, "parameters": point, "b_full_closure_rate": round(measured, 6)})
        tornado = sorted(
            [{"parameter": row["parameter"], "effect": row["effect"],
              "low_metric": row["low_metric"], "high_metric": row["high_metric"]} for row in oat],
            key=lambda row: (-abs(row["effect"]), row["parameter"]),
        )
        return {"one_at_a_time": oat, "latin_hypercube": lhs, "tornado": tornado,
                "metric": "B-full.closure_rate", "analysis_cohort_size": base_config.cohort_size,
                "analysis_runs": base_config.runs}

    def _stress_scenarios(self) -> dict[str, Any]:
        scenarios = self.parameters.get("stress_scenarios", {})
        config = self._analysis_config()
        output: dict[str, Any] = {}
        for name, overrides in sorted(scenarios.items()):
            if not isinstance(overrides, dict):
                continue
            params = deepcopy(self.parameters)
            params.update(overrides)
            scenario = Simulator(config, params)._run_core()
            output[name] = {"parameters": overrides, "summary": scenario.summary,
                            "pathway_metrics": self._pathway_metrics(scenario)}
        return output

    def _v2_stress_scenarios(self) -> dict[str, Any]:
        configured = self.parameters.get("stress_scenarios_v2", {
            "insufficient_staff": {"capacity.navigators": 1, "capacity.providers": {"intake": 1, "owner": 1, "specialist": 1, "clinic": 1, "manager": 1}},
            "poor_contact_data": {"contact_data_quality": 0.45, "arm_a.loss_to_follow_up_probability": 0.12},
            "cross_provider_dominant": {"arm_a.cross_provider_probability": 0.85},
            "rare_reporting": {"unknown_partner_report_probability": 0.001},
            "e_consult_unavailable": {"econsult_unavailable_rate": 1.0},
        })
        output: dict[str, Any] = {}
        config = self._analysis_config()
        for name, overrides in sorted(configured.items()):
            if not isinstance(overrides, dict):
                continue
            params = deepcopy(self.parameters)
            params.update(overrides)
            scenario = Simulator(config, params)._run_core()
            output[name] = {"parameters": overrides, "summary": scenario.summary,
                            "ranges": self._scenario_ranges(scenario)}
        return output

    @staticmethod
    def _scenario_ranges(result: SimulationResult) -> dict[str, Any]:
        rows = [row for row in result.segment_metrics if row["segment"] == "all"]
        return {arm: {
            "closure_rate": Simulator._interval([row["closure_rate"] for row in rows if row["arm"] == arm], clamp=True),
            "closure_within_sla_rate": Simulator._interval([row["closure_within_sla_rate"] for row in rows if row["arm"] == arm], clamp=True),
        } for arm in Simulator.ARMS}


def simulate(config: SimulationConfig | None = None, parameters: dict[str, Any] | None = None) -> SimulationResult:
    return Simulator(config, parameters).run()
