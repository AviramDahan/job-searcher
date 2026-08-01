from __future__ import annotations

import unittest

from src.jobify_apply import classify_jobify_state


class JobifyApplyTests(unittest.TestCase):
    def test_existing_email_error_is_account_gate_even_after_upload(self) -> None:
        stage, reason = classify_jobify_state(
            "https://jobify360.co.il/ab-type",
            "קורות החיים הועלו בהצלחה",
            "כתובת האימייל כבר קיימת",
        )

        self.assertEqual(stage, "account_gate")
        self.assertIn("existing email", reason)

    def test_salary_screen_remains_salary_gate(self) -> None:
        stage, reason = classify_jobify_state(
            "https://jobify360.co.il/ob-salary",
            "ציפיות שכר",
        )

        self.assertEqual(stage, "salary_gate")
        self.assertIn("salary", reason.lower())

    def test_plain_upload_without_gate_is_uploaded(self) -> None:
        stage, _ = classify_jobify_state(
            "https://jobify360.co.il/ab-type",
            "קורות החיים הועלו בהצלחה",
        )

        self.assertEqual(stage, "uploaded")


if __name__ == "__main__":
    unittest.main()
