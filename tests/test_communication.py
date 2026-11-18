"""Focused communication and teach-back behavior tests."""

import unittest

from api.communication import evaluate_teach_back, render_template, teach_back_questions


class CommunicationTests(unittest.TestCase):
    def test_english_is_ltr_and_has_human_review_flags(self):
        message = render_template("follow_up", language="en", context={"patient_name": "Synthetic Patient"})
        self.assertEqual(message["direction"], "ltr")
        self.assertFalse(message["requires_native_speaker_review"])
        self.assertTrue(message["requires_clinical_review"])
        self.assertFalse(message["clinical_decision_by_ai"])

    def test_arabic_is_rtl_and_marked_for_native_review(self):
        message = render_template("appointment_reminder", language="ar", context={"patient_name": "مريض", "appointment_date": "2026-01-02"})
        self.assertEqual(message["direction"], "rtl")
        self.assertTrue(message["requires_native_speaker_review"])
        self.assertIn("موعد", message["subject"])

    def test_teach_back_reports_follow_up_without_clinical_decision(self):
        questions = teach_back_questions(language="en")
        self.assertEqual(len(questions), 3)
        incomplete = evaluate_teach_back(["next step"], language="en")
        complete = evaluate_teach_back(["next step", "tomorrow", "no questions"], language="en")
        self.assertEqual(incomplete["outcome"], "needs_human_follow_up")
        self.assertEqual(complete["outcome"], "complete")
        self.assertFalse(complete["clinical_decision_by_ai"])
        self.assertTrue(complete["requires_clinical_review"])


if __name__ == "__main__":
    unittest.main()
