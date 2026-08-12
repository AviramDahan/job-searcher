from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.job_records import COMPANY, LINK, PENDING, REJECTED, SCORE, STATUS, TITLE, deduplicate_rows, duplicate_keys, job_key, load_rows, write_rows


class JobRecordsTests(unittest.TestCase):
    def test_nestle_job_key_uses_numeric_job_id(self) -> None:
        first = {
            LINK: "https://jobdetails.nestle.com/job/Sderot-%D7%A8%D7%9B%D7%96%D7%AA-%D7%9E%D7%A6/1411622433/"
        }
        second = {
            LINK: "https://jobdetails.nestle.com/job/Sderot-%D7%A8%D7%9B%D7%96_%D7%AA-%D7%9E%D7%A6/1411622433/"
        }

        self.assertEqual(job_key(first), "nestle:1411622433")
        self.assertEqual(job_key(second), "nestle:1411622433")
        self.assertEqual(duplicate_keys([first, second]), ["nestle:1411622433"])

    def test_drushim_job_key_uses_numeric_job_id(self) -> None:
        first = {LINK: "https://www.drushim.co.il/job/37735694/66ab8947/"}
        second = {LINK: "https://www.drushim.co.il/job/37735694/another-token/"}

        self.assertEqual(job_key(first), "drushim:37735694")
        self.assertEqual(job_key(second), "drushim:37735694")
        self.assertEqual(duplicate_keys([first, second]), ["drushim:37735694"])

    def test_deduplicate_rows_keeps_best_duplicate(self) -> None:
        rejected = {
            LINK: "https://www.drushim.co.il/job/37735694/66ab8947/",
            COMPANY: "Old",
            TITLE: "Old title",
            STATUS: REJECTED,
            SCORE: "66",
        }
        pending = {
            LINK: "https://www.drushim.co.il/job/37735694/another-token/",
            COMPANY: "Current",
            TITLE: "Current title",
            STATUS: PENDING,
            SCORE: "80",
        }

        deduped = deduplicate_rows([rejected, pending])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0][COMPANY], "Current")

    def test_write_rows_removes_broken_question_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "jobs.csv"
            write_rows(
                path,
                [
                    {
                        COMPANY: "Company ???",
                        TITLE: "Buyer",
                        LINK: "https://example.test",
                        STATUS: PENDING,
                        SCORE: "80",
                    }
                ],
            )

            text = path.read_text(encoding="utf-8-sig")
            rows = load_rows(path)

            self.assertNotIn("???", text)
            self.assertEqual(rows[0][COMPANY], "Company")


if __name__ == "__main__":
    unittest.main()
