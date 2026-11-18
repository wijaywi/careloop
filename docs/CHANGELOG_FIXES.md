# Consolidation and fixes map

This map records the requested items, the principal files changed, and the
verification status. The project remains an offline synthetic prototype.

| Item | Files/functions changed | Status |
|---|---|---|
| 0.1–0.2 | Archive manifest outside the project; root inventory; `docs/README.md` | Differing parent materials archived; no outside project modified. |
| 0.3 | `careloop/loop_engine/ledger.py`, `api/service.py`, `api/app.py`, simulator imports, tests | One canonical ledger/projection; old engine files and route adapter removed. |
| 0.4 | `out/`, `scripts/reproduce.py`, simulator CLI | Stale output contents removed after hash manifest; outputs regenerated. Full study not rerun after engine migration. |
| 0.5 | README, Dockerfile, API smoke commands, hygiene search | Loopback default verified; path search and runnable checks performed. |
| 0.6 | Final tree and reports | Final verification remains at the end of this pass. |
| A1 | `api/communication.py`, web patient copy, responsible-AI/docs | Teach-back is response recording for staff review; no comprehension claim. |
| A2 | `ledger.py`, `api/service.py`, closure tests | Typed code + evidence required; high-risk authorization required. |
| A3 | Architecture, limitations, API projection | Single ledger/data model stated. |
| A4 | `default.yml`, registry, parameter docs/tests | English is the active/default language segment. |
| A5 | Parameter notes and simulator comments | Segment modifiers marked hand-authored assumptions that may encode bias. |
| B1 | `scripts/reproduce.py`, generated output, evaluation docs | Reproduction config is read from generated JSON; canonical compact run is 24 × 2. |
| B2 | `docs/ARCHITECTURE.md` | Count and layer description corrected. |
| B3 | `docs/DECISIONS.md`, evaluation/final docs | Decision numbering and repository-root wording corrected; full-study status remains open after migration. |
| B4 | registry generator, `registry.csv`, parameter tests | Seed range is `0..2147483647`; default validation added. |
| B5 | `docs/README.md` | Video script removed from document map. |
| B6 | registry/report generators | Registry regenerated: 72 total, 0 sourced. |
| C1 | simulator ledger adapter and stress test | Stress override regression covered; 200 × 10 attempt exceeded the 120-second bounded command window and is not claimed complete. |
| C2 | `docs/EVALUATION_REPORT.md` | Ablation interpretation added; negative/null mechanisms are not hidden. |
| C3 | reproduction/evaluation docs | Intervals and sample-size caveats retained; tiny samples are described as bounded outputs. |
| D1–D5 | `THIRD_PARTY_NOTICES.md`, license note, AI disclosure, docs | No shipped path or other-project reference intended; CareLoop trademark remains unchecked. |
| E1–E3 | `api/app.py`, Dockerfile, `SECURITY_NOTES.md`, tests | Loopback default, warning, demo identity limitation, suppression, and security gaps documented. |
| F | `docs/REGULATORY_READINESS.md`, `DATA_SOURCES.md`, README map | Informational checklist with counsel-verification wording. |
| G | `docs/SUBMISSION_ALIGNMENT.md` | Human-facing alignment document created; form-specific final confirmation remains open. |

## Not done / not claimed

* The full 10,000 × 500 study was not rerun after the canonical-ledger code
  migration; previous outputs were removed as stale.
* The 200 × 10 stress/ablation investigation exceeded the bounded command
  window and has no claimed result in this revision.
* No real data, pilot, clinical validation, security assessment, production
  identity, certified FHIR implementation, or native-speaker translation
  approval was added.
* No project license was selected; see `docs/LICENSE_DECISION.md`.
