# Assumptions and limitations

## Product and evidence status

CareLoop is a **prototype / hackathon demonstration**. It demonstrates a
workflow shape and deterministic software behavior; it does not establish
clinical effectiveness, safety, health outcomes, cost savings, equity impact,
or regulatory compliance. Every simulator parameter is marked `ASSUMPTION` and
has no external source in the supplied manifest.

## Simulation assumptions

* Cohorts are synthetic and sampled from hand-authored categorical weights.
* Arm A and B-full share seeded people and arm-independent hash draws
  to support paired comparison.
* Stage delays, success probabilities, capacities, segment modifiers, pathway
  modifiers, escalation effects, loss-to-follow-up, no-show, and unnecessary
  escalation settings are assumptions rather than observed estimates.
* Provider capacity is represented by simple earliest-slot queues; staffing,
  calendars, holidays, geography, and operational policies are not modeled.
* A failed step can be retried once after escalation; a second escalation stays
  unresolved. This is a simulator rule, not a care policy.
* Confidence intervals use a normal approximation over run-level metrics, as
  implemented in `Simulator._confidence_intervals`; they are not validated
  inferential estimates.
* The simulator reports completion timing and binary workflow outcomes, not
  clinical outcomes or diagnostic accuracy.
* transport-ledger ranges for barriers, distance, payer, partner reporting, e-consult,
  handoff, patient-pull, closure evidence, and mechanism effects are explicit
  assumptions until verified sources are found.
* The primary scenario is an abnormal mammogram requiring diagnostic imaging or
  biopsy. Stage 9 treatment/surveillance timing is configured as an operational
  assumption of 14 days urgent and 30 days routine; the applicable guideline
  was not verified in this session.

## API and domain limitations

* Demo fixtures are synthetic and startup seeding is local and deterministic.
* SQLite persistence is suitable for the demo; concurrency, migrations,
  backups, encryption, retention, and disaster recovery are not implemented.
* The schema enables SQLite foreign keys but does not declare foreign-key
  relationships in the current DDL.
* API case stages are free-form strings; the service layer does not enforce the
  domain engine's configured transition graph.
* The API and domain engine have separate role vocabularies and are not a
  complete identity or organization-access system.
* The FHIR result is explicitly R4-like, not a conformance-tested FHIR server.
* Audit rows are append-only by service behavior, but there is no tamper-proof
  storage, export signing, retention job, or administrator review workflow.
* The communication templates are fixed English/Arabic strings. Arabic is
  flagged for native-speaker review; no translation quality study is included.
* Teach-back response handling counts non-empty answers and records the
  patient's responses for staff review. It does not assess semantic
  understanding, literacy, diagnosis, urgency, or treatment choice.
* No message delivery provider, EHR connector, identity provider, or real-time
  notification channel is included.
* The seven-field E1-E9 event contract intentionally excludes clinical content;
  the API projection and event ledger are one prototype data model, but this is
  not a production integration contract.
* `UNKNOWN` means the partner event is not visible, not that the patient did
  not receive care. The absence detector cannot distinguish those states without
  a later reported event.

## Interpretation limits

Simulation deltas are conditional on the supplied assumptions and code. They
must not be described as expected clinical improvement or an ROI forecast.
Small demo test fixtures and synthetic case counts are not population evidence.
Any result promoted beyond a demo must be independently reproduced, reviewed
by clinical/operational stakeholders, and validated on an approved dataset.
