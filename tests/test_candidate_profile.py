from __future__ import annotations

import unittest

from src.candidate_profile import CandidateProfile, FactIssueSeverity, SystemSkillFact, assess_candidate_facts, safe_form_answers


TEST_PROFILE = CandidateProfile(
    full_name="קורן דהן",
    national_id="123456789",
    has_relatives_at_company=False,
    has_driving_license=True,
    has_car=True,
    can_arrive_independently=True,
    marketing_consent_approved=True,
    approved_salary_expectation=13000,
    system_skills=(
        SystemSkillFact("SAP", ("sap",), False),
        SystemSkillFact("ERP", ("erp",), False),
        SystemSkillFact("MRP", ("mrp",), False),
        SystemSkillFact("Priority", ("priority", "פריוריטי"), True),
        SystemSkillFact("Power BI", ("power bi", "מערכת bi"), None),
        SystemSkillFact("MS Project", ("ms project",), None),
        SystemSkillFact("Nibit", ("nibit",), None),
        SystemSkillFact("חשבשבת", ("חשבשבת",), True),
    ),
)


class CandidateProfileTests(unittest.TestCase):
    def test_id_and_relatives_are_verified_answers(self) -> None:
        assessment = assess_candidate_facts("הטופס דורש מספר תעודת זהות ותשובה האם יש קרובי משפחה בחברה.", profile=TEST_PROFILE)

        self.assertFalse(assessment.blockers)
        self.assertEqual({issue.code for issue in assessment.resolved}, {"national_id_available", "relatives_answer_available"})
        self.assertEqual(safe_form_answers(TEST_PROFILE)["national_id"], "123456789")
        self.assertEqual(safe_form_answers(TEST_PROFILE)["has_relatives_at_company"], "לא")

    def test_required_erp_is_disqualifying_because_candidate_has_no_experience(self) -> None:
        assessment = assess_candidate_facts("דרישות חובה: ניסיון במערכת ERP ועבודה מול ספקים.", profile=TEST_PROFILE)

        self.assertTrue(assessment.has_disqualifying_blocker)
        self.assertEqual(assessment.first_blocker.severity, FactIssueSeverity.DO_NOT_APPLY)
        self.assertIn("ERP", assessment.first_blocker.label)

    def test_required_mrp_is_disqualifying_even_when_it_appears_in_title(self) -> None:
        assessment = assess_candidate_facts("בקר/ית MRP וניהול לוגיסטי", profile=TEST_PROFILE)

        self.assertTrue(assessment.has_disqualifying_blocker)
        self.assertEqual(assessment.first_blocker.label, "MRP")

    def test_optional_priority_does_not_block_submission(self) -> None:
        assessment = assess_candidate_facts("ניסיון ברכש חובה; Priority או תוכנה דומה יתרון; Office ו-Excel.", profile=TEST_PROFILE)

        self.assertFalse(assessment.blockers)

    def test_optional_priority_is_not_punished_by_neighboring_required_skill(self) -> None:
        assessment = assess_candidate_facts("ניסיון ERP חובה, Priority יתרון.", profile=TEST_PROFILE)

        self.assertEqual([issue.label for issue in assessment.blockers], ["ERP"])

    def test_car_or_independent_arrival_is_resolved_when_verified(self) -> None:
        assessment = assess_candidate_facts("נדרשת ניידות והגעה עצמאית.", profile=TEST_PROFILE)

        self.assertFalse(assessment.has_human_blocker)
        self.assertEqual(assessment.resolved[0].code, "driving_or_car_available")

    def test_unverified_driving_still_requires_human_answer(self) -> None:
        profile = CandidateProfile(
            full_name="קורן דהן",
            national_id="123456789",
            has_relatives_at_company=False,
            has_driving_license=None,
            has_car=None,
            can_arrive_independently=None,
            marketing_consent_approved=True,
            approved_salary_expectation=13000,
            system_skills=TEST_PROFILE.system_skills,
        )
        assessment = assess_candidate_facts("נדרשת ניידות והגעה עצמאית.", profile=profile)

        self.assertTrue(assessment.has_human_blocker)
        self.assertEqual(assessment.first_blocker.code, "driving_or_car_unverified")

    def test_marketing_consent_is_resolved_when_approved(self) -> None:
        assessment = assess_candidate_facts("הרשמה כוללת תוכן שיווקי מצדדים שלישיים.", profile=TEST_PROFILE)

        self.assertFalse(assessment.blockers)
        self.assertEqual(assessment.resolved[0].code, "marketing_consent_approved")

    def test_salary_is_resolved_when_numeric_expectation_is_approved(self) -> None:
        assessment = assess_candidate_facts("הטופס דורש ציפיות שכר מספריות.", profile=TEST_PROFILE)

        self.assertFalse(assessment.blockers)
        self.assertEqual(assessment.resolved[0].code, "numeric_salary_approved")
        self.assertEqual(safe_form_answers(TEST_PROFILE)["approved_salary_expectation"], "13000")


if __name__ == "__main__":
    unittest.main()
