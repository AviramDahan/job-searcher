from __future__ import annotations

import unittest

from src.sync_location_preferences import normalize_location_preferences


class SyncLocationPreferencesTests(unittest.TestCase):
    def test_normalizes_only_approved_locations(self) -> None:
        payload = {
            "generated_at": "2026-08-09T18:00:00Z",
            "location_preferences": {
                "approved_locations": {
                    "rehovot": {
                        "key": "rehovot",
                        "label": "רחובות",
                        "terms": ["רחובות", "rehovot"],
                        "approved": True,
                    },
                    "lod": {
                        "key": "lod",
                        "label": "לוד",
                        "terms": ["לוד", "lod"],
                        "approved": False,
                    },
                }
            },
        }

        normalized = normalize_location_preferences(payload)
        approved = normalized["location_preferences"]["approved_locations"]

        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["key"], "rehovot")
        self.assertIn("רחובות", approved[0]["terms"])


if __name__ == "__main__":
    unittest.main()
