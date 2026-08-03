from __future__ import annotations

import unittest
from dataclasses import replace

from src.candidate_profile import CandidateProfile, SystemSkillFact
from src.job_records import COMPANY, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE
from src.send_manual_alerts_from_csv import manual_alert_decision, target_rows


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
UNAPPROVED_MARKETING_PROFILE = replace(TEST_PROFILE, marketing_consent_approved=False)


def row(
    reason: str,
    requirements: str = "",
    link: str = "https://www.jobmaster.co.il/jobs/checknum.asp?key=1",
    status: str = PENDING,
) -> dict[str, str]:
    return {
        COMPANY: "Test Company",
        TITLE: "Buyer",
        LOCATION: "Test",
        LINK: link,
        SCORE: "85",
        STATUS: status,
        STOP_REASON: reason,
        REQUIREMENTS: requirements,
    }


class ManualAlertDecisionTests(unittest.TestCase):
    def test_required_erp_is_not_sent_as_manual_submission(self) -> None:
        decision = manual_alert_decision(
            row("LinkedIn login required", "Experience with ERP systems."),
            profile=TEST_PROFILE,
        )

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.log_mode, "skipped_profile_mismatch")

    def test_retryable_form_failure_is_not_sent_as_manual_submission(self) -> None:
        decision = manual_alert_decision(
            row("הטופס הקפיא את ההגשה באוטומציה", "Priority או תוכנה דומה יתרון; Excel."),
            profile=TEST_PROFILE,
        )

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.log_mode, "skipped_retryable")

    def test_captcha_is_sent_as_human_gate(self) -> None:
        decision = manual_alert_decision(
            row("The form is protected by reCAPTCHA."),
            profile=TEST_PROFILE,
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.log_mode, "sent")

    def test_approved_marketing_consent_is_not_sent_as_manual_submission(self) -> None:
        decision = manual_alert_decision(
            row(
                "Registration requires third-party marketing consent",
                link="https://www.drushim.co.il/job/1",
            ),
            profile=TEST_PROFILE,
        )

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.log_mode, "skipped_retryable")

    def test_manual_required_no_direct_form_sends_alert(self) -> None:
        decision = manual_alert_decision(
            row(
                "אין אתר חברה רשמי פעיל; נדרשת הגשה ידנית.",
                "Procurement, suppliers, Excel.",
                link="https://www.drushim.co.il/job/37905896/3d25ce42/",
                status=MANUAL_REQUIRED,
            ),
            profile=TEST_PROFILE,
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.log_mode, "sent")

    def test_approved_marketing_consent_does_not_override_experience_gate(self) -> None:
        decision = manual_alert_decision(
            row(
                "Registration requires third-party marketing consent",
                link="https://www.drushim.co.il/job/1",
            )
            | {TITLE: "PMO"},
            profile=TEST_PROFILE,
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.log_mode, "sent")

    def test_unapproved_marketing_consent_is_still_sent_as_manual_submission(self) -> None:
        decision = manual_alert_decision(
            row(
                "Registration requires third-party marketing consent",
                link="https://www.drushim.co.il/job/1",
            ),
            profile=UNAPPROVED_MARKETING_PROFILE,
        )

        self.assertTrue(decision.should_alert)
        self.assertEqual(decision.log_mode, "sent")

    def test_id_and_relatives_do_not_create_manual_alert_without_real_human_gate(self) -> None:
        decision = manual_alert_decision(
            row("הטופס דורש תעודת זהות וקרובי משפחה בחברה.", "Procurement experience."),
            profile=TEST_PROFILE,
        )

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.log_mode, "skipped_resolved_candidate_fact")

    def test_verified_system_skill_does_not_create_manual_alert(self) -> None:
        decision = manual_alert_decision(
            row("נעצר כי חשבשבת לא הייתה מאומתת.", "Excel וחשבשבת"),
            profile=TEST_PROFILE,
        )

        self.assertFalse(decision.should_alert)
        self.assertEqual(decision.log_mode, "skipped_resolved_candidate_fact")

    def test_default_target_rows_include_only_manual_required(self) -> None:
        pending = row("נדרש אישור לפני הגשה: חסר אישור מרחק.")
        manual = row(
            "CAPTCHA באתר ההגשה.",
            status=MANUAL_REQUIRED,
        )

        self.assertEqual(target_rows([pending, manual]), [manual])
        self.assertEqual(target_rows([pending, manual], include_pending_approvals=True), [pending, manual])


if __name__ == "__main__":
    unittest.main()
