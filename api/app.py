"""HTTP API for CareLoop.

Endpoints:

* ``GET /health`` - readiness and role list.
* ``POST /demo/seed`` and ``POST /demo/scenario`` - synthetic fixtures.
* ``GET /cases`` / ``POST /cases`` - role-filtered list and case creation.
* ``GET /cases/{id}`` - case detail with consent, evidence, handoffs, and audit.
* ``POST /cases/{id}/actions`` - explicit RBAC-protected case action dispatcher.
* ``GET /cases/{id}/audit`` and ``GET /audit`` - append-only audit log.
* ``GET /cases/{id}/fhir`` - basic FHIR R4-like export.
* ``GET /analytics/cases`` - aggregate counts with threshold-10 suppression.
* ``POST /v2/loops`` and related routes - compatibility URLs backed by the
  same canonical E1-E9 ledger used by case operations.

The FastAPI adapter is optional.  ``create_wsgi_app`` provides a dependency-free
WSGI implementation suitable for offline tests and local use.
"""

import json
import logging
import os
from http import HTTPStatus
from io import BytesIO
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server
from typing import Any, Callable

from careloop.loop_engine.errors import ClosureError, DuplicateEntityError

from .service import AuthorizationError, CareLoopError, CareLoopService, NotFoundError, ValidationError

DEFAULT_ACTOR = "navigator-1"

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _actor(headers: Any, query: dict[str, list[str]]) -> str:
    return headers.get("x-actor-id") or headers.get("X-Actor-ID") or (query.get("actor_id") or [DEFAULT_ACTOR])[0]


def _error_status(error: Exception) -> int:
    if isinstance(error, AuthorizationError):
        return 403
    if isinstance(error, NotFoundError):
        return 404
    if isinstance(error, DuplicateEntityError):
        return 409
    if isinstance(error, (ValidationError, ClosureError)):
        return 400
    return 500


def _payload(request: Any) -> dict[str, Any]:
    try:
        value = request.json()
    except Exception:
        value = {}
    return value if isinstance(value, dict) else {}


def build_routes(service: CareLoopService) -> Callable[[str, str, dict[str, list[str]], dict[str, Any], Any], tuple[int, Any]]:
    """Build the route dispatcher shared by FastAPI and WSGI adapters."""

    def dispatch(method: str, path: str, query: dict[str, list[str]], payload: dict[str, Any], headers: Any) -> tuple[int, Any]:
        actor = _actor(headers, query)
        try:
            if method == "GET" and path == "/health":
                return 200, {"status": "ok", "service": "careloop-api", "roles": sorted(("navigator", "clinician", "program_manager", "patient"))}
            if method == "POST" and path == "/loops":
                return 201, service.create_transport_loop(payload)
            if method == "POST" and path.startswith("/loops/") and path.endswith("/events"):
                loop_id = path[len("/loops/"):-len("/events")].rstrip("/")
                return 201, service.record_transport_event(loop_id, payload)
            if method == "GET" and path.startswith("/loops/") and path.endswith("/absence"):
                loop_id = path[len("/loops/"):-len("/absence")].rstrip("/")
                return 200, {"items": service.transport_absence(loop_id)}
            if method == "POST" and path.startswith("/loops/") and path.endswith("/close"):
                loop_id = path[len("/loops/"):-len("/close")].rstrip("/")
                return 200, service.close_transport_loop(loop_id, payload)
            if method == "GET" and path.startswith("/loops/"):
                return 200, service.get_transport_loop(path[len("/loops/"):].rstrip("/"))
            if method == "POST" and path == "/demo/seed":
                try:
                    seed = int(payload.get("seed", 20261019))
                    case_count = int(payload.get("case_count", 12))
                except (TypeError, ValueError) as exc:
                    raise ValidationError("seed and case_count must be integers") from exc
                return 200, service.load_demo_data(seed=seed, case_count=case_count)
            if method == "POST" and path == "/demo/scenario":
                return 200, service.run_stalled_case_scenario(actor_id=actor)
            if method == "GET" and path == "/cases":
                cases = service.list_case_summaries(actor, status=(query.get("status") or [None])[0], patient_id=(query.get("patient_id") or [None])[0])
                return 200, {"items": cases, "count": len(cases)}
            if method == "POST" and path == "/cases":
                item = service.create_case(str(payload["id"]), str(payload["patient_id"]), str(payload.get("title", "CareLoop case")), str(payload["owner_id"]), actor_id=actor, stage=str(payload.get("stage", "result_issued")), high_risk=bool(payload.get("high_risk", False)), urgency=str(payload.get("urgency", "routine")))
                return 201, service._case_payload(str(payload["id"]), str(payload.get("title", "CareLoop case")), item)
            if method == "GET" and path == "/audit":
                return 200, {"items": [item.model_dump() for item in service.audit(actor)]}
            if method == "GET" and path == "/analytics/cases":
                return 200, service.analytics(actor, group_by=(query.get("group_by") or ["stage"])[0])
            if method == "GET" and path.startswith("/cases/"):
                remainder = path[len("/cases/"):]
                case_id, _, suffix = remainder.partition("/")
                if suffix == "fhir":
                    return 200, service.fhir_export(actor, case_id)
                if suffix == "audit":
                    return 200, {"items": [item.model_dump() for item in service.audit(actor, case_id=case_id)]}
                if not suffix:
                    return 200, service.get_case(actor, case_id)
            if method == "POST" and path.startswith("/cases/") and path.endswith("/actions"):
                case_id = path[len("/cases/"):-len("/actions")].rstrip("/")
                return 200, service.action(case_id, actor, str(payload.get("action", "")), payload.get("payload", payload))
            if method == "POST" and path.startswith("/cases/") and path.endswith("/consents"):
                case_id = path[len("/cases/"):-len("/consents")].rstrip("/")
                item = service.record_consent(case_id, actor, str(payload.get("scope", "care_coordination")), bool(payload.get("granted", False)), consent_id=payload.get("id"))
                return 201, item.model_dump()
            return 404, {"error": "route not found"}
        except CareLoopError as error:
            return _error_status(error), {"error": str(error), "type": type(error).__name__}
        except (KeyError, TypeError, ValueError) as error:
            return 400, {"error": str(error), "type": type(error).__name__}
        except Exception:  # Keep the HTTP adapter from leaking internals.
            logger.exception("unhandled API error")
            return 500, {"error": "internal error"}

    return dispatch


class WSGIApp:
    """Minimal standard-library WSGI adapter used when FastAPI is unavailable."""

    def __init__(self, service: CareLoopService):
        self.service = service
        self.dispatch = build_routes(service)

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        parsed = urlparse(environ.get("PATH_INFO", "/"))
        query = parse_qs(environ.get("QUERY_STRING") or parsed.query)
        cors_headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Headers", "Content-Type, X-Actor-ID"),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ]
        if method == "OPTIONS":
            start_response("204 No Content", [("Content-Length", "0"), *cors_headers])
            return [b""]
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ.get("wsgi.input", BytesIO()).read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            payload = {}
        headers = {key[5:].lower().replace("_", "-"): value for key, value in environ.items() if key.startswith("HTTP_")}
        status, body = self.dispatch(method, parsed.path.rstrip("/") or "/", query, payload if isinstance(payload, dict) else {}, headers)
        encoded = json.dumps(_jsonable(body), ensure_ascii=False).encode("utf-8")
        phrase = HTTPStatus(status).phrase if status in HTTPStatus._value2member_map_ else "Error"
        start_response(f"{status} {phrase}", [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(encoded))),
            *cors_headers,
        ])
        return [encoded]


def create_wsgi_app(service: CareLoopService | None = None) -> WSGIApp:
    """Return the dependency-free WSGI app."""

    return WSGIApp(service or CareLoopService(os.environ.get("CARELOOP_DB", ":memory:")))


def create_app(service: CareLoopService | None = None, *, seed: bool = False, db_path: str | None = None) -> Any:
    """Create FastAPI when present, otherwise return :class:`WSGIApp`."""

    service = service or CareLoopService(db_path or os.environ.get("CARELOOP_DB", ":memory:"))
    if seed:
        service.load_demo_data()
    try:
        from fastapi import FastAPI, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse

        application = FastAPI(title="CareLoop API", version="1.0.0", description=__doc__)
        application.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-Actor-ID"],
        )
        dispatch = build_routes(service)

        @application.api_route("/{full_path:path}", methods=["GET", "POST"])
        async def catch_all(full_path: str, request: Request) -> JSONResponse:
            path = "/" + full_path
            query = parse_qs(request.url.query)
            payload: dict[str, Any] = {}
            if request.method == "POST" and request.headers.get("content-length", "0") != "0":
                try:
                    parsed = await request.json()
                except (ValueError, UnicodeDecodeError):
                    return JSONResponse(content={"error": "invalid JSON body", "type": "ValidationError"}, status_code=400)
                payload = parsed if isinstance(parsed, dict) else {}
            status, body = dispatch(request.method, path.rstrip("/") or "/", query, payload, request.headers)
            return JSONResponse(content=_jsonable(body), status_code=status)

        application.state.careloop_service = service
        return application
    except ImportError:
        return WSGIApp(service)


# Importing ``api.app`` is side-effect free.  The module entrypoint
# (``serve``) creates and seeds the single service that owns the database.


def __getattr__(name: str) -> Any:
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the fallback HTTP server with synthetic demo data."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"WARNING: API is binding to non-loopback host {host!r}")
    service = CareLoopService(os.environ.get("CARELOOP_DB", ":memory:"))
    service.load_demo_data()
    try:
        import uvicorn
        fastapi_app = create_app(service)
        if not isinstance(fastapi_app, WSGIApp):
            uvicorn.run(fastapi_app, host=host, port=port)
            return
    except ImportError:
        pass
    with make_server(host, port, WSGIApp(service)) as server:
        print(f"CareLoop API listening on http://{host}:{port}")
        server.serve_forever()
