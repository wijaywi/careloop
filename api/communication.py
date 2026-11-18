"""Deterministic patient communications; no clinical decisions are automated.

``render_template`` only formats approved, human-authored language.  Arabic
messages are marked for native-speaker review and every message is marked for
clinical review before sending.  Teach-back evaluation reports communication
follow-up needs; it never diagnoses, triages, or recommends treatment.
"""

from __future__ import annotations

from typing import Any, Mapping

TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "screening_result": {
        "en": {
            "subject": "Your screening follow-up",
            "body": "Hello {patient_name}, your screening follow-up is ready. A member of your care team will contact you about the next step. Please ask questions if anything is unclear.",
        },
        "ar": {
            "subject": "متابعة فحصك",
            "body": "مرحباً {patient_name}، أصبحت متابعة الفحص جاهزة. سيتواصل معك أحد أفراد فريق الرعاية بشأن الخطوة التالية. يرجى طرح الأسئلة إذا كان أي شيء غير واضح.",
        },
    },
    "appointment_reminder": {
        "en": {
            "subject": "Appointment reminder",
            "body": "Hello {patient_name}, this is a reminder about your appointment on {appointment_date}. Contact your care team if you need help.",
        },
        "ar": {
            "subject": "تذكير بالموعد",
            "body": "مرحباً {patient_name}، هذا تذكير بموعدك في {appointment_date}. تواصل مع فريق الرعاية إذا احتجت إلى مساعدة.",
        },
    },
    "follow_up": {
        "en": {
            "subject": "Care team follow-up",
            "body": "Hello {patient_name}, your care team is following up with you. Please tell us what you think the next step is and what questions you have.",
        },
        "ar": {
            "subject": "متابعة فريق الرعاية",
            "body": "مرحباً {patient_name}، يتابع فريق الرعاية معك. يرجى إخبارنا بما فهمته عن الخطوة التالية وما هي أسئلتك.",
        },
    },
}

TEACH_BACK: dict[str, tuple[str, ...]] = {
    "en": (
        "What do you think the next step is?",
        "When do you expect the next step to happen?",
        "What questions or support do you need from your care team?",
    ),
    "ar": (
        "ما هي الخطوة التالية التي فهمتها؟",
        "متى تتوقع أن تحدث الخطوة التالية؟",
        "ما الأسئلة أو الدعم الذي تحتاجه من فريق الرعاية؟",
    ),
}


def _language(language: str) -> str:
    normalized = (language or "en").lower().replace("_", "-").split("-")[0]
    if normalized not in TEMPLATES["screening_result"]:
        raise ValueError("language must be 'en' or 'ar'")
    return normalized


def render_template(template: str, *, language: str = "en", context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Render one deterministic template with review metadata."""

    lang = _language(language)
    if template not in TEMPLATES:
        raise ValueError(f"unknown communication template: {template}")
    values = dict(context or {})
    source = TEMPLATES[template][lang]
    try:
        subject = source["subject"].format(**values)
        body = source["body"].format(**values)
    except KeyError as exc:
        raise ValueError(f"missing template context: {exc.args[0]}") from exc
    return {
        "template": template,
        "language": lang,
        "direction": "rtl" if lang == "ar" else "ltr",
        "subject": subject,
        "body": body,
        "requires_native_speaker_review": lang == "ar",
        "requires_clinical_review": True,
        "clinical_decision_by_ai": False,
        "teach_back_questions": list(TEACH_BACK[lang]),
    }


def teach_back_questions(*, language: str = "en") -> list[str]:
    """Return fixed questions that record responses for staff review."""

    return list(TEACH_BACK[_language(language)])


def evaluate_teach_back(answers: Mapping[str, Any] | list[Any], *, language: str = "en") -> dict[str, Any]:
    """Record whether a patient answered each question.

    The result records the patient's teach-back responses for staff review. It
    does not assess understanding, make a clinical decision, or replace review.
    """

    lang = _language(language)
    values = list(answers.values()) if isinstance(answers, Mapping) else list(answers)
    answered = sum(bool(str(value).strip()) for value in values)
    complete = len(values) >= len(TEACH_BACK[lang]) and answered >= len(TEACH_BACK[lang])
    return {
        "outcome": "complete" if complete else "needs_human_follow_up",
        "answered": answered,
        "question_count": len(TEACH_BACK[lang]),
        "requires_clinical_review": True,
        "clinical_decision_by_ai": False,
    }


# Friendly aliases for adapters and clients.
render_communication = render_template
