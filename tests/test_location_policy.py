from __future__ import annotations

import unittest

from src.location_policy import LocationDecision, assess_location, location_policy_payload


class LocationPolicyTests(unittest.TestCase):
    def test_far_secondary_city_is_rejected_instead_of_pending_approval(self) -> None:
        assessment = assess_location("ראשון לציון")

        self.assertEqual(assessment.decision, LocationDecision.OUT_OF_SCOPE)
        self.assertIn("רחוק משדרות", assessment.reason)

    def test_yavne_is_no_longer_a_primary_target_location(self) -> None:
        assessment = assess_location("יבנה")

        self.assertEqual(assessment.decision, LocationDecision.OUT_OF_SCOPE)
        self.assertIn("יבנה", assessment.matched_terms)

    def test_southern_location_still_keeps_multi_location_posting_in_scope(self) -> None:
        assessment = assess_location("- אשדוד; - ראשון לציון, רחובות, יבנה")

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("אשדוד", assessment.matched_terms)

    def test_far_city_with_limited_hybrid_is_still_rejected(self) -> None:
        assessment = assess_location("רחובות", "היברידי עד פעמיים בשבוע")

        self.assertEqual(assessment.decision, LocationDecision.OUT_OF_SCOPE)
        self.assertIn("רחובות", assessment.matched_terms)

    def test_dashboard_approved_city_becomes_in_scope(self) -> None:
        assessment = assess_location("רחובות", approved_location_terms=("רחובות", "rehovot"))

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("אושר בדשבורד", assessment.reason)

    def test_full_remote_can_override_far_office_city(self) -> None:
        assessment = assess_location("רחובות", "עבודה מרחוק מלאה")

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("מרחוק", assessment.reason)


    def test_nearby_settlement_requires_dashboard_approval(self) -> None:
        assessment = assess_location("ניר עם", approved_location_terms=())

        self.assertEqual(assessment.decision, LocationDecision.OUT_OF_SCOPE)

    def test_nearby_settlement_becomes_in_scope_after_dashboard_approval(self) -> None:
        assessment = assess_location("ניר עם", approved_location_terms=("ניר עם", "nir am"))

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("ניר עם", assessment.matched_terms)

    def test_location_policy_payload_includes_map_and_nearby_locations(self) -> None:
        payload = location_policy_payload()

        self.assertEqual(payload["home"]["key"], "sderot")
        self.assertIn("map_points", payload)
        self.assertIn("ניר עם", [item["label"] for item in payload["nearby_options"]])
        self.assertIn("דרום", [item["label"] for item in payload["region_options"]])
        for region in payload["region_options"]:
            self.assertIn("map_area", region)
            self.assertGreaterEqual(len(region["map_area"]["polygon"]), 3)
        self.assertIn(60, payload["radius_options_km"])
        self.assertGreaterEqual(payload["israel_localities_count"], 1000)
        self.assertGreaterEqual(len(payload["map_points"]), payload["israel_localities_count"])
        self.assertEqual(payload["israel_localities_source"]["resource_id"], "d47a54ff-87f0-44b3-b33a-f284c0c38e5a")
        self.assertIn("שחר", [item["label"] for item in payload["map_points"]])

    def test_dashboard_approved_region_becomes_in_scope(self) -> None:
        assessment = assess_location("תל אביב", approved_location_terms=("תל אביב", "מרכז", "tel aviv"))

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)

    def test_radius_can_make_known_nearby_city_in_scope(self) -> None:
        assessment = assess_location("רחובות", approved_location_terms=(), radius_km=60)

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("רדיוס", assessment.reason)

    def test_radius_can_use_cbs_localities_not_in_manual_list(self) -> None:
        assessment = assess_location("שחר", approved_location_terms=(), radius_km=40)

        self.assertEqual(assessment.decision, LocationDecision.IN_SCOPE)
        self.assertIn("רדיוס", assessment.reason)

    def test_radius_does_not_approve_far_cbs_locality(self) -> None:
        assessment = assess_location("חיפה", approved_location_terms=(), radius_km=40)

        self.assertEqual(assessment.decision, LocationDecision.OUT_OF_SCOPE)


if __name__ == "__main__":
    unittest.main()
