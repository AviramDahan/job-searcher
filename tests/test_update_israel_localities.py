from __future__ import annotations

import unittest

from src.update_israel_localities import build_locality_record, itm_to_wgs84, parse_itm_coordinates


class UpdateIsraelLocalitiesTests(unittest.TestCase):
    def test_parse_itm_coordinates_splits_cbs_combined_coordinate(self) -> None:
        self.assertEqual(parse_itm_coordinates(174014614251), (174014, 614251))

    def test_itm_to_wgs84_converts_known_city_coordinates(self) -> None:
        lat, lng = itm_to_wgs84(159680, 619930)

        self.assertAlmostEqual(lat, 31.67, places=2)
        self.assertAlmostEqual(lng, 34.57, places=2)

    def test_build_locality_record_normalizes_terms_and_metadata(self) -> None:
        record = {
            "שם יישוב": "שחר",
            "סמל יישוב": 7,
            "תעתיק": "SHAHAR",
            "שם מחוז": "הדרום",
            "שם נפה": "אשקלון",
            "שם מעמד מונציפאלי": "מועצה אזורית לכיש",
            "קואורדינטות": 174014614251,
            "שנה": 2023,
            "שם יישוב באנגלית": "Shahar",
            "סך הכל אוכלוסייה 2023 - ארעי": 812,
        }

        locality = build_locality_record(record)

        self.assertIsNotNone(locality)
        assert locality is not None
        self.assertEqual(locality["key"], "cbs_7")
        self.assertEqual(locality["label"], "שחר")
        self.assertIn("Shahar", locality["terms"])
        self.assertEqual(locality["district"], "הדרום")
        self.assertEqual(locality["population"], 812)
        self.assertTrue(31.5 <= locality["lat"] <= 31.8)
        self.assertTrue(34.6 <= locality["lng"] <= 34.9)


if __name__ == "__main__":
    unittest.main()
