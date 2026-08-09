from __future__ import annotations

import unittest

from src.location_policy import LocationDecision, assess_location


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


if __name__ == "__main__":
    unittest.main()
