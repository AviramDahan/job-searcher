from __future__ import annotations

import unittest

from src.job_records import LINK, duplicate_keys, job_key


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


if __name__ == "__main__":
    unittest.main()
