# Architecture

## Scope

The implementation has four cooperating slices:

1. **Canonical ledger (`careloop/loop_engine/ledger.py`)** — `CareLoopLedger`
   owns the E1-E9 event contract, stage graph, SLA state, handoffs, e-consults,
   passports, visibility gaps, and closure contract.
2. **HTTP adapter (`api/app.py`)** — a shared route dispatcher is exposed
   through FastAPI when installed, otherwise through a dependency-free WSGI
   adapter.
3. **SQLite projection (`api/service.py`)** — `CareLoopService` persists
   canonical loop records, events, evidence, authorization, and ancillary
   artifacts while applying demo role checks.
4. **Simulator and web adapters** — the deterministic simulator and React/Vite
   client consume the same naming and transport contract.

The simulator (`careloop/simulator/`) runs
   paired Arm A and B-full arms over shared seeded cohorts and aggregates
   segment/pathway metrics, ablations, uncertainty, visibility, leakage, and
   workload outputs.
Communication helpers in `api/communication.py` render fixed English/Arabic
templates and fixed teach-back questions. They do not call a model or make a
clinical decision.

The web client uses `web/src/api/client.ts` for health, demo-seeding, and case
action calls. Vite proxies `/api` to `127.0.0.1:8000` during development. If
the API is unavailable, the UI keeps a labelled synthetic local fallback so an
offline demo remains usable; this fallback is not production synchronization.

## API request flow

```text
HTTP request
  -> WSGI/FastAPI adapter
  -> shared build_routes dispatcher
  -> X-Actor-ID/query actor resolution
  -> CareLoopService authorization + SQLite transaction
  -> model dump / JSON response
```

`python -m api` creates a service, loads synthetic demo data, and starts the
optional Uvicorn/FastAPI path or standard-library WSGI server. `CARELOOP_DB`
selects the SQLite file; the default is in-memory.

## API capabilities implemented in code

| Route | Behavior |
| --- | --- |
| `GET /health` | Returns service status and the four API role names. |
| `POST /demo/seed` | Inserts deterministic synthetic users/cases; default case count is 12. |
| `POST /demo/scenario` | Runs stall detection → escalation → handoff → synthetic evidence → closure. |
| `GET /cases` / `POST /cases` | Lists role-filtered cases or creates a care-team-owned case. |
| `GET /cases/{id}` | Returns case details and consent, evidence, escalation, handoff, and appointment records. |
| `POST /cases/{id}/actions` | Dispatches acknowledge, transition, escalate, handoff, evidence, consent, appointment, teach_back, or close. |
| `GET /cases/{id}/audit`, `GET /audit` | Reads append-only audit rows for care-team roles. |
| `GET /cases/{id}/fhir` | Emits a FHIR R4-like Bundle with Task, Communication, ServiceRequest and optional Appointment/DiagnosticReport references. |
| `GET /analytics/cases` | Groups by stage, status, or owner and suppresses counts below 10. |
| `POST /loops` | Opens a pseudonymous transport-ledger loop with urgency and next owner. |
| `POST /loops/{id}/events` | Accepts exactly the transport-only E1-E9 event fields. |
| `GET /loops/{id}/absence` | Returns the expected next event, deadline, urgency, and visibility. |
| `POST /loops/{id}/close` | Applies a typed, evidence-gated transport-ledger closure. |

The route dispatcher returns 400 for validation errors, 403 for authorization
errors, 404 for missing resources, and 500 for otherwise unhandled errors.

## Persistence model

`CareLoopService._init_schema()` creates SQLite projections for users, cases,
ledger events, closure authorizations, audit rows, evidence, handoffs, and
ancillary records. The code enables SQLite foreign keys, but the current DDL
does not declare foreign-key constraints; this is a known prototype limitation.

## Domain loop model

`CareLoopLedger` keeps typed loop records and an append-only E1-E9 event list.
Stage transitions are legal only when the expected event for the current stage
is recorded. Closure requires a typed closure code and evidence reference; a
high-risk loop additionally requires a recorded human authorization.

The simulator configures five stages—`notification`, `confirmation`,
`consult`, `treatment`, and `closure`—with SLAs of 1, 2, 10, 10, and 1 day in
`careloop/simulator/engine.py`. These values are **CODE**, but their use in a
clinical pathway is not evidence of a clinical standard.

## Simulator flow

Each run creates a seeded cohort, then sends the same cohort through `Arm A`
and `B-full` arms plus explicit ablations. An event heap processes notification,
consult, treatment, escalation, and closure events. Provider-slot capacity can
create backlog. Deterministic SHA-256 draws omit the arm label so a zero-effect
configuration can be compared pairwise. Results are written as JSON and/or a
flat CSV through `SimulationResult`.

The default CLI is a quick run (1,000 cohort members × 10 runs); `--full`
selects the manifest's 10,000 × 500 × 90-day defaults. Both are **CODE** and
**ASSUMPTION** where the values originate in the manifest.

transport-ledger additionally emits Arm A, B-full, and four component ablations. It
uses the same cohort seed across arms and records model mechanics for patient
distance, barriers, payer, companions, provider changes, patient-pull contact,
e-consult availability, partner reporting failures, and positive handoff
rerouting. The output includes 95% replication intervals, uncertainty hours,
unknown visibility rate, typed closure/evidence distributions, leakage by
language/distance/age/payer, FIFO versus priority workload, and the core metric
of named owner plus documented closure within SLA.

## Roles and boundaries

The API service roles are `navigator`, `clinician`, `program_manager`, and
`patient`. The domain engine has its own generic roles (`PATIENT`, `PROVIDER`,
`STAFF`, `COORDINATOR`, `ADMIN`) because it is a reusable domain slice. They
should not be treated as a single production identity model without an
explicit mapping and security review.
