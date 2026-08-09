from __future__ import annotations

import unittest

from src.conversion_audit import build_audit
from src.job_records import LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, SUBMITTED


class ConversionAuditTests(unittest.TestCase):
    def test_build_audit_reports_funnel_and_source_quality(self) -> None:
        rows = [
            {LINK: "https://www.jobmaster.co.il/jobs/checknum.asp?key=1", STATUS: SUBMITTED},
            {LINK: "https://www.drushim.co.il/job/1/", STATUS: PENDING},
            {LINK: "https://www.alljobs.co.il/Search/UploadSingle.aspx?JobID=1", STATUS: MANUAL_REQUIRED},
            {LINK: "https://www.jobnet.co.il/jobs?positionid=1", STATUS: REJECTED},
        ]

        audit = build_audit(rows, scanned=100, plans=[{"decision": "policy_required", "site": "Drushim"}], retry_items=[])

        self.assertEqual(audit["counts"]["scanned"], 100)
        self.assertEqual(audit["counts"]["total"], 4)
        self.assertEqual(audit["counts"]["submitted"], 1)
        self.assertEqual(audit["submission_plan"]["plans"], 1)
        self.assertTrue(any(item["source"] == "JobMaster" for item in audit["source_quality"]))
        self.assertTrue(audit["recommendations"])


if __name__ == "__main__":
    unittest.main()
