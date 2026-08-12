from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.system_health_check import check_csv, check_job_data


class SystemHealthCheckTests(unittest.TestCase):
    def test_csv_detects_three_question_mark_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.csv"
            path.write_text("a,b\nsafe,broken ??? text\n", encoding="utf-8-sig")

            check = check_csv(path)

            self.assertFalse(check.ok)
            self.assertTrue(check.details["contains_replacement_question_runs"])

    def test_job_data_detects_three_question_mark_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "job-data.json"
            path.write_text('{"jobs":[{"title":"broken ??? text"}]}', encoding="utf-8")

            check = check_job_data(path)

            self.assertFalse(check.ok)
            self.assertTrue(check.details["contains_replacement_question_runs"])


if __name__ == "__main__":
    unittest.main()
