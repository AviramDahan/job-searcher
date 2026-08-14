from __future__ import annotations

import unittest

from src.public_text import public_hebrew_text


def broken_utf8_as_latin1(value: str) -> str:
    return value.encode("utf-8").decode("latin-1")


class PublicTextTests(unittest.TestCase):
    def test_repairs_historical_mojibake(self) -> None:
        text = public_hebrew_text(broken_utf8_as_latin1("קורן דהן - קניינית רכש בדרום"))

        self.assertEqual(text, "קורן דהן - קניינית רכש בדרום")

    def test_repairs_mixed_mojibake_and_utf8_punctuation(self) -> None:
        text = public_hebrew_text(broken_utf8_as_latin1("קניינית רכש – באר שבע"))

        self.assertEqual(text, "קניינית רכש – באר שבע")

    def test_translates_submission_engine_reason(self) -> None:
        text = public_hebrew_text(
            "Approval required by submission engine: MS Project appears to be a required skill, "
            "but it is not verified in the candidate profile. Next: Ask the operator for approval "
            "or the missing policy-sensitive answer before attempting submission."
        )

        self.assertIn("נדרש אישור לפני הגשה", text)
        self.assertIn("נדרש ניסיון ב-MS Project כחובה", text)
        self.assertIn("השלב הבא", text)
        self.assertNotIn("Approval required", text)
        self.assertNotIn("candidate profile", text)

    def test_translates_manual_fallback_reason(self) -> None:
        text = public_hebrew_text(
            "Manual submission required: Official fallback checked at https://jobs.rami-levy.co.il/; "
            "no direct posting/form for procurement clerk at Timorim was found, "
            "only WhatsApp/phone/recruiting email contact. Recommendation: apply manually via Drushim "
            "or contact Rami Levy recruiting with the approved CV."
        )

        self.assertIn("נדרשת הגשה ידנית", text)
        self.assertIn("https://jobs.rami-levy.co.il/", text)
        self.assertIn("לא נמצאה משרה ישירה", text)
        self.assertNotIn("Manual submission required", text)

    def test_translates_retry_and_site_adapter_text(self) -> None:
        text = public_hebrew_text(
            "SuccessFactors requires account creation. "
            "Search for the same role on the official company career page; if no direct form exists, send manual handoff. "
            "The form is protected by reCAPTCHA."
        )

        self.assertIn("SuccessFactors דורש יצירת חשבון", text)
        self.assertIn("אתר הקריירה הרשמי", text)
        self.assertIn("הטופס מוגן באמצעות reCAPTCHA", text)
        self.assertNotIn("requires account creation", text)
        self.assertNotIn("manual handoff", text)

    def test_translates_candidate_profile_fact_text(self) -> None:
        text = public_hebrew_text(
            "Driving license, car, and independent arrival are verified in the candidate profile. "
            "Use the verified candidate profile answer. "
            "The official form asks whether the candidate previously applied, and this answer is not verified in the candidate profile."
        )

        self.assertIn("רישיון נהיגה", text)
        self.assertIn("בתשובה המאומתת מפרופיל המועמדת", text)
        self.assertIn("הגישה מועמדות בעבר", text)
        self.assertNotIn("candidate profile", text)


if __name__ == "__main__":
    unittest.main()
