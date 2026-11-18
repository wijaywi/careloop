"""HTTP adapter smoke tests for the offline API surface."""

import io
import json
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

from api.app import create_wsgi_app
from api.service import CareLoopService


def request(app, method: str, path: str, *, actor: str = "navigator-1", payload: dict | None = None, query: str = ""):
    body = json.dumps(payload or {}).encode("utf-8")
    environ: dict = {}
    setup_testing_defaults(environ)
    environ.update({
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": "application/json",
        "HTTP_X_ACTOR_ID": actor,
        "wsgi.input": io.BytesIO(body),
    })
    status: list[str] = []
    response = b"".join(app(environ, lambda value, _headers: status.append(value)))
    decoded = json.loads(response.decode("utf-8")) if response else {}
    return int(status[0].split()[0]), decoded


class ApiHttpTests(unittest.TestCase):
    def setUp(self):
        self.service = CareLoopService(":memory:")
        self.service.load_demo_data(case_count=12)
        self.app = create_wsgi_app(self.service)

    def tearDown(self):
        self.service.close()

    def test_health_and_case_endpoint(self):
        status, health = request(self.app, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        status, detail = request(self.app, "GET", "/cases/demo-case-01")
        self.assertEqual(status, 200)
        self.assertEqual(detail["id"], "demo-case-01")

    def test_patient_rbac_is_enforced_at_endpoint(self):
        status, body = request(self.app, "GET", "/cases/demo-case-02", actor="patient-01")
        self.assertEqual(status, 403)
        self.assertEqual(body["type"], "AuthorizationError")

    def test_v2_loop_event_endpoint_keeps_transport_schema(self):
        status, loop = request(self.app, "POST", "/loops", payload={
            "patient_id": "synthetic-v2-patient",
            "owner_next": "navigator-org",
            "urgency": "routine",
        })
        self.assertEqual(status, 201)
        event_payload = {
            "event_type": "E1",
            "reporter_org": "screening-org",
            "owner_next": "navigator-org",
            "due_at": "2026-01-02T00:00:00+00:00",
            "evidence_ref": None,
        }
        status, event = request(self.app, "POST", f"/loops/{loop['loop_id']}/events", payload=event_payload)
        self.assertEqual(status, 201)
        self.assertEqual(set(event), {"loop_id", "event_type", "timestamp", "reporter_org", "owner_next", "due_at", "evidence_ref"})

    def test_wsgi_query_string_filters_and_preflight(self):
        status, body = request(self.app, "GET", "/cases", query="status=open")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 12)
        self.assertTrue(all(item["status"] == "open" for item in body["items"]))

        status, body = request(self.app, "GET", "/cases", actor="", query="actor_id=patient-01")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)

        status, _body = request(self.app, "OPTIONS", "/cases")
        self.assertEqual(status, 204)

    def test_demo_seed_bounds_case_count(self):
        for case_count in (0, 100000, "many"):
            status, body = request(self.app, "POST", "/demo/seed", payload={"case_count": case_count})
            self.assertEqual(status, 400, case_count)
            self.assertEqual(body["type"], "ValidationError")

    def test_unexpected_errors_return_generic_500(self):
        with patch.object(self.service, "list_case_summaries", side_effect=RuntimeError("secret path")):
            status, body = request(self.app, "GET", "/cases")
        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": "internal error"})

    def test_domain_errors_map_to_client_status_codes(self):
        payload = {
            "patient_id": "synthetic-duplicate",
            "owner_next": "navigator-org",
            "loop_id": "loop_" + "a" * 32,
        }
        status, _loop = request(self.app, "POST", "/loops", payload=payload)
        self.assertEqual(status, 201)
        status, _body = request(self.app, "POST", "/loops", payload=payload)
        self.assertEqual(status, 409)

        evidence = self.service.record_evidence("demo-case-01", "clinician-1", "review", "synthetic")
        status, body = request(self.app, "POST", "/cases/demo-case-01/actions", payload={
            "action": "close",
            "payload": {"evidence_id": evidence.id},
        })
        self.assertEqual(status, 400)
        self.assertEqual(body["type"], "ClosureError")


class FastApiAdapterTests(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("FastAPI is not installed")
        from api.app import create_app

        self.service = CareLoopService(":memory:")
        self.service.load_demo_data(case_count=12)
        self.client = TestClient(create_app(self.service))

    def tearDown(self):
        self.service.close()

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            "/demo/seed",
            content=b"{not-json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid JSON body")


if __name__ == "__main__":
    unittest.main()
