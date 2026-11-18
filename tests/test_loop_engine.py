from __future__ import annotations

import unittest
from datetime import datetime, timezone

from careloop.loop_engine import (
    CareLoopLedger,
    ClosureCode,
    ClosureError,
    Patient,
    Urgency,
    canonical_loop_id,
)


class CanonicalLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = CareLoopLedger(clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.loop.register_patient(Patient("patient-1", "Synthetic Patient", "English"))
        self.record = self.loop.create_loop(
            "patient-1", "screening-org", "navigator-org", urgency=Urgency.ROUTINE
        )

    def test_transport_events_are_the_single_state_transition_contract(self) -> None:
        self.assertEqual(self.record.stage, "result_issued")
        self.loop.record_event(self.record.loop_id, "E1", reporter_org="screening-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).stage, "notification")
        self.loop.record_event(self.record.loop_id, "E2", reporter_org="screening-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).stage, "acknowledgement")
        with self.assertRaises(Exception):
            self.loop.record_event(self.record.loop_id, "E8", reporter_org="screening-org")
        self.assertEqual(
            [item.event_type for item in self.loop.events(self.record.loop_id)], ["E1", "E2"]
        )

    def test_pseudonymous_identifier_does_not_expose_patient_reference(self) -> None:
        identifier = canonical_loop_id("patient-1")
        self.assertTrue(identifier.startswith("loop_"))
        self.assertNotIn("patient-1", identifier)

    def test_closure_requires_typed_code_and_evidence(self) -> None:
        with self.assertRaises(ClosureError):
            self.loop.close_loop(self.record.loop_id, closure_code=ClosureCode.COMPLETED)
        with self.assertRaises(ClosureError):
            self.loop.close_loop(self.record.loop_id, closure_code="free-text")
        closed = self.loop.close_loop(
            self.record.loop_id,
            closure_code=ClosureCode.COMPLETED,
            evidence_refs=("evidence-1",),
        )
        self.assertEqual(closed.closure_code, ClosureCode.COMPLETED)
        self.assertEqual(closed.evidence_refs, ("evidence-1",))

    def test_high_risk_closure_requires_explicit_human_authorization(self) -> None:
        high_risk = self.loop.create_loop(
            "patient-1", "screening-org", "navigator-org", high_risk=True,
            loop_id=canonical_loop_id("patient-1", namespace="high-risk"),
        )
        with self.assertRaises(ClosureError):
            self.loop.close_loop(high_risk.loop_id, closure_code=ClosureCode.COMPLETED, evidence_refs=("ev",))
        self.loop.authorize_high_risk(
            high_risk.loop_id,
            authorization_id="auth-1",
            authorized_by="clinician-1",
            rationale="Synthetic human review",
        )
        closed = self.loop.close_loop(high_risk.loop_id, closure_code=ClosureCode.COMPLETED, evidence_refs=("ev",))
        self.assertEqual(closed.authorization_id, "auth-1")

    def test_positive_handoff_keeps_sender_until_acceptance(self) -> None:
        handoff = self.loop.propose_handoff(self.record.loop_id, "handoff-1", "specialist-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).owner_next, "navigator-org")
        self.loop.accept_handoff(handoff.handoff_id, accepted_by="specialist-org")
        self.assertEqual(self.loop.get_loop(self.record.loop_id).owner_next, "specialist-org")


if __name__ == "__main__":
    unittest.main()
