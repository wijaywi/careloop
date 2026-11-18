# Simulator parameters

The default manifest is `careloop/simulator/params/default.yml`. It is a
JSON-compatible YAML document parsed by `load_parameters`. The
registry is `careloop/simulator/params/registry.csv` and is generated from the
manifest by `scripts/generate_parameter_registry.py`. All current records are
`assumption` with source `not yet found / assumption`; no citation has been
invented. The complete list is in [ASSUMPTION_REGISTRY.md](ASSUMPTION_REGISTRY.md).

## Study controls

| Key | Default | Used by |
| --- | ---: | --- |
| `cohort_size` | 10,000 | Default full-run cohort per simulation run. |
| `runs` | 500 | Number of paired runs. |
| `virtual_days` | 90 | Maximum simulated horizon. |
| `seed` | 20261019 | Deterministic seed. |

The CLI's ordinary invocation overrides these to 1,000 people and 10 runs for
a quick smoke run; `--full` retains manifest values.

## Cohort composition

* `segment_weights.language`: English 0.65, Spanish 0.20, Mandarin 0.10,
  Other 0.05.
* `segment_weights.literacy`: high 0.55, limited 0.30, low 0.15.
* `segment_weights.age_band`: 18–44 0.40, 45–64 0.35, 65+ 0.25.
* `pathway_weights`: colorectal 0.34, mammogram 0.33, lab 0.33.
* `risk_probability_add`: 0.10 × the generated person risk value.

The generator samples each categorical field by weight and draws risk from a
uniform pseudo-random value. Segment labels are used to alter delays and some
probabilities; they are not validated clinical risk strata.

## Capacity and service time

`capacity.providers` defaults to intake 3, owner 4, specialist 2,
cross_provider 2, clinic 3, manager 1. `capacity.navigators` is 4.
Service-day durations are notification 0.15, confirmation 0.2, consult 1.0,
treatment 0.8, and escalation 0.3. The simulator reserves the earliest
provider slot and increments backlog counters when requested work waits.

## Arm A

Delays in days: notification 2.0, confirmation 2.0, consult 10.0, treatment
8.0. Success probabilities: confirmation 0.78, consult 0.82, treatment 0.78.
Teach-back response probability is 0.48 and owner coverage probability is 0.70.
Cross-provider probability is 0.25. Loss-to-follow-up, no-show, and unnecessary
escalation probabilities default to 0.0.

## B-full mechanism effects

Delay multipliers are notification 0.65, confirmation 0.70, consult 0.65, and
treatment 0.75. Probability additions are confirmation +0.10, consult +0.08,
treatment +0.08, teach-back response +0.20, and owner coverage +0.20. Escalation is
multiplied by 0.75. Cross-provider and loss-to-follow-up additions are 0.0;
no-show addition is 0.0; unnecessary escalation is 0.02.

These are mechanism settings for a paired model, not effect estimates. The
simulator clips stage probabilities to [0.05, 0.99] and rates to [0, 1] where
implemented.

## Segment and pathway modifiers

Non-English language multiplies delay by 1.25, limited literacy by 1.20, and
age 65+ by 1.15. Low literacy subtracts 0.08 from stage probability and 0.10
from teach-back probability. Pathway delay multipliers are colorectal 1.0,
mammogram 1.1, lab 0.85; probability additions are 0.0, −0.02, and +0.02.

## Stress and sensitivity configuration

Stress scenarios are `few_navigators` (capacity 1), `poor_contact_data`
(quality 0.55 plus loss settings), `cross_provider_dominant` (Arm A 0.8),
and `high_no_show` (Arm A 0.3). One-at-a-time bounds cover Arm A
confirmation probability [0.65, 0.90], consult probability [0.70, 0.95], loss
probability [0.0, 0.25], navigator capacity [1, 8], cross-provider probability
[0.1, 0.9], and no-show probability [0.0, 0.35]. The Latin-hypercube section
uses eight deterministic samples and analysis caps of 1,000 cohort members and
20 runs.

## SLA and transport-ledger mechanism parameters

The selected primary scenario is **abnormal mammogram requiring diagnostic
imaging or biopsy**. `careloop/simulator/params/sla_policy.json` contains urgent and routine
deadlines plus owner and escalation targets for notification,
acknowledgement/teach-back, confirmatory testing, e-consult, referral creation,
referral acceptance, appointment scheduling, attendance, treatment/surveillance,
and closure. For this prototype, Stage 9 is configured as an operational
assumption of 14 days urgent and 30 days routine for treatment/surveillance
start after the breast-pathway care decision. This is not a verified clinical
guideline value.

The transport-ledger mechanism inputs include language-concordant communication,
positive-handoff rejection reduction, escalation success probability, partner
event-reporting failure, patient-pull contact, referral rejection, closure
evidence availability, uncertainty hours, distance bands, barriers, companions,
payer type, provider changes, alert-fatigue threshold, and e-consult
availability. Each is varied or represented in the sensitivity and
stress output where applicable.

Duration inputs are paired across arms and receive a deterministic spread using
`duration_variability_cv` with a lognormal-like bounded factor. This keeps the
same synthetic person and seed comparable while avoiding a claim that a single
mean duration is a measured operational distribution.

## Parameter change protocol

To use observed or literature-derived values, replace the manifest record with
a verified source and update the evaluation report. Do not relabel a value
`OBSERVED` merely because it looks plausible; the current validator is designed
to prevent that.
