# Regulatory readiness

## Important status statement

This is an informational repository assessment. It is not a regulatory
classification, compliance opinion, certification, or submission. All
regulatory and legal items below are informational and **to be verified by
qualified counsel against official sources**.

**Official-source verification:** unavailable; no official-source verification
was performed. The repository does not state a target jurisdiction, regulator,
intended commercial deployment, or submission pathway.

## Product facts relevant to readiness

The repository describes CareLoop as an offline, synthetic-only prototype and
hackathon demonstration. It contains a local SQLite API, a deterministic domain
loop engine, a paired simulator, fixed communication and teach-back helpers,
and a React/Vite web prototype. It states that the implementation is not
clinically validated, has no production integration, carries no claim of
clinical effectiveness, and uses no real patient data or external clinical
evidence package.

The active/default language segment is English (`ltr`). Arabic and other
multilingual content is retained as structured communication data for reviewed
translation workflows; Arabic messages are marked for native-speaker review.

## Readiness matrix

## Named topics for counsel verification

Each item in this section is **unverified by the repository author** and is
**to be verified by qualified counsel against official sources**. No official
source was read for this revision; the statements below are scoping prompts,
not legal conclusions.

### UAE federal health-information topics

* Verify UAE Federal Law No. 2 of 2019 on the Use of Information and
  Communications Technology (ICT) in Health Fields, including any general
  restriction on storing, processing, generating, or transferring health data
  outside the UAE unless authorized.
* Verify the implementing regulations and their scope, definitions,
  exceptions, approvals, and operational requirements.
* Verify Ministerial Resolution No. 51/2021 and any permitted exceptions,
  approval route, and conditions relevant to a pilot.

### Abu Dhabi Department of Health topics

* Verify the requirements for DoH-licensed entities, including the applicable
  health-information and cyber-security standard.
* Verify restrictions on sharing even de-identified health data with third
  parties without DoH authorization.
* Verify cloud-provider, hosting, cross-border transfer, and data-residency
  expectations for the proposed pilot architecture.

### Pilot consequences to resolve

Before any onboarding or external hosting, counsel and the accountable
organization must resolve hosting location; cloud and AI-service location;
data-sharing agreements with licensed partners; consent model; retention and
deletion; access control; incident management; breach notification; and the
boundary between synthetic demonstration data and any future health data.

### Open software-classification question

Obtain a jurisdiction-specific assessment of whether escalation/closure-
management software could be treated as medical software or clinical decision
support in the pilot jurisdiction. The repository makes no classification.

| Topic | Repository evidence | Readiness interpretation |
| --- | --- | --- |
| Intended use and claims | README and existing reports limit the project to workflow mechanics and simulation | A final intended-use statement, user population, claims boundary, and labeling package are not supplied |
| Clinical safety and effectiveness | Deterministic simulator, tests, assumptions, and limitations are documented | Simulation outputs are not clinical evidence; prospective validation, risk controls, and clinical governance are not supplied |
| Software lifecycle | Python modules, API, web client, tests, Make targets, and a lock file exist | A controlled lifecycle, release records, traceability, change control, and production verification package are not supplied |
| Risk management | Responsible-AI and limitations documents identify human-review and data-boundary risks | A formal hazard analysis, risk acceptability record, mitigations, and residual-risk review are not supplied |
| Privacy and security | Synthetic-only fixtures, role checks, audit rows, small-cell suppression, and explicit gaps are documented | A deployment privacy/security assessment, identity system, retention policy, incident plan, and security test evidence are not supplied |
| Interoperability | Local FHIR R4-like export and E1-E9 transport-only events are implemented | The repository explicitly says the FHIR output is not certified; conformance, partner contracts, and production integration evidence are not supplied |
| Human factors and accessibility | English/Arabic templates, teach-back prompts, and review flags are present | Usability validation, accessibility conformance evidence, native-speaker review, and community review are not supplied |
| Data and provenance | DATA_SOURCES.md identifies synthetic fixtures, assumptions, code, and tests | No real-world evidence package, data-use approval, or external clinical dataset is bundled |
| AI/automation transparency | Communication code reports no AI clinical decision and requires clinical review | No model card, model validation, or AI risk package is relevant to the documented runtime; any future model use would need a new review |
| Distribution and third parties | `web/package.json` and `web/package-lock.json` are present; notices are recorded separately | Project license selection and distribution-time notice review remain open; see `THIRD_PARTY_NOTICES.md` and `LICENSE_DECISION.md` |

## Potentially relevant review areas

Depending on a future intended use and jurisdiction, qualified reviewers may
need to assess medical-device or clinical-software rules, health-information
privacy and security rules, research or quality-improvement requirements,
accessibility and language obligations, interoperability requirements, records
retention, cybersecurity expectations, advertising/marketing claims, and
third-party software licensing. Mentioning these areas is not a determination
that any particular rule applies.

## Submission package gaps

No submission-ready package is present. A future package would need a defined
intended use and claims boundary; jurisdiction and classification rationale;
requirements-to-test traceability; software architecture and lifecycle records;
risk management; cybersecurity and privacy evidence; clinical or operational
validation; usability and accessibility evidence; data and translation
provenance; release configuration; complaint, incident, and post-deployment
monitoring plans; and a complete third-party notice and license review.

These are informational planning items only and are **to be verified by
qualified counsel against official sources**.
