# CareLoop documentation

CareLoop is an offline, synthetic-only prototype. It demonstrates workflow
behaviour on synthetic data, not clinical effectiveness, safety, compliance, or
production readiness. The repository has one canonical ledger/data model and
one route set.

## Reproduce from the repository root

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.lock
python -B -m unittest discover -s tests -p "test_*.py"
python scripts/reproduce.py --output out
cd web
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
```

## Document map

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Single ledger, projections, routes, and boundaries. |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Synthetic-only data and future onboarding gate. |
| [PARAMETERS.md](PARAMETERS.md) | Assumption-only simulator parameters. |
| [ASSUMPTIONS_AND_LIMITATIONS.md](ASSUMPTIONS_AND_LIMITATIONS.md) | Explicit evidence and scope limits. |
| [RESPONSIBLE_AI.md](RESPONSIBLE_AI.md) | Human review and automation boundaries. |
| [EVALUATION_REPORT.md](EVALUATION_REPORT.md) | Actual test and output evidence. |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Offline demo commands and wording. |
| [DECISIONS.md](DECISIONS.md) | Recorded implementation decisions. |
| [FINAL_REPORT.md](FINAL_REPORT.md) | Consolidated maturity and result summary. |
| [CHANGELOG.md](CHANGELOG.md) | Dated history. |
| [ASSUMPTION_REGISTRY.md](ASSUMPTION_REGISTRY.md) | Generated registry from `registry.csv`. |
| [REGULATORY_READINESS.md](REGULATORY_READINESS.md) | Informational counsel-verification checklist. |
| [SUBMISSION_ALIGNMENT.md](SUBMISSION_ALIGNMENT.md) | Human alignment notes for external materials. |
| [AI_USE_DISCLOSURE.md](AI_USE_DISCLOSURE.md) | Draft disclosure for human review. |

The root also contains [SECURITY_NOTES.md](../SECURITY_NOTES.md),
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), and
[LICENSE_DECISION.md](LICENSE_DECISION.md).
