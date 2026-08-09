from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.export_pages_dashboard import build_payload
from src.job_records import COMPANY, LINK, PENDING, SCORE, STATUS, TITLE, write_rows


class ExportPagesDashboardTests(unittest.TestCase):
    def test_build_payload_includes_conversion_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "job_applications.csv"
            summary_path = root / "job_search_summary.md"
            plan_path = root / "submission_engine_plan.json"
            retry_path = root / "retry_queue.json"

            write_rows(
                csv_path,
                [
                    {
                        COMPANY: "BudgetCo",
                        TITLE: "Junior Budget Controller",
                        LINK: "https://www.drushim.co.il/job/1/",
                        SCORE: "80",
                        STATUS: PENDING,
                    }
                ],
            )
            summary_path.write_text("- מספר המשרות שנסרקו: 10\n", encoding="utf-8-sig")
            plan_path.write_text(
                json.dumps([{"decision": "not_supported", "site": "Drushim", "can_attempt": False}]),
                encoding="utf-8-sig",
            )
            retry_path.write_text(json.dumps([{"mode": "company_fallback", "site": "Drushim"}]), encoding="utf-8-sig")

            payload = build_payload(csv_path, summary_path, "קורן דהן", submission_plan_path=plan_path, retry_queue_path=retry_path)

            self.assertEqual(payload["conversion"]["counts"]["scanned"], 10)
            self.assertEqual(payload["conversion"]["submission_plan"]["decisions"]["not_supported"], 1)
            self.assertEqual(payload["conversion"]["retry_queue"]["modes"]["company_fallback"], 1)
            self.assertIn("location_policy", payload)
            self.assertIn("שדרות", [item["label"] for item in payload["location_policy"]["default_approved"]])
            self.assertIn("רחובות", [item["label"] for item in payload["location_policy"]["user_approvable"]])


            self.assertIn("ניר עם", [item["label"] for item in payload["location_policy"]["nearby_options"]])
            self.assertTrue(payload["location_policy"]["map_points"])


if __name__ == "__main__":
    unittest.main()
