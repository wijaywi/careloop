# Responsible AI and automation boundaries

## Position

The current implementation is deterministic software and does not invoke a
generative or predictive AI model. It is still an automation system in a
health context, so the prototype treats human accountability, minimum data,
access control, and clear uncertainty as first-class requirements.

## Human decision boundary

`api/communication.py` returns `clinical_decision_by_ai: False` and
`requires_clinical_review: True` for every rendered message and teach-back
response. Templates only format approved language. The helper counts non-empty
answers and records the patient's teach-back responses for staff review; it does
not assess understanding, diagnose, triage, or recommend treatment.

Case closure requires a typed closure code and a case-scoped evidence
identifier. High-risk closure additionally requires explicit human
authorization. This is an auditability control, not a substitute for clinical
judgment.

transport-ledger strengthens the boundary with a closure contract, typed closure
codes, mandatory evidence references for E9, and explicit authorization for
high-risk loops. A partner reporting failure is represented as `UNKNOWN`, not
as a claim that care did not occur. The absence detector only identifies an
expected event that is not visible by its deadline.

## Access and privacy controls present in code

* API roles are navigator, clinician, program manager, and patient.
* Patients can list and access only their own case and cannot close cases,
  transition cases, escalate, view aggregate analytics, or view the audit log.
* Care-team mutations append an audit row with actor, action, payload, and
  timestamp.
* Analytics suppress counts below the code threshold of 10 to reduce small-cell
  disclosure in the demo.
* The default data is synthetic, and the code has no external data connector.
* E1-E9 partner events accept only loop progress fields and no clinical
  content.
* Positive handoff keeps the sender as owner until explicit acceptance;
  rejection requires a reason and alternative destination.

These are prototype controls. SQLite permissions, transport security,
authentication, authorization testing at deployment scale, and retention are
not supplied.

## Language and accessibility

The communication module supports English (`ltr`) and Arabic (`rtl`). Arabic
messages set `requires_native_speaker_review: True`. Both languages use the
same three fixed teach-back prompts. Native-speaker, accessibility, readability,
and community review are required before real use.

## Fairness and monitoring plan

The simulator reports segment metrics for language, literacy, and age band, and
the manifest includes segment delay/probability modifiers. These settings are
assumptions and may encode bias; they are not fairness evidence. A real pilot
should pre-specify minimum cell sizes, missingness checks, outcome parity
definitions, escalation burden, language quality review, and a stop rule for
harm or unexplained disparity.

transport-ledger adds distance, barrier, companion, payer, provider-change, and
stage-1-to-stage-11 leakage views. The leakage map demonstrates that the
system can measure and mitigate disparities; it is not a finding about any real
population. Queue comparisons must include workload and alert-fatigue burden,
not only closure metrics.

## Prohibited interpretation

Do not present a simulator probability as an individual risk score, infer a
diagnosis from a case stage, auto-send an unreviewed message, or use a
teach-back outcome as proof of clinical understanding. Do not introduce real
patient data into the demo without governance approval and a separate security
review.
