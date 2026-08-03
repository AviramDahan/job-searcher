from __future__ import annotations

import unittest

from src.action_insights import build_insights, categories_for_row
from src.job_records import COMPANY, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REJECTED, SCORE, STATUS, STOP_REASON, TITLE


class ActionInsightsTests(unittest.TestCase):
    def test_manual_captcha_row_becomes_top_manual_action(self) -> None:
        rows = [
            {
                COMPANY: "IAI",
                TITLE: "קניין/ית רכש",
                LOCATION: "אשדוד",
                LINK: "https://jobs.example.test/1",
                SCORE: "96",
                STATUS: MANUAL_REQUIRED,
                STOP_REASON: "Manual gate: official form requires CAPTCHA/reCAPTCHA.",
            }
        ]

        insights = build_insights(rows)

        self.assertEqual(insights["snapshot"]["manual_required"], 1)
        self.assertEqual(insights["blocker_counts"][0]["category"], "security_gate")
        self.assertIn("ידניות", insights["next_actions"][0]["title"])
        self.assertEqual(insights["next_actions"][0]["jobs"][0]["company"], "IAI")

    def test_pending_location_and_experience_generate_separate_actions(self) -> None:
        rows = [
            {
                COMPANY: "Renuar",
                TITLE: "רפרנט/ית ייבוא",
                LOCATION: "ראשון לציון",
                LINK: "https://jobs.example.test/2",
                SCORE: "100",
                STATUS: PENDING,
                STOP_REASON: "נדרש אישור לפני הגשה: מיקום באזור משני מחוץ לרשימת היעד הראשית.",
            },
            {
                COMPANY: "BudgetCo",
                TITLE: "בקר/ית תקציב",
                LOCATION: "אשדוד",
                LINK: "https://jobs.example.test/3",
                SCORE: "92",
                STATUS: PENDING,
                STOP_REASON: "נדרש אישור לפני הגשה: יש דרישת ניסיון סביב 3 שנים.",
            },
        ]

        titles = [action["title"] for action in build_insights(rows)["next_actions"]]

        self.assertIn("להחליט אם מרחיבים מיקומים", titles)
        self.assertIn("למפות ניסיון גבולי לדרישות חובה", titles)

    def test_rejected_system_requirement_is_counted_but_not_a_next_action(self) -> None:
        row = {
            COMPANY: "DSV",
            TITLE: "Procurement Specialist",
            LOCATION: "Kiryat Gat",
            LINK: "https://jobs.example.test/4",
            SCORE: "90",
            STATUS: REJECTED,
            STOP_REASON: "Rejected: ERP appears to be a required skill.",
        }

        insights = build_insights([row])

        self.assertEqual(categories_for_row(row)[0].category, "system_skill_gap")
        self.assertEqual(insights["next_actions"][0]["title"], "להרחיב מקורות חיפוש")


if __name__ == "__main__":
    unittest.main()
