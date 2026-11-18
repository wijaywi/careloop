# AI use disclosure

## Scope and status

This disclosure describes the runtime behavior evidenced by the repository. It
is informational and does not make a legal, regulatory, clinical, or marketing
claim. Any regulatory or legal item is informational and **to be verified by
qualified counsel against official sources**.

**Official-source verification:** unavailable; no official-source verification
was performed.

## Runtime disclosure

**AI model use in the documented runtime: none.** The repository's responsible-
AI documentation states that the implementation is deterministic software and
does not invoke a generative or predictive AI model. The communication module
uses fixed English and Arabic strings and fixed teach-back prompts. No model
endpoint, model weights, model configuration, or external AI service is
documented.

| Capability | Observed implementation | Disclosure |
| --- | --- | --- |
| Message generation | Fixed templates in `api/communication.py` | Template rendering, not generative AI |
| Clinical decision | `clinical_decision_by_ai: False` and `requires_clinical_review: True` | No AI clinical decision is reported; human clinical review remains required |
| Teach-back | Reports `complete` or `needs_human_follow_up` from non-empty answers | Does not diagnose, triage, recommend treatment, or infer comprehension |
| Simulation | Seeded deterministic event queue and hash-based draws | Model outputs are simulated workflow outputs, not individual risk predictions or observed outcomes |
| Case closure | Typed closure code, mandatory evidence reference, and high-risk human authorization | Automation supports auditability and workflow state; it is not a substitute for clinical judgment |
| External data/model calls | Repository documents no external data connector and no model call | No external AI inference is documented |

## Language segment

The active/default language segment is **English (`ltr`)**. Arabic (`rtl`) and
other multilingual content is kept as structured communication data for
reviewed translation workflows. Arabic messages are explicitly marked for
native-speaker review. Language support does not imply that translation,
readability, accessibility, or clinical appropriateness has been validated for
real use.

## Data and human oversight

The default fixtures and simulator cohorts are synthetic. The repository does
not document a real-patient training, fine-tuning, or inference dataset. Case
actions, closure evidence, authorization, and communication review remain
bounded by code and human-review flags. These facts do not establish safety or
effectiveness outside the prototype environment.

## Boundary of this disclosure

This document covers application behavior visible in the repository. The
repository does not provide a complete record of how every artifact was
authored or of tools used outside the runtime. Future introduction of a model,
external AI service, automated clinical recommendation, or model-generated
patient communication would require a new disclosure and appropriate review.
