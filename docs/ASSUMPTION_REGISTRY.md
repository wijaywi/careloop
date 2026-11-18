# CareLoop simulator assumption registry

This file is generated from `careloop/simulator/params/registry.csv`.
Every row is currently marked `assumption` because no parameter source
was verified for this revision. These values are not clinical evidence.

Total records: **72**; assumption records: **72**; sourced records: **0**.

| Parameter | Range | Distribution | Source | Status | Notes |
|---|---|---|---|---|---|
| cohort_size | 1..10000 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| runs | 1..10000 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| virtual_days | 0..720 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| seed | 0..2147483647 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| segment_weights.language | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | English is the active/default language segment; non-English modifiers remain hand-authored assumptions. |
| segment_weights.literacy | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: limited-literacy segment modifier. |
| segment_weights.age_band | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: age 65+ segment modifier. |
| capacity.providers | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| capacity.navigators | 1..10000 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| capacity.service_days | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.notification_delay | 0..720 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.confirmation_delay | 0..720 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.consult_delay | 0..720 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.treatment_delay | 0..720 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.confirmation_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.consult_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.treatment_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.teach_back_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.owner_coverage_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.notification_delay_multiplier | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.confirmation_delay_multiplier | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.consult_delay_multiplier | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.treatment_delay_multiplier | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.confirmation_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.consult_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.treatment_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.teach_back_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.owner_coverage_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.escalation_multiplier | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.cross_provider_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.cross_provider_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.loss_to_follow_up_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.loss_to_follow_up_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.no_show_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.no_show_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| arm_a.unnecessary_escalation_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| b_full.unnecessary_escalation_probability | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| contact_data_quality | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| pathways | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| pathway_weights | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| stress_scenarios | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| sensitivity_parameters | categorical map; each probability 0..1 | categorical | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| segment_delay_multiplier.language_non_english | [0, 2] | configured | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION; retained as an optional non-English mechanism while English is active/default. |
| segment_delay_multiplier.literacy_limited | [0, 2] | configured | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: limited-literacy segment modifier. |
| segment_delay_multiplier.age_65_plus | [0, 2] | configured | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: age 65+ segment modifier. |
| risk_probability_add | 0..1 | configured | not yet found / assumption | assumption | Current model input; range is an assumption until a source is verified. |
| distance_weights | [0, 1] | categorical | not yet found / assumption | assumption | synthetic travel-distance bands |
| distance_km | [0, 200] | categorical | not yet found / assumption | assumption | synthetic distance representatives |
| barrier_weights | [0, 1] | categorical | not yet found / assumption | assumption | synthetic barrier mix |
| companion_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | synthetic support-person availability |
| payer_weights | [0, 1] | categorical | not yet found / assumption | assumption | synthetic payer mix |
| provider_change_distribution | [0, 2] | categorical | not yet found / assumption | assumption | synthetic provider-change count |
| alert_fatigue_threshold | [1, 20] | fixed | not yet found / assumption | assumption | alerts per case before fatigue is counted |
| absence_detector_no_show_multiplier | [0, 1] | fixed | not yet found / assumption | assumption | mechanistic reminder effect |
| patient_pull_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | patient-initiated recontact probability |
| referral_rejection_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | synthetic referral acceptance failure |
| unknown_partner_report_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | synthetic external-report identity uncertainty |
| closure_evidence_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | typed evidence availability |
| base_uncertainty_hours | [0, 720] | fixed | not yet found / assumption | assumption | uncertainty measure when closure evidence is missing |
| closure_sla_days | [1, 365] | fixed | not yet found / assumption | assumption | core documented-closure SLA |
| econsult_unavailable_rate | [0, 1] | bernoulli | not yet found / assumption | assumption | availability stress input |
| stress_scenarios_v2 | categorical map; each probability 0..1 | scenario | not yet found / assumption | assumption | bounded stress scenarios |
| b_full.multilingual_delay_multiplier | [0, 1] | bounded_multiplier | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: language-concordant communication mechanism; English is active/default. |
| b_full.multilingual_understanding_probability_add | [0, 1] | bounded_probability | not yet found / assumption | assumption | HAND-AUTHORED ASSUMPTION: language-concordant understanding mechanism; English is active/default. |
| b_full.positive_handoff_rejection_multiplier | [0, 1] | bounded_multiplier | not yet found / assumption | assumption | positive-handoff rejection mechanism |
| escalation_success_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | escalation mechanism; varied in sensitivity analysis |
| partner_event_reporting_failure_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | partner reporting failure creates UNKNOWN visibility |
| primary_screening_type | configured category | categorical | not yet found / assumption | assumption | Selected primary scenario: abnormal mammogram requiring diagnostic imaging or biopsy; Stage 9 timing remains an operational assumption |
| arm_a.result_flag_probability | [0, 1] | bernoulli | not yet found / assumption | assumption | probability an actionable result is correctly flagged at source |
| b_full.result_flag_probability_add | [0, 1] | bounded_probability | not yet found / assumption | assumption | source-flag visibility mechanism scenario input |
| duration_variability_cv | [0, 1] | lognormal_like | not yet found / assumption | assumption | paired deterministic spread around duration inputs |
| sla_table_v2 | each duration is an ASSUMPTION | fixed_configurable | not yet found / assumption | assumption | Selected primary scenario: abnormal mammogram requiring diagnostic imaging or biopsy. Stage 9 operational target is urgent 14 days and routine 30 days; no guideline source was verified. |
