from __future__ import annotations

import unittest

from src.categorize_manual_required import categorize_rows
from src.job_records import COMPANY, LINK, MANUAL_REQUIRED, PENDING, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE


def row(reason: str) -> dict[str, str]:
    return {
        COMPANY: "IAI",
        TITLE: "Buyer",
        LINK: "https://jobs.iai.co.il/job/1/",
        SCORE: "90",
        REQUIREMENTS: "Bachelor degree; procurement; Excel.",
        STATUS: PENDING,
        STOP_REASON: reason,
    }


class CategorizeManualRequiredTests(unittest.TestCase):
    def test_captcha_moves_to_manual_required(self) -> None:
        rows = [row("The form is protected by reCAPTCHA.")]

        changed = categorize_rows(rows)

        self.assertEqual(changed, 1)
        self.assertEqual(rows[0][STATUS], MANUAL_REQUIRED)

    def test_policy_question_stays_pending(self) -> None:
        rows = [row("The form requires numeric salary expectation.")]

        changed = categorize_rows(rows)

        self.assertEqual(changed, 0)
        self.assertEqual(rows[0][STATUS], PENDING)


if __name__ == "__main__":
    unittest.main()
