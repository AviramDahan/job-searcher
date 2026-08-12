from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.sync_location_preferences import (
    SyncEndpointError,
    endpoint_from_dashboard_config,
    normalize_location_preferences,
    require_healthy_payload,
    resolve_endpoint,
)


class SyncLocationPreferencesTests(unittest.TestCase):
    def test_normalizes_only_approved_locations(self) -> None:
        payload = {
            "generated_at": "2026-08-09T18:00:00Z",
            "location_preferences": {
                "radius_km": 60,
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
        self.assertEqual(normalized["location_preferences"]["radius_km"], 60)

    def test_resolves_endpoint_from_dashboard_config(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "dashboard-config.json"
            config.write_text('{"updatesEndpoint":"https://worker.example.test/sync"}', encoding="utf-8")

            self.assertEqual(endpoint_from_dashboard_config(config), "https://worker.example.test/sync")
            self.assertEqual(resolve_endpoint("", config), "https://worker.example.test/sync")
            self.assertEqual(resolve_endpoint("https://override.example.test/sync", config), "https://override.example.test/sync")

    def test_relative_dashboard_endpoint_resolves_to_sites_origin(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "dashboard-config.json"
            config.write_text('{"updatesEndpoint":"/api/sync"}', encoding="utf-8")

            self.assertEqual(
                endpoint_from_dashboard_config(config),
                "https://job-searcher-live-dashboard.aviramsdahan.chatgpt.site/api/sync",
            )

    def test_unhealthy_sync_payload_is_not_treated_as_success(self) -> None:
        with self.assertRaises(SyncEndpointError):
            require_healthy_payload({"ok": False, "error": "sync_storage_disabled"})

    def test_alerts_only_payload_is_not_treated_as_durable_preferences(self) -> None:
        with self.assertRaises(SyncEndpointError):
            require_healthy_payload({"ok": True, "storage_status": "alerts_only", "storage_warning": "jsonblob_read_404"})


if __name__ == "__main__":
    unittest.main()
