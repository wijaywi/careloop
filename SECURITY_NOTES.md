# CareLoop security notes

## Status and scope

These notes are informational documentation of the repository as inspected.
They are not a security certification, deployment approval, privacy notice, or
legal advice. All regulatory and legal items in this document are informational
and **to be verified by qualified counsel against official sources**.

**Official-source verification:** unavailable; no official-source verification
was performed for this document.

CareLoop is described by the repository as an offline, synthetic-only prototype
and hackathon demonstration. It is not described as a clinically validated or
production-ready product. The default API data and simulator cohorts are
synthetic. The repository does not include an external data connector.

## Security-relevant implementation inventory

| Area | Repository evidence | Observed boundary |
| --- | --- | --- |
| Runtime | Python 3.11.9; the Python lock file is intentionally empty | Core API, simulator, and tests use the Python standard library; optional web tooling is separate |
| Persistence | Local SQLite selected by `CARELOOP_DB` | Local runtime state; no hosted database, backup, or retention service is supplied |
| API roles | `navigator`, `clinician`, `program_manager`, and `patient` | Service-level role checks are present; the `X-Actor-ID` header is not documented as production authentication |
| Audit | Mutations append actor, action, payload, and timestamp rows | Auditability is implemented locally; operational log protection and retention are not supplied |
| Privacy-oriented controls | Patient self-case restriction; aggregate suppression below 10 | Prototype controls only; no deployment-scale privacy assessment is supplied |
| Event transport | transport-ledger uses pseudonymous loop IDs and a transport-only E1-E9 schema | Partner event fields exclude clinical content; partner identity and transport security are not supplied |
| Communications | Fixed English and Arabic templates; messages require clinical review | The active/default language segment is English (`ltr`); Arabic is structured translation data needing review |
| AI boundary | Communication helpers report `clinical_decision_by_ai: False` and `requires_clinical_review: True` | No generative or predictive model invocation is documented |

## Controls present in code and documentation

* The default fixtures are synthetic, and the simulator is deterministic.
* Patients can access only their own case and cannot close, transition,
  escalate, or view aggregate analytics or the audit log.
* Care-team mutations append audit records.
* Analytics suppress groups with fewer than 10 cases.
* transport-ledger partner events carry progress fields rather than clinical content.
* Case closure requires a typed closure code and case-scoped evidence;
  high-risk closure additionally requires explicit human authorization.
* Positive handoff keeps the sender as owner until acceptance; rejection needs
  a reason and an alternative destination.
* Fixed messages and teach-back results are marked for clinical review.

These controls are implementation facts, not evidence of security effectiveness
in a production environment.

## Known gaps and deployment risks

The repository identifies or shows the following gaps:

* no production identity provider, session management, or demonstrated
  authentication protocol;
* no TLS/transport-security configuration, network policy, secret management,
  key management, or service-to-service trust model;
* local SQLite permissions, encryption at rest, backup, restore, deletion, and
  retention controls are not supplied;
* the SQLite DDL enables foreign keys but does not declare foreign-key
  constraints;
* no production monitoring, alerting, incident-response process, recovery
  objectives, vulnerability-management process, or dependency scanning is
  supplied;
* no production integration with an EHR, messaging, appointment, claims, or
  laboratory system is supplied; and
* no real-patient-data approval, data-processing agreement, or deployment-scale
  authorization evidence is present.

The `X-Actor-ID` mechanism and seeded demo identities must not be treated as a
production identity boundary without an explicit security review.

## Pre-deployment verification record

Before any real data or external integration is considered, an owner should
record decisions and evidence for identity and access management, threat
modeling, secure configuration, transport and storage protection, logging and
retention, backup and recovery, incident response, dependency and build
provenance, privacy review, clinical governance, language/accessibility review,
and independent security testing. This list is a planning aid, not a claim that
the controls are complete.

Regulatory, privacy, and security requirements depend on the deployment,
jurisdiction, data, and role of the operator. They are informational here and
**to be verified by qualified counsel against official sources**.
