# Pilot plan

This is a proposed validation plan, not evidence that a pilot has occurred.
The current build remains synthetic-only and offline.

## Gate 0 — governance and readiness

Before real data or patient contact, obtain organizational ownership, privacy/
security review, clinical safety review, language/community review, accessibility
review, data-use approval, and an incident/stop policy. Define the accountable
clinical owner for every escalation and closure. Keep the demo environment
isolated from production records.

## Gate 1 — silent workflow validation

Use de-identified or synthetic replay data approved by the organization. Do
not send messages or change care. Compare case-stage timestamps and ownership
events with the source workflow. Check identity mapping, duplicate events,
missing fields, stage transitions, audit completeness, small-cell suppression,
and FHIR export semantics. Resolve discrepancies before human-facing use.

## Gate 2 — supervised staff usability

Start with a small, explicitly approved care-team group. Staff review every
message, escalation, handoff, teach-back outcome, and closure. Patients do not
receive automated clinical recommendations. Capture usability, time-to-action,
false or unnecessary escalations, missed stalls, handoff completeness, and
language review findings.

## Gate 3 — limited prospective feasibility

If Gate 2 is acceptable, pre-register a limited pathway and period, define
inclusion/exclusion criteria, and preserve a human-controlled comparison. Do
not power or describe this as an effectiveness trial until a statistician and
clinical owner approve the design. Monitor:

* notification-to-confirmation, confirmation-to-consult, and consult-to-
  treatment time;
* closure within the agreed operational window;
* loss-to-follow-up and no-show rates;
* owner coverage, handoff completion, teach-back follow-up, and escalation
  burden;
* outcomes by language, literacy support need, age band, pathway, and access
  context, subject to privacy thresholds;
* safety incidents, patient complaints, incorrect routing, and unreviewed
  communication.

## Stop rules

Pause the pilot for any unreviewed clinical message, incorrect patient/case
match, missed urgent follow-up attributable to the workflow, material privacy
incident, unexplained disparity, or sustained operational burden above the
pre-agreed limit. The exact thresholds are **ASSUMPTION / TO BE AGREED** and
must be set before a real pilot.

## Analysis and reporting

Report denominators, missingness, exclusions, pathway and segment definitions,
confidence-method choices, and all protocol deviations. Keep simulator outputs
separate from observed pilot outcomes. A successful pilot would support a
decision about a larger study; it would not alone establish clinical efficacy.
