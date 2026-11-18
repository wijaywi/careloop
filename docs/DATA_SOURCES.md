# Data sources and provenance

## Declaration

CareLoop is **synthetic-only**. No real patient records, claims, screening
registry, laboratory feed, appointment system, public-health dataset, or
external clinical evidence source is bundled or required. The current API
startup fixture creates synthetic names such as `Synthetic Patient 01` and
synthetic case titles. The simulator generates synthetic cohorts in memory.

## Inventory

| Source | Location | Contents | Provenance |
| --- | --- | --- | --- |
| Demo users/cases | `api/service.py::load_demo_data` | Deterministic users, 12 default cases, case stages, and a scripted stalled case | **CODE**; generated from a local seed, not observed data |
| Simulator manifest | `careloop/simulator/params/default.yml` | Cohort size, weights, capacities, delays, probabilities, pathways, SLA table, ablations, stress scenarios, and sensitivity bounds | **ASSUMPTION**; every record is listed in `params/registry.csv` with source `not yet found / assumption` |
| Simulated people | `careloop/simulator/engine.py::_cohort` | Language, literacy, age band, risk, distance, barrier, companion, payer, provider changes, and pathway labels | **CODE + ASSUMPTION**; values are sampled from the manifest |
| E1-E9 event ledger | `careloop/loop_engine/ledger.py` and simulator transport adapter | Pseudonymous loop IDs, E1-E9 progress events, deadlines, owners, evidence references, and UNKNOWN gaps | **CODE**; no clinical content is carried in the partner event schema |
| API database | SQLite selected by `CARELOOP_DB` | Runtime cases, users, artifacts, and audit rows | Local synthetic runtime state; not a source dataset |
| Test fixtures | `tests/` | Small deterministic entities and expected behaviors | **CODE/TEST**; fixtures are not clinical observations |

The manifest is JSON-compatible YAML and is loaded without PyYAML. A regular
YAML file requires the optional PyYAML import; the supplied default does not.

## What the pathways mean

The default pathway labels are colorectal / FIT to colonoscopy, abnormal
mammogram to diagnostic imaging/biopsy, and markedly abnormal lab to
primary-care follow-up. They are labels for simulated workflow branches, not
clinical protocols, diagnostic definitions, or prevalence estimates. Their
weights and modifiers are **ASSUMPTION**.

## Data handling in the prototype

* API persistence is local SQLite; there is no network connector.
* FHIR output is a local R4-like representation assembled by
  `CareLoopService.fhir_export`; it is not a certified FHIR implementation.
* The communication module contains fixed English and Arabic strings. Arabic
  is structured translation data and explicitly marked for native-speaker and
  clinical review; active application copy is English.
* Audit entries record mutation actor, action, payload, and timestamp.
* Aggregate analytics return `count: null` and `suppressed: true` when a group
  count is below the code constant `SMALL_CELL_THRESHOLD = 10`.

## Future data onboarding gate

Before any real data is introduced, the project needs an approved data
contract, lawful-use/privacy review, de-identification or minimum-necessary
policy, access controls, retention/deletion rules, data quality checks, and a
separate evaluation plan. The named regulatory topics and counsel-verification
checklist are in [REGULATORY_READINESS.md](REGULATORY_READINESS.md). None of
those approvals is implied by this demo.
