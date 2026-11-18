# Recorded decisions

These decisions describe choices visible in the current implementation.

## D-001 — Offline standard-library core

**Decision:** Keep the core API, simulator, and tests runnable with Python's
standard library; optional FastAPI/Uvicorn support may improve serving.

**Evidence:** `requirements.txt` documents no third-party runtime dependency;
`requirements.lock` is intentionally empty; `api.app` has a WSGI fallback;
parameter loading accepts the supplied JSON-compatible manifest without
PyYAML.

**Consequence:** Reproducibility is strong offline, while production HTTP,
identity, and integration capabilities are outside this prototype.

## D-002 — Synthetic-only fixtures and explicit provenance

**Decision:** Keep demo data synthetic and require every manifest record to be
`ASSUMPTION` with a null source.

**Evidence:** `load_demo_data` creates synthetic users/cases; the manifest and
`validate_parameter_document` enforce the status/source rule.

**Consequence:** No clinical or population claim can be inferred from default
outputs; a real-data onboarding gate is required.

## D-003 — Human review at the communication boundary

**Decision:** Use fixed templates and mark every rendered message/teach-back response
result for clinical review, with Arabic native-speaker review.

**Evidence:** `api/communication.py` emits the review flags and explicitly
sets `clinical_decision_by_ai` to false.

**Consequence:** The demo avoids automated diagnosis/treatment decisions, but
translation, readability, and workflow usability still need validation.

## D-004 — Evidence-backed closure

**Decision:** Require case-scoped evidence or a documented human decision for
domain closure; the API requires evidence or an explicit closure basis.

**Evidence:** `CareLoop.close_case` and `CareLoopService.close_case` reject
unsupported closure requests.

**Consequence:** Closure is auditable, but the prototype does not judge whether
evidence is clinically sufficient.

## D-005 — Paired deterministic simulation

**Decision:** Compare Arm A and B-full on shared seeded cohorts and
arm-independent deterministic draws.

**Evidence:** `Simulator._cohort` and `_draw`; the test suite checks
determinism and equality when B-full mechanism effects are set to zero.

**Consequence:** Changes can be attributed within the model more cleanly, but
the result remains assumption-dependent and not externally validated.

## D-006 — Small-cell suppression

**Decision:** Suppress aggregate case counts below 10.

**Evidence:** `SMALL_CELL_THRESHOLD = 10` and `CareLoopService.analytics` return
null counts with `suppressed: true` below the threshold.

**Consequence:** This reduces demo disclosure risk but is not a complete privacy
or disclosure-control program.

## D-007 — Self-contained repository root

**Decision:** Keep all CareLoop code, tests, parameters, scripts, web client,
documentation, and outputs in one self-contained repository root.

**Consequence:** The health prototype has its own runtime, API, web build,
database, and documentation boundary.

## D-008 — Bounded reproduction versus full study

**Decision:** `make reproduce` uses a bounded 100-person × 2-run analysis so it
can complete on a developer machine; `make simulate` retains the required
10,000-person × 500-run manifest defaults.

**Consequence:** The checked evaluation artefacts are explicitly bounded. The
full-study command is available but its output is not claimed until executed.

## D-009 — Local-first web prototype

**Decision:** The React/Vite interface uses deterministic local demo state and
does not require an API or network connection to demonstrate the screens.

**Consequence:** The UI is reliable for an offline judging demo, while a future
integration must connect the visible actions to authenticated API calls.

## D-010 — transport-ledger transport contract is separate from clinical content

**Decision:** The shared partner event schema accepts exactly seven fields and
does not carry diagnosis, test values, or treatment content. Clinical context
stays behind the local case/consult boundary.

**Consequence:** Partners can report loop progress without sharing unnecessary
clinical content, but a real deployment still needs a governed identity and
minimum-data exchange contract.

## D-011 — Unknown is not failure-to-complete

**Decision:** A partner reporting failure creates `UNKNOWN` visibility and is
counted separately from an absent event. The daily detector reports what is
expected next without asserting that the underlying care did not happen.

**Consequence:** Visibility gaps remain measurable without turning incomplete
data into a false clinical outcome.

## D-012 — English application copy

**Decision:** Use an abnormal mammogram requiring diagnostic imaging or biopsy
as the primary transport-ledger scenario. Configure Stage 9 treatment/surveillance
start at 14 days for urgent cases and 30 days for routine cases.

**Evidence:** `params/sla_policy_v2.json` and the `primary_screening_type` and
`sla_table_v2` manifest records. Both are explicitly marked assumptions because
no clinical guideline source was verified in this session.

**Consequence:** The prototype has a concrete Stage 9 scenario for the demo and
simulation configuration, but the policy must be replaced or validated by the
clinical governance team before real use.

## D-013 — Primary screening scenario and Stage 9 policy

**Decision:** Active UI copy, navigation, documentation, and API messages are
English. Multilingual patient message templates remain structured data with
native-speaker and clinical-review flags for a future reviewed translation
workflow.

**Consequence:** The prototype is consistent for an English-language demo while
retaining the data contract needed to test language-concordant communication.
