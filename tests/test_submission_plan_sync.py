from __future__ import annotations

import unittest

from src.job_records import LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, STOP_REASON
from src.submission_engine import SubmissionDecision
from src.submission_plan_sync import sync_rows


def row(status: str = PENDING, reason: str = "") -> dict[str, str]:
    return {
        "קישור": "https://www.jobmaster.co.il/jobs/checknum.asp?key=111",
        "סטטוס": status,
        "סיבת פסילה או עצירה": reason,
        "שם קובץ קורות החיים שצורף": "",
    }


def plan(decision: SubmissionDecision, reason: str = "reason", next_step: str = "next") -> dict:
    return {
        "job": {"key": "jobmaster:111"},
        "decision": decision.value,
        "reason": reason,
        "next_step": next_step,
        "can_attempt": False,
    }


class SubmissionPlanSyncTests(unittest.TestCase):
    def test_do_not_apply_marks_pending_row_rejected(self) -> None:
        rows = [row()]

        stats = sync_rows(rows, [plan(SubmissionDecision.DO_NOT_APPLY)])

        self.assertEqual(stats.marked_rejected, 1)
        self.assertEqual(rows[0][STATUS], REJECTED)
        self.assertIn("נפסל", rows[0][STOP_REASON])

    def test_human_gate_marks_pending_row_manual_required(self) -> None:
        rows = [row()]

        stats = sync_rows(rows, [plan(SubmissionDecision.HUMAN_GATE)])

        self.assertEqual(stats.marked_manual_required, 1)
        self.assertEqual(rows[0][STATUS], MANUAL_REQUIRED)
        self.assertIn("נדרשת הגשה ידנית", rows[0][STOP_REASON])

    def test_policy_required_keeps_pending_but_updates_reason(self) -> None:
        rows = [row()]

        stats = sync_rows(rows, [plan(SubmissionDecision.POLICY_REQUIRED)])

        self.assertEqual(stats.marked_pending_policy, 1)
        self.assertEqual(rows[0][STATUS], PENDING)
        self.assertIn("נדרש אישור לפני הגשה", rows[0][STOP_REASON])

    def test_synced_reason_is_idempotent(self) -> None:
        reason = "נדרש אישור לפני הגשה: reason השלב הבא: next"
        rows = [row(reason=reason)]

        stats = sync_rows(rows, [plan(SubmissionDecision.POLICY_REQUIRED, reason="reason", next_step="next")])

        self.assertEqual(stats.changed, 0)
        self.assertEqual(rows[0][STOP_REASON], reason)

    def test_protected_manual_row_is_not_overwritten(self) -> None:
        rows = [row(status=MANUAL_REQUIRED, reason="Manual gate: official form requires CAPTCHA.")]

        stats = sync_rows(rows, [plan(SubmissionDecision.HUMAN_GATE, reason="new")])

        self.assertEqual(stats.skipped_protected, 1)
        self.assertEqual(rows[0][STOP_REASON], "Manual gate: official form requires CAPTCHA.")

    def test_manual_required_row_is_not_downgraded_to_pending(self) -> None:
        rows = [row(status=MANUAL_REQUIRED, reason="Needs manual upload")]

        stats = sync_rows(rows, [plan(SubmissionDecision.POLICY_REQUIRED)])

        self.assertEqual(stats.skipped_protected, 1)
        self.assertEqual(rows[0][STATUS], MANUAL_REQUIRED)
        self.assertEqual(rows[0][STOP_REASON], "Needs manual upload")

    def test_manual_required_fallback_reason_is_not_overwritten(self) -> None:
        reason = "נדרשת הגשה ידנית: נבדק fallback רשמי; לא נמצא טופס חברה ישיר."
        rows = [row(status=MANUAL_REQUIRED, reason=reason)]

        stats = sync_rows(rows, [plan(SubmissionDecision.HUMAN_GATE, reason="generic blocker")])

        self.assertEqual(stats.skipped_protected, 1)
        self.assertEqual(rows[0][STATUS], MANUAL_REQUIRED)
        self.assertEqual(rows[0][STOP_REASON], reason)


if __name__ == "__main__":
    unittest.main()
