"""Focused behavior tests for the offline CareLoop API service."""

import tempfile
from pathlib import Path
import unittest

from api import AuthorizationError, create_service


class CareLoopApiTests(unittest.TestCase):
    def test_seed_is_deterministic_and_small_cells_are_suppressed(self):
        service = create_service(seed=True, seed_value=7)
        self.assertEqual(len(service.list_cases("manager-1")), 12)
        report = service.analytics("manager-1", group_by="stage")
        self.assertEqual(report["threshold"], 10)
        self.assertTrue(all(group["suppressed"] for group in report["groups"]))
        self.assertTrue(all(group["count"] is None for group in report["groups"]))

    def test_rbac_patient_sees_only_own_case_and_cannot_close(self):
        service = create_service(seed=True)
        cases = service.list_cases("patient-01")
        self.assertEqual([case.patient_id for case in cases], ["patient-01"] * len(cases))
        with self.assertRaises(AuthorizationError):
            service.get_case("patient-01", "demo-case-02")
        with self.assertRaises(AuthorizationError):
            service.action("demo-case-01", "patient-01", "close", {"closure_basis": "not a patient decision"})

    def test_stalled_escalation_handoff_evidence_closure_and_fhir(self):
        service = create_service()
        result = service.run_stalled_case_scenario()
        self.assertEqual(result["case"]["status"], "closed")
        self.assertEqual(result["steps"][0], "stall_detected")
        self.assertIn("case_escalated", [event["action"] for event in result["audit"]])
        bundle = service.fhir_export("manager-1", "demo-stalled-case")
        resource_types = {entry["resource"]["resourceType"] for entry in bundle["entry"]}
        self.assertTrue({"Task", "Communication", "ServiceRequest", "DiagnosticReport"}.issubset(resource_types))

    def test_case_list_summaries_use_a_bounded_query_count(self):
        service = create_service(seed=True)
        try:
            statements: list[str] = []
            service.db.set_trace_callback(statements.append)
            try:
                items = service.list_case_summaries("manager-1")
            finally:
                service.db.set_trace_callback(None)
            self.assertEqual(len(items), 12)
            self.assertLessEqual(len(statements), 4)
            self.assertNotIn("events", items[0])
            self.assertTrue({"id", "status", "stage", "owner_id"} <= set(items[0]))
        finally:
            service.close()

    def test_sqlite_records_survive_service_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "careloop.sqlite3")
            first = create_service(db_path)
            first.load_demo_data(case_count=10)
            first.close()
            second = create_service(db_path)
            self.assertEqual(len(second.list_cases("manager-1")), 10)
            second.close()


if __name__ == "__main__":
    unittest.main()
