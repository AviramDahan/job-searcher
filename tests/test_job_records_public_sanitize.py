from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.job_records import (
    COMPANY,
    COVER,
    CV,
    DATE,
    FIT,
    HEADERS,
    LINK,
    LOCATION,
    REQUIREMENTS,
    SCORE,
    STATUS,
    STOP_REASON,
    TITLE,
    load_rows,
    write_rows,
)


class JobRecordsPublicSanitizeTests(unittest.TestCase):
    def test_write_rows_translates_public_status_text_without_touching_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "jobs.csv"
            link = "https://example.test/Ashdod/job"
            row = {header: "" for header in HEADERS}
            row.update(
                {
                    DATE: "2026-08-19",
                    COMPANY: "חברה",
                    TITLE: "תפקיד",
                    LOCATION: "Ashdod",
                    LINK: link,
                    SCORE: "90",
                    REQUIREMENTS: "Office",
                    FIT: "מתאים",
                    STATUS: "נפסל",
                    STOP_REASON: (
                        "Rejected: AllJobs automation was blocked; do not retry manually unless "
                        "an official direct posting is found."
                    ),
                    COVER: "",
                    CV: "koren_dahan_cv.pdf",
                }
            )

            write_rows(path, [row])
            rows = load_rows(path)

        self.assertEqual(rows[0][LINK], link)
        self.assertIn("האוטומציה ב-AllJobs נחסמה", rows[0][STOP_REASON])
        self.assertNotIn("Rejected:", rows[0][STOP_REASON])
        self.assertNotIn("do not retry", rows[0][STOP_REASON])


if __name__ == "__main__":
    unittest.main()
