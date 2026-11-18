# Evaluation report

## Evaluation question

Does the current repository reproduce its documented software behaviors
offline, deterministically, and with explicit provenance for simulated
parameters? This report evaluates the prototype mechanics. It does not claim
clinical effectiveness.

## Test-run evidence

Command run from the repository root:

```text
python -m unittest discover -s tests -p "test_*.py"
```

Observed result in this work session: **36 tests ran and passed** (`OK`). The
tests cover:

* explicit transitions, single ownership, immutable event payloads, SLA stall
  detection, deduplicated escalation, and evidence/human-decision closure;
* role-aware domain actions;
* deterministic paired simulation, output JSON/CSV writing, default controls,
  parameter schema provenance, zero-effect arm equality, pathway metrics,
  stress scenarios, sensitivity output, and intervals;
* English/Arabic review flags and non-clinical teach-back response behavior;
* API seed determinism, patient isolation, scripted closure and FHIR-like
  export, SQLite persistence after service reopen, and transport-ledger HTTP event
  routes;
* transport-ledger E1-E9 field restrictions, unknown gaps, daily absence reports,
  urgent/routine SLA loading, typed closure gates, positive handoffs,
  e-consults, passports, module ablations, stress scenarios, and registry
  completeness.

The test suite is offline and closes test-created SQLite resources.

## Reproduction commands

```text
make test
PYTHONPATH=. python -m careloop.simulator --cohort-size 1000 --runs 10 --seed 20261019 --json out/smoke.json --csv out/smoke.csv
PYTHONPATH=. python -B -m careloop.simulator scripts/reproduce.py --output out
PYTHONPATH=. python -m careloop.simulator --full --sensitivity --stress --json out/full.json --csv out/full.csv
```

The CLI writes `SimulationResult.to_dict()` to JSON and segment/paired rows to
CSV. The supplied default manifest is synthetic and assumption-only. Repeated
runs with the same config and parameters are expected to be byte-stable in
their structured values; this is directly asserted for representative runs by
the simulator tests.

## Generated-result evidence

The following outputs were generated with Windows Python
from the repository root:

```text
python scripts/reproduce.py --output out
python -B -m careloop.simulator --cohort-size 1000 --runs 10 --seed 20261019 --json out/simulate-fast.json --csv out/simulate-fast.csv
```

The bounded reproduction run is `out/reproduce.json`, with the flat table in
`out/reproduce.csv`, the generated SVG figure in `out/closure-rate.svg`, and a
Markdown table in `out/evaluation-table.md`. It used 24 cases × 2 paired
runs, seed `20261019`, and a 90-day virtual horizon. Its generated closure-rate
means were Arm A `0.5000` with interval `[0.2550, 0.7450]` and B-full `0.5834`
with interval `[0.5017, 0.6650]`. The paired closure-rate deltas were `0.0000`
and `0.1667`. These are model-conditional workflow outputs, not clinical
effectiveness evidence.

The bounded smoke run is `out/simulate-fast.json` / `out/simulate-fast.csv`.
It used 50 people × 2 runs, seed `20261019`, and 90 virtual days. The generated
Arm A closure rate was `0.5100`, B-full was `0.5800`, and B-full's core metric
was `0.4200`. These values are reported only to make the run reproducible; they
must not be generalized to a real population.

The full 10,000-person × 500-run result was removed as stale after the canonical-ledger migration and was not rerun. The `--full` command remains available, but no full-study result is claimed in this revision.

The primary scenario metadata is abnormal mammogram requiring diagnostic imaging or biopsy. Stage 9 is an operational assumption of 14 days urgent and 30 days routine; it is not a clinical guideline.

The regenerated compact output is `out/reproduce.json` / `out/reproduce.csv`. It used 24 synthetic cases × 2 replications with seed `20261019` and a 90-day virtual horizon. Arm A closure was `0.5000` with interval `[0.2550, 0.7450]`; B-full closure was `0.5834` with interval `[0.5017, 0.6650]`. The paired closure deltas were `0.0000` and `0.1667`.

The regenerated 200-case × 10-run bounded result is `out/stress-200x10.json` / `out/stress-200x10.csv`. Arm A closure was `0.4600` with interval `[0.4405, 0.4795]`; B-full was `0.5675` with interval `[0.5430, 0.5920]`. The core named-owner/documented-closure-within-SLA rate was `0.0580` for Arm A and `0.1455` for B-full. These results are conditional on synthetic assumptions and are not population evidence.

The same 200 × 10 run reported closure rates of `0.7095` without the closure gate, `0.5665` without the absence detector, `0.5055` without positive handoff, and `0.5675` without the multilingual passport. B-full unknown rate was `0.0535`; patient-pull rate was `0.0030`.

## Sensitivity and stress interpretation

The bounded ablation results are descriptive, not a ranking claim. Removing the closure gate increases closure because cases without evidence can be counted as closed; that is a gate/metric trade-off, not evidence that the gate is harmful. Removing the absence detector matched B-full within this run because its changed no-show/patient-pull path was rarely exercised. The multilingual passport had no difference under the English-only default segment. These components therefore have no demonstrated positive contribution under every current assumption. Priority queue results must likewise be read as workload trade-offs, not guaranteed improvement.

## Metrics implemented

The simulator computes stage completion means, unresolved counts at 30/60/90
days, closure rate, owner coverage, teach-back response, cross-provider, loss to
follow-up, no-show, unnecessary escalation, escalation count, backlog events,
maximum backlog, uncertainty hours, unknown visibility, typed closure and
evidence distributions, consults without referral, reroutes, patient pull,
stage 1-11 leakage by language/distance/age/payer, FIFO/priority workload,
ablation results, and the named-owner/documented-closure-within-SLA core
metric. These are workflow simulation metrics, not patient outcomes.

## Evaluation gaps

There is no external validation dataset, clinical chart review, prospective
pilot, calibrated risk model, translation validation, load test, security test,
FHIR conformance test, or cost-effectiveness study in this repository. These
are prerequisites for stronger claims.

## Ablation interpretation

The bounded ablations are descriptive model outputs, not a ranking claim. A component can show no contribution or a negative contribution under the current assumptions because it changes event timing, evidence gating, retry opportunities, or queue exposure. In particular, removing the closure gate can increase the reported closure metric by allowing cases without evidence to be counted as closed; that is a measurement/mechanism trade-off, not evidence that the gate is harmful. Removing the absence detector can match or exceed B-full in a small sample because the detector changes no-show and patient-pull paths. These components therefore have no demonstrated positive contribution under every current assumption.
