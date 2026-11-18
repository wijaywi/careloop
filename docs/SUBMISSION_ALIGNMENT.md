# Submission alignment notes

This document is for the human preparing a submission. It is not for judges,
is not a submission, and does not add evidence. Legal and regulatory wording is
informational and **to be verified by qualified counsel against official
sources**.

## Repository facts to keep synchronized

* **Solution stage:** Prototype only, provided the documented Python and web
  checks run in a clean environment. The current repository checks have run in
  this workspace; a fresh-environment rerun remains the human's release gate.
* **What has been built:** an offline, synthetic-only Python API and canonical
  E1-E9 ledger; SQLite projection; deterministic paired simulator with Arm A,
  B-full, ablations, stress and interval outputs; React/Vite client; audit,
  evidence, typed closure, handoff, SLA, absence, e-consult, passport, and
  small-cell-suppression workflow mechanics.
* **Primary scenario:** abnormal mammogram requiring diagnostic imaging or
  biopsy. Its timing values are assumptions, not clinical guidelines.
* **Language:** English is the active/default segment. Arabic content is
  structured review data and is flagged for native-speaker review; no
  native-speaker approval is claimed.
* **Teach-back:** the prototype records the patient's teach-back responses for
  staff review. It counts non-empty answers and does not assess understanding.
* **Closure:** the code requires a typed closure code and mandatory evidence
  reference; high-risk loops also require explicit human authorization. Do not
  say that every closure is human-authorized.
* **Not done:** no real data, pilot, clinical validation, security assessment,
  certified FHIR conformance, production identity, external AI/model call,
  native-speaker translation approval, or production integration.

## Replacement text for a 1,500-character solution-stage field

> CareLoop is an offline, synthetic-only prototype. It demonstrates a
> reproducible screening-to-care workflow: a canonical E1-E9 transport ledger,
> SQLite-backed case projection, typed evidence-gated closure, high-risk human
> authorization, positive handoffs, SLA/absence visibility, e-consult and
> patient-passport workflow objects, a deterministic paired simulator, and a
> React/Vite prototype. All data is synthetic and all simulator parameters are
> assumption-only. The prototype demonstrates workflow behaviour on synthetic
> data; it does not establish clinical effectiveness, safety, regulatory
> compliance, certified interoperability, or production readiness. English is
> the active/default language. Arabic content remains structured data requiring
> native-speaker review. Teach-back responses are recorded for staff review; no
> comprehension assessment is performed.

## Replacement text for a 1,500-character “what has been built” field

> The repository contains one canonical E1-E9 ledger/data model and one route
> set. The API runs locally with synthetic fixtures, role-convention checks,
> audit rows, evidence records, typed closure codes, mandatory evidence
> references, and explicit high-risk authorization. The simulator compares Arm
> A and B-full on the same seeded synthetic cohort and reports ablations,
> stress scenarios, uncertainty, visibility gaps, workload, and replication
> intervals. The web client is an offline-capable React/Vite demonstration.
> Generated results are model-conditional workflow outputs only.

## Replacement text for a 1,500-character limitations field

> CareLoop has no real patient data, pilot, clinical validation, prospective
> evaluation, production identity system, security assessment, encryption or
> tamper-proof audit design, retention policy, EHR/provider integration,
> certified FHIR implementation, native-speaker translation approval, or
> external AI/model call. The X-Actor-ID/query role convention is spoofable and
> must not be exposed to untrusted networks. Numeric parameters, segment
> modifiers, SLA values, and scenario weights are assumptions with no verified
> sources in the repository. Outputs must not be presented as clinical
> effectiveness, safety, equity, compliance, or ROI evidence.

## Pre-existing IP and AI-disclosure fields

* **Pre-existing IP:** the human must identify any code, diagrams, logo, text,
  templates, or other assets created before this repository and provide owner,
  license, permission, and attribution details. The repository cannot infer
  ownership. `THIRD_PARTY_NOTICES.md` records the inspected dependency metadata.
* **AI disclosure:** use the draft in `AI_USE_DISCLOSURE.md`. The human must
  fill its blanks with the factual scope, dates, and tools used for code,
  documentation, diagrams, and logo work. The runtime itself documents no
  generative or predictive AI model call.

## Regulatory and trademark caution

The product name **CareLoop has not been checked for trademark conflicts**.
Regulatory statements remain informational and require qualified-counsel
verification against official sources.
