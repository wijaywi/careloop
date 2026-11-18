from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from careloop.loop_engine import (
    CareLoopLedger,
    ClosureCode,
    ClosureError,
    EConsultStatus,
    EVENT_FIELDS,
    ELEVEN_STAGE_MAPPING,
    LoopEvent,
    Patient,
    Urgency,
    load_sla_table,
)
from careloop.loop_engine.errors import ValidationError


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.loop = CareLoopLedger(
            clock=self.clock,
            sla_table=load_sla_table(
                '{"urgent":{"default":"4h"},"routine":{"default":"24h"}}'
            ),
        )
        self.loop.register_patient(
            Patient("patient-1", "Synthetic", "Arabic", "far", "transport", "family", "public")
        )
        self.record = self.loop.create_loop(
            "patient-1", "screening-org", "navigator-org", urgency=Urgency.URGENT, high_risk=True
        )

    def test_id_and_event_contract_are_pseudonymous_and_nonclinical(self) -> None:
        self.assertTrue(self.record.loop_id.startswith("loop_"))
        self.assertNotIn("patient-1", self.record.loop_id)
        event = self.loop.record_event(self.record.loop_id, "E1", reporter_org="screening-org")
        self.assertEqual(set(event.to_dict()), set(EVENT_FIELDS))
        with self.assertRaises(ValidationError):
            LoopEvent.from_mapping({**event.to_dict(), "diagnosis": "not allowed"})
        with self.assertRaises(ValidationError):
            self.loop.record_event(self.record.loop_id, "E9", reporter_org="screening-org")
        self.assertEqual([item.event_type for item in self.loop.events(self.record.loop_id)], ["E1"])

    def test_partner_failure_is_unknown_and_daily_report_has_required_fields(self) -> None:
        self.loop.record_event(self.record.loop_id, "E1", reporter_org="screening-org")
        gap = self.loop.report_partner_failure(self.record.loop_id, "E2", reporter_org="partner")
        self.assertEqual(gap.status, "UNKNOWN")
        report = self.loop.daily_absence_report()
        self.assertEqual(report[0].visibility, "UNKNOWN")
        self.assertEqual(report[0].expected_next_event, "E2")
        self.assertEqual(report[0].urgency, Urgency.URGENT)

    def test_handoff_keeps_sender_owner_until_acceptance_and_rejection_is_actionable(self) -> None:
        handoff = self.loop.propose_handoff(self.record.loop_id, "h1", "specialist-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).owner_next, "navigator-org")
        rejected = self.loop.reject_handoff("h1", reason="capacity", alternative_destination="backup-org")
        self.assertEqual(rejected.alternative_destination, "backup-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).owner_next, "navigator-org")
        handoff = self.loop.propose_handoff(self.record.loop_id, "h2", "specialist-org")
        self.loop.accept_handoff("h2", accepted_by="specialist-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).owner_next, handoff.destination)

    def test_econsult_supports_resolved_without_referral(self) -> None:
        consult = self.loop.request_econsult(
            self.record.loop_id,
            "c1",
            requester_org="navigator-org",
            destination_org="specialist-org",
            clinical_question="Is referral required?",
            minimal_data_package={"screening_date": "2026-01-01"},
        )
        resolved = self.loop.resolve_econsult("c1", resolution="Monitor", resolved_without_referral=True)
        self.assertEqual(consult.status, EConsultStatus.REQUESTED)
        self.assertEqual(resolved.status, EConsultStatus.RESOLVED_WITHOUT_REFERRAL)

    def test_result_passport_and_patient_pull_contact_are_separate(self) -> None:
        passport = self.loop.issue_result_passport(
            self.record.loop_id,
            meaning="Actionable result",
            next_step_owner="navigator-org",
            no_contact_instruction="Call the navigator if nobody calls.",
        )
        self.assertEqual(self.loop.pull_result_passport(self.record.loop_id), passport)
        contact = self.loop.pull_contact(
            self.record.loop_id, contact_method="phone", reporter_org="patient"
        )
        self.assertEqual(contact.patient_id, "patient-1")

    def test_closure_gate_requires_evidence_and_human_authorization_for_high_risk(self) -> None:
        with self.assertRaises(ClosureError):
            self.loop.close_loop(self.record.loop_id, closure_code=ClosureCode.COMPLETED)
        with self.assertRaises(ClosureError):
            self.loop.close_loop(self.record.loop_id, closure_code=ClosureCode.COMPLETED, evidence_refs=("ev-1",))
        self.loop.authorize_high_risk(
            self.record.loop_id, authorization_id="auth-1", authorized_by="clinician", rationale="reviewed"
        )
        closed = self.loop.close_loop(
            self.record.loop_id, closure_code=ClosureCode.COMPLETED, evidence_refs=("ev-1",)
        )
        self.assertEqual(closed.closure_code, ClosureCode.COMPLETED)

    def test_sla_hook_and_eleven_stage_mapping(self) -> None:
        self.assertEqual(len(ELEVEN_STAGE_MAPPING), 11)
        self.loop.set_escalation_probability_hook(lambda loop, level: 0.75)
        assessment = self.loop.escalation_success_probability(self.record.loop_id, level=2)
        self.assertEqual(assessment.probability, 0.75)


if __name__ == "__main__":
    unittest.main()
