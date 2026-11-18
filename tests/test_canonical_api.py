from __future__ import annotations

import contextlib
import io
import inspect
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from api import create_service
from api.app import serve
from careloop.loop_engine import ClosureCode, ClosureError, LoopRecord, ValidationError


class _FakeServer:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def serve_forever(self):
        return None


class CanonicalApiTests(unittest.TestCase):
    def test_sqlite_cases_use_the_single_canonical_loop_record(self):
        service = create_service(seed=True)
        try:
            record = service.list_cases("manager-1")[0]
            self.assertIs(service.loop, service.ledger)
            self.assertIsInstance(record, LoopRecord)
            self.assertEqual(service.case_id_for_loop(record.loop_id), "demo-case-01")
        finally:
            service.close()

    def test_closure_requires_typed_code_evidence_and_human_authorization_when_high_risk(self):
        service = create_service(seed=True)
        try:
            service.create_case("high-risk", "patient-01", "Synthetic high-risk case", "navigator-1", actor_id="manager-1", high_risk=True)
            evidence = service.record_evidence("high-risk", "clinician-1", "review", "Synthetic review")
            with self.assertRaises(ClosureError):
                service.close_case("high-risk", "clinician-1", evidence_id=evidence.id)
            with self.assertRaises(ClosureError):
                service.close_case("high-risk", "clinician-1", evidence_id=evidence.id, closure_code=ClosureCode.COMPLETED)
            with self.assertRaises(ClosureError):
                service.action("high-risk", "clinician-1", "close", {"closure_basis": "free text"})
            closed = service.close_case("high-risk", "clinician-1", evidence_id=evidence.id, closure_code=ClosureCode.COMPLETED, authorization_id="auth-high-risk", authorized_by="manager-1", rationale="Synthetic human review")
            self.assertEqual(closed.closure_code, ClosureCode.COMPLETED)
            self.assertEqual(closed.evidence_refs, (evidence.id,))
        finally:
            service.close()

    def test_transition_graph_rejects_non_adjacent_canonical_stage(self):
        service = create_service(seed=True)
        try:
            with self.assertRaises(ValidationError):
                service.transition_case("demo-case-01", "manager-1", "treatment")
            changed = service.transition_case("demo-case-01", "manager-1", "notification")
            self.assertEqual(changed.stage, "notification")
        finally:
            service.close()

    def test_invalid_initial_stage_does_not_mutate_ledger(self):
        service = create_service(seed=True)
        try:
            before = len(service.ledger._loops)
            with self.assertRaises(ValidationError):
                service.create_case(
                    "orphan-case", "patient-01", "Synthetic", "navigator-1",
                    actor_id="manager-1", stage="notification",
                )
            self.assertEqual(len(service.ledger._loops), before)
        finally:
            service.close()

    def test_closed_case_rejects_operational_mutations(self):
        service = create_service(seed=True)
        try:
            evidence = service.record_evidence("demo-case-01", "clinician-1", "review", "Synthetic review")
            service.close_case(
                "demo-case-01", "clinician-1",
                evidence_id=evidence.id, closure_code=ClosureCode.COMPLETED,
            )
            with self.assertRaises(ValidationError):
                service.handoff_case("demo-case-01", "navigator-1", "navigator-2")
            with self.assertRaises(ValidationError):
                service.escalate_case("demo-case-01", "manager-1", "synthetic")
            with self.assertRaises(ValidationError):
                service.schedule_appointment("demo-case-01", "manager-1", "2026-12-01T09:00:00+00:00")
            with self.assertRaises(ValidationError):
                service.authorize_closure(
                    "demo-case-01", "manager-1",
                    authorization_id="auth-after-close", authorized_by="manager-1", rationale="synthetic",
                )
        finally:
            service.close()

    def test_transport_closure_records_e9_and_rejects_invalid_contract(self):
        service = create_service()
        try:
            loop = service.create_transport_loop({"patient_id": "synthetic", "owner_next": "navigator-org"})
            with self.assertRaises(ClosureError):
                service.close_transport_loop(loop["loop_id"], {"closure_code": "Completed"})
            self.assertEqual(service.ledger.events(loop["loop_id"]), ())

            closed = service.close_transport_loop(
                loop["loop_id"],
                {"closure_code": "Completed", "evidence_refs": ["evidence-synthetic"]},
            )
            self.assertEqual(closed["status"], "closed")
            self.assertEqual(
                [event.event_type for event in service.ledger.events(loop["loop_id"])], ["E9"]
            )
            with self.assertRaises(ValidationError):
                service.close_transport_loop(
                    loop["loop_id"],
                    {"closure_code": "Completed", "evidence_refs": ["evidence-synthetic"]},
                )
        finally:
            service.close()

    def test_stalled_scenario_is_idempotent_after_closure(self):
        service = create_service()
        try:
            first = service.run_stalled_case_scenario()
            self.assertEqual(first["case"]["status"], "closed")
            before = service.get_case("manager-1", "demo-stalled-case")
            second = service.run_stalled_case_scenario()
            self.assertEqual(second["case"]["status"], "closed")
            self.assertEqual(second["steps"], ["already_closed"])
            after = service.get_case("manager-1", "demo-stalled-case")
            for key in ("escalations", "handoffs", "evidence", "events"):
                self.assertEqual(len(before[key]), len(after[key]), key)
        finally:
            service.close()

    def test_import_api_has_no_database_side_effect(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "side-effect.sqlite3")
            env = {**os.environ, "CARELOOP_DB": db_path, "PYTHONPATH": str(root)}
            result = subprocess.run(
                [sys.executable, "-B", "-c", "import api"],
                cwd=root, env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(os.path.exists(db_path))

    def test_default_bind_is_loopback_and_non_loopback_prints_warning(self):
        self.assertEqual(inspect.signature(serve).parameters["host"].default, "127.0.0.1")
        fake_uvicorn = types.SimpleNamespace(run=lambda *_args, **_kwargs: None)
        output = io.StringIO()
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}), patch("api.app.make_server", return_value=_FakeServer()), contextlib.redirect_stdout(output):
            serve("0.0.0.0", 0)
        self.assertIn("WARNING", output.getvalue())
        self.assertIn("non-loopback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
