# Demo script

This walkthrough uses only synthetic data and uses commands executed from the
repository root with its spaces in the path.

## 1. Establish the boundary

Say: “CareLoop is an offline prototype for coordination, not an AI
diagnostician. The fixtures and simulator are synthetic. Teach-back responses
are recorded for staff review; they are not an assessment of understanding.”

## 2. Run the tests

```text
python -B -m unittest discover -s tests -p "test_*.py"
```

Observed result: 52 tests ran and passed.

## 3. Start the API smoke check

```text
python -m api --host 127.0.0.1 --port 8000
```

The verification process queried `GET /health` and observed HTTP 200. The
default bind is loopback; the X-Actor-ID role convention is demo-only.

## 4. Generate the synthetic demo artifact

```text
python scripts/demo.py --output out/demo.json
```

Observed result: the synthetic stalled-case scenario reached evidence-gated
closure.

## 5. Run the compact reproduction

```text
python scripts/reproduce.py --output out
```

This writes `out/reproduce.json`, `out/reproduce.csv`,
`out/closure-rate.svg`, and `out/evaluation-table.md`. It uses 24 cases × 2
paired runs, seed `20261019`, and a 90-day virtual horizon.

## 6. Run the larger bounded investigation

```text
python -m careloop.simulator --bounded --cohort-size 200 --runs 10 --max-cohort-size 200 --max-runs 10 --json out/stress-200x10.json --csv out/stress-200x10.csv
```

The output is a conditional model result. It reports Arm A, B-full, and the
four explicit ablations; it is not clinical evidence.

## 7. Run the web checks

From PowerShell at the repository root:

```text
Set-Location web
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
```

The web client is an offline-capable prototype. English is the active patient
display; structured Arabic content remains review data.

## 8. Close with maturity

Say: “This demo shows a reproducible workflow slice and its guardrails. It does
not prove clinical effectiveness, safety, ROI, compliance, or production
readiness. A pilot would require governance, silent validation, supervised
staff use, security review, and predefined stop rules.”

The primary scenario is an abnormal mammogram requiring diagnostic imaging or
biopsy. Stage 9 timing is an assumption, not a clinical guideline.
