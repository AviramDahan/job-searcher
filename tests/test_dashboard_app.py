from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.dashboard_app import DashboardPaths, build_alert_payload, dashboard_state, plan_job_submission, resend_telegram, update_job
from src.job_records import (
    COMPANY,
    COVER,
    CV,
    DATE,
    FIT,
    LINK,
    LOCATION,
    PENDING,
    REJECTED,
    REQUIREMENTS,
    SCORE,
    STATUS,
    STOP_REASON,
    SUBMITTED,
    TITLE,
    load_rows,
    write_rows,
)


def sample_rows() -> list[dict[str, str]]:
    return [
        {
            DATE: "2026-08-01",
            COMPANY: "Acme",
            TITLE: "Procurement Coordinator",
            LOCATION: "Sderot",
            LINK: "https://www.jobmaster.co.il/jobs/checknum.asp?key=1001",
            SCORE: "88",
            REQUIREMENTS: "Excel, suppliers, quotes",
            FIT: "Procurement and budget-control experience",
            STATUS: SUBMITTED,
            STOP_REASON: "",
            COVER: "Hello Acme",
            CV: "cv.pdf",
        },
        {
            DATE: "2026-08-01",
            COMPANY: "BudgetCo",
            TITLE: "Junior Budget Controller",
            LOCATION: "Beer Sheva",
            LINK: "https://jobs.example.test/2002",
            SCORE: "79",
            REQUIREMENTS: "Budget control, Excel",
            FIT: "Budget analysis and reporting",
            STATUS: PENDING,
            STOP_REASON: "Requires numeric salary expectation",
            COVER: "",
            CV: "",
        },
        {
            DATE: "2026-07-31",
            COMPANY: "RejectCo",
            TITLE: "Senior Sales Manager",
            LOCATION: "Ashdod",
            LINK: "https://jobs.example.test/3003",
            SCORE: "41",
            REQUIREMENTS: "Sales management",
            FIT: "",
            STATUS: REJECTED,
            STOP_REASON: "Senior sales role",
            COVER: "",
            CV: "",
        },
    ]


class DashboardAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = DashboardPaths(
            csv=root / "job_applications.csv",
            summary=root / "job_search_summary.md",
            manual_log=root / "manual_alert_log.json",
            retry_queue=root / "retry_queue.json",
            dashboard_log=root / "dashboard_alert_log.json",
        )
        write_rows(self.paths.csv, sample_rows())
        self.paths.summary.write_text("- מספר המשרות שנסרקו: 50\n", encoding="utf-8-sig")
        self.paths.manual_log.write_text(
            json.dumps(
                [
                    {"mode": "sent", "ok": True},
                    {"mode": "skipped_profile_mismatch", "ok": True},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8-sig",
        )
        self.paths.retry_queue.write_text(
            json.dumps([{"mode": "retry"}, {"mode": "manual"}], ensure_ascii=False),
            encoding="utf-8-sig",
        )
        self.env_patcher = patch.dict(os.environ, {"CANDIDATE_PROFILE_PATH": str(root / "missing-profile.json")}, clear=False)
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()
        self.tmp.cleanup()

    def test_dashboard_state_summarizes_tracker_files(self) -> None:
        state = dashboard_state(self.paths)

        self.assertEqual(state["counts"]["scanned"], 50)
        self.assertEqual(state["counts"]["documented"], 3)
        self.assertEqual(state["counts"]["submitted"], 1)
        self.assertEqual(state["counts"]["pending"], 1)
        self.assertEqual(state["counts"]["rejected"], 1)
        self.assertEqual(state["telegram"]["manual_alerts"]["sent"], 1)
        self.assertEqual(state["retry_queue"]["total"], 2)
        self.assertEqual(state["jobs"][0]["company"], "Acme")

    def test_update_job_adds_note_without_changing_status(self) -> None:
        key = "jobmaster:1001"
        with patch("src.dashboard_app.now_string", return_value="2026-08-01 21:00:00"):
            updated = update_job(self.paths, key, "add_note", note="called recruiter")

        rows = load_rows(self.paths.csv)
        row = next(item for item in rows if item[COMPANY] == "Acme")
        self.assertEqual(updated["status"], SUBMITTED)
        self.assertIn("called recruiter", row[STOP_REASON])

    def test_update_job_marks_pending_job_as_submitted(self) -> None:
        key = "manual:https://jobs.example.test/2002|budgetco|junior budget controller|beer sheva"
        with patch("src.dashboard_app.now_string", return_value="2026-08-01 21:05:00"):
            updated = update_job(self.paths, key, "mark_submitted", note="submitted by phone", cv_filename="new-cv.pdf")

        self.assertEqual(updated["status"], SUBMITTED)
        self.assertEqual(updated["date"], "2026-08-01")
        self.assertEqual(updated["cv"], "new-cv.pdf")
        self.assertIn("submitted by phone", updated["stop_reason"])

    def test_build_alert_payload_matches_job_status(self) -> None:
        submitted, pending, _ = sample_rows()

        submitted_payload = build_alert_payload(submitted, timestamp="2026-08-01 21:10:00")
        pending_payload = build_alert_payload(pending)

        self.assertEqual(submitted_payload["kind"], "submitted")
        self.assertEqual(submitted_payload["submitted_at"], "2026-08-01 21:10:00")
        self.assertEqual(pending_payload["kind"], "manual")
        self.assertIn("Requires numeric salary", pending_payload["blocker"])

    def test_resend_telegram_writes_dashboard_log(self) -> None:
        key = "jobmaster:1001"
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "-1001"}, clear=False):
            with patch("src.dashboard_app.send", return_value={"ok": True, "result": {"message_id": 7}}) as send_mock:
                result = resend_telegram(self.paths, key)

        self.assertTrue(result["ok"])
        self.assertEqual(result["message_id"], 7)
        self.assertTrue(self.paths.dashboard_log.exists())
        send_mock.assert_called_once()

    def test_plan_job_submission_returns_engine_decision(self) -> None:
        result = plan_job_submission(self.paths, "jobmaster:1001")

        self.assertEqual(result["job_key"], "jobmaster:1001")
        self.assertEqual(result["plan"]["site"], "JobMaster")
        self.assertIn("decision", result["plan"])


if __name__ == "__main__":
    unittest.main()
