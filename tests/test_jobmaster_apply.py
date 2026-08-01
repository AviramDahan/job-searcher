from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.job_records import COMPANY, CV, DATE, FIT, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, TITLE, load_rows, write_rows
from src.jobmaster_apply import JobMasterResult, JobMasterStage, classify_page_state, expected_cv_name, job_id_from_url
from src.submission_engine import SubmissionRunMode, SubmissionRunStatus, plan_jobs, record_submission_success, run_plan


def row() -> dict[str, str]:
    return {
        DATE: "2026-08-01",
        COMPANY: "Acme",
        TITLE: "Procurement Specialist",
        LOCATION: "Sderot",
        LINK: "https://www.jobmaster.co.il/jobs/checknum.asp?key=9812089",
        SCORE: "88",
        REQUIREMENTS: "Procurement, suppliers, Excel",
        FIT: "Strong procurement fit",
        STATUS: "נדרש אישור",
        STOP_REASON: "",
        CV: "",
    }


class JobMasterApplyTests(unittest.TestCase):
    def test_job_id_from_url_uses_key_query_param(self) -> None:
        self.assertEqual(job_id_from_url("https://www.jobmaster.co.il/jobs/checknum.asp?key=9812089"), "9812089")

    def test_classify_page_state_detects_login_and_success(self) -> None:
        self.assertEqual(
            classify_page_state("https://account.jobmaster.co.il/?r=x", "כניסת משתמש\nסיסמה"),
            JobMasterStage.LOGIN_REQUIRED,
        )
        self.assertEqual(
            classify_page_state("https://www.jobmaster.co.il/jobs/checknum.asp?key=1", "קורות החיים נשלחו בהצלחה"),
            JobMasterStage.SUBMITTED,
        )

    def test_expected_cv_name_prefers_override(self) -> None:
        self.assertEqual(expected_cv_name(Path("data/private/current.pdf"), "from-row.pdf"), "from-row.pdf")

    def test_expected_cv_name_ignores_manual_tracker_note(self) -> None:
        self.assertEqual(expected_cv_name(Path("data/private/current.pdf"), "לא צורף - נדרשת השלמה ידנית"), "current.pdf")

    def test_engine_jobmaster_prepare_maps_to_prepared_status(self) -> None:
        plans = plan_jobs([row()])
        fake = JobMasterResult(
            site="JobMaster",
            job_key=plans[0].job.key,
            job_url=plans[0].job.link,
            stage=JobMasterStage.FORM_PREPARED.value,
            submitted=False,
            reason="prepared",
            next_step="submit later",
            current_url=plans[0].job.link,
            evidence="evidence.json",
            cv_filename="cv.pdf",
        )
        with patch("src.submission_engine.run_jobmaster_application", return_value=fake):
            result = asyncio.run(run_plan(plans[0], SubmissionRunMode.PREPARE, Path(".")))

        self.assertEqual(result.status, SubmissionRunStatus.PREPARED.value)
        self.assertEqual(result.evidence, "evidence.json")
        self.assertEqual(result.next_step, "submit later")

    def test_record_submission_success_updates_tracker_row(self) -> None:
        plans = plan_jobs([row()])
        result = asyncio.run(run_plan(plans[0], SubmissionRunMode.PLAN_ONLY, Path(".")))
        object.__setattr__(result, "status", SubmissionRunStatus.SUBMITTED.value)
        object.__setattr__(result, "evidence", "data/evidence/jobmaster/test.json")
        object.__setattr__(result, "attempted_at", "2026-08-01T21:00:00")

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "jobs.csv"
            write_rows(csv_path, [row()])
            changed = record_submission_success(csv_path, plans[0], result, cv_filename="current.pdf")
            updated = load_rows(csv_path)[0]

        self.assertTrue(changed)
        self.assertEqual(updated[STATUS], SUBMITTED)
        self.assertEqual(updated[DATE], "2026-08-01")
        self.assertEqual(updated[CV], "current.pdf")
        self.assertIn("JobMaster adapter", updated[STOP_REASON])


if __name__ == "__main__":
    unittest.main()
