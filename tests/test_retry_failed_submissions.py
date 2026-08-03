from __future__ import annotations

import unittest
from dataclasses import replace

from src.candidate_profile import CandidateProfile, SystemSkillFact
from src.job_records import COMPANY, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, PENDING
from src.retry_failed_submissions import RetryMode, build_retry_alert_payload, build_retry_items
from src.send_job_status_alerts import build_message
from src.send_retry_queue_alerts import build_blocked_alert


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
UNVERIFIED_DRIVING_PROFILE = replace(TEST_PROFILE, has_driving_license=None, has_car=None, can_arrive_independently=None)


def row(company: str, title: str, link: str, reason: str, score: str = "80") -> dict[str, str]:
    return {
        COMPANY: company,
        TITLE: title,
        LOCATION: "Test",
        LINK: link,
        SCORE: score,
        STATUS: PENDING,
        STOP_REASON: reason,
    }


class RetryQueueTests(unittest.TestCase):
    def test_login_failures_are_retryable(self) -> None:
        items = build_retry_items(
            [
                row(
                    "DSV",
                    "Procurement Specialist",
                    "https://jobs.dsv.com/job/example",
                    "SuccessFactors requires account creation",
                    "90",
                )
            ],
            profile=TEST_PROFILE,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].mode, RetryMode.AUTO_RETRYABLE.value)
        self.assertTrue(items[0].can_resend_now)

    def test_failed_existing_account_password_is_human_gate(self) -> None:
        items = build_retry_items(
            [
                row(
                    "JobMaster",
                    "Buyer",
                    "https://www.jobmaster.co.il/jobs/checknum.asp?key=9812089",
                    "ניסיון התחברות עם הסיסמה שסופקה נכשל, והרשמה החזירה שהמייל כבר קיים במערכת. נדרש להתחבר/לאפס סיסמה.",
                    "78",
                )
            ],
            profile=TEST_PROFILE,
        )

        self.assertEqual(items[0].mode, RetryMode.HUMAN_GATE.value)
        self.assertFalse(items[0].can_resend_now)

    def test_captcha_failures_are_human_gate(self) -> None:
        items = build_retry_items(
            [
                row(
                    "IAI",
                    "Buyer",
                    "https://jobs.iai.co.il/job/1/",
                    "The form is protected by reCAPTCHA",
                    "96",
                )
            ],
            profile=TEST_PROFILE,
        )
        self.assertEqual(items[0].mode, RetryMode.HUMAN_GATE.value)
        self.assertFalse(items[0].can_resend_now)

    def test_marketing_consent_requires_policy(self) -> None:
        items = build_retry_items(
            [
                row(
                    "Drushim",
                    "Buyer",
                    "https://www.drushim.co.il/job/1",
                    "Registration requires third-party marketing consent",
                    "86",
                )
            ],
            profile=UNAPPROVED_MARKETING_PROFILE,
        )
        self.assertEqual(items[0].mode, RetryMode.POLICY_REQUIRED.value)
        self.assertFalse(items[0].can_resend_now)

    def test_approved_marketing_consent_uses_drushim_company_fallback(self) -> None:
        items = build_retry_items(
            [
                row(
                    "Drushim",
                    "Buyer",
                    "https://www.drushim.co.il/job/1",
                    "Registration requires third-party marketing consent",
                    "86",
                )
            ],
            profile=TEST_PROFILE,
        )
        self.assertEqual(items[0].mode, RetryMode.COMPANY_FALLBACK.value)
        self.assertTrue(items[0].can_resend_now)
        self.assertEqual(items[0].action, "use_company_site_fallback")

    def test_jobnet_login_like_blocker_is_manual_until_adapter_exists(self) -> None:
        items = build_retry_items(
            [
                row(
                    "Jobnet",
                    "Buyer",
                    "https://www.jobnet.co.il/jobs?positionid=13300382",
                    "The application path depends on login, account state, or a site session.",
                    "86",
                )
            ],
            profile=TEST_PROFILE,
        )

        self.assertEqual(items[0].mode, RetryMode.HUMAN_GATE.value)
        self.assertFalse(items[0].can_resend_now)
        self.assertEqual(items[0].action, "fill_until_human_gate")

    def test_required_erp_excludes_item_from_retry_queue(self) -> None:
        source_row = row(
            "Variscite",
            "Purchasing Agent",
            "https://il.linkedin.com/jobs/view/purchasing-agent-at-variscite-ltd-4444115835",
            "LinkedIn login required",
            "89",
        )
        source_row[REQUIREMENTS] = "Experience with ERP systems, familiarity with Priority"

        items = build_retry_items([source_row], profile=TEST_PROFILE)

        self.assertEqual(items, [])

    def test_optional_priority_does_not_block_form_retry(self) -> None:
        source_row = row(
            "AllJobs",
            "Procurement Coordinator",
            "https://www.alljobs.co.il/Search/UploadSingle.aspx?JobID=1",
            "הטופס הקפיא את ההגשה באוטומציה",
            "82",
        )
        source_row[REQUIREMENTS] = "Procurement experience; Priority או תוכנה דומה יתרון; Excel."

        items = build_retry_items([source_row], profile=TEST_PROFILE)

        self.assertEqual(items[0].mode, RetryMode.AUTO_RETRYABLE.value)
        self.assertEqual(items[0].failure_kind, "form_automation_unreliable")

    def test_verified_id_and_relatives_allow_captcha_human_gate(self) -> None:
        source_row = row(
            "IAI",
            "Buyer",
            "https://jobs.iai.co.il/job/1/",
            "The official form requires תעודת זהות and קרובי משפחה בחברה, then reCAPTCHA.",
            "96",
        )
        source_row[REQUIREMENTS] = "Bachelor's degree; procurement experience; Excel."

        items = build_retry_items([source_row], profile=TEST_PROFILE)

        self.assertEqual(items[0].mode, RetryMode.HUMAN_GATE.value)
        self.assertEqual(items[0].failure_kind, "captcha_or_security")
        self.assertTrue(items[0].candidate_facts)
        self.assertFalse(items[0].candidate_blockers)

    def test_unverified_non_system_blocker_is_excluded(self) -> None:
        items = build_retry_items(
            [
                row(
                    "Nestle",
                    "Buyer",
                    "https://jobdetails.nestle.com/job/example",
                    "The role requires independent arrival by car",
                    "91",
                )
            ],
            profile=UNVERIFIED_DRIVING_PROFILE,
        )
        self.assertEqual(items, [])

    def test_resolved_candidate_fact_only_blocker_becomes_retryable(self) -> None:
        items = build_retry_items(
            [
                row(
                    "Nestle",
                    "Buyer",
                    "https://jobdetails.nestle.com/job/example",
                    "The role requires independent arrival by car",
                    "91",
                )
            ],
            profile=TEST_PROFILE,
        )

        self.assertEqual(items[0].mode, RetryMode.AUTO_RETRYABLE.value)
        self.assertEqual(items[0].failure_kind, "sensitive_field")
        self.assertTrue(items[0].candidate_facts)

    def test_resolved_system_skill_only_blocker_becomes_retryable(self) -> None:
        source_row = row(
            "JobMaster",
            "Purchasing Clerk",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=2",
            "The form stopped because חשבשבת was not verified",
            "80",
        )
        source_row[REQUIREMENTS] = "Excel וחשבשבת"

        items = build_retry_items([source_row], profile=TEST_PROFILE)

        self.assertEqual(items[0].mode, RetryMode.AUTO_RETRYABLE.value)
        self.assertEqual(items[0].failure_kind, "unverified_system_skill")

    def test_retry_alert_uses_fit_text_and_clean_hebrew(self) -> None:
        source_row = row(
            "DSV",
            "Procurement Specialist",
            "https://jobs.dsv.com/job/example",
            "SuccessFactors requires account creation",
            "90",
        )
        source_row["סיבות להתאמה"] = "תואר בכלכלה; ניסיון ברכש; עבודה מול ספקים"
        items = build_retry_items([source_row], profile=TEST_PROFILE)

        payload = build_retry_alert_payload(items[0], {"status": "opened", "evidence": "data/evidence/test.json"}, attempted_at="2026-08-01T12:00:00")
        message = build_message(payload)

        self.assertEqual(payload["kind"], "retry")
        self.assertIn("ניסיון הגשה חוזר", message)
        self.assertIn("תואר בכלכלה", message)
        self.assertNotIn("????", message)
        self.assertNotIn("×", message)

    def test_human_gate_retry_alert_stays_manual(self) -> None:
        items = build_retry_items(
            [
                row(
                    "IAI",
                    "Buyer",
                    "https://jobs.iai.co.il/job/1/",
                    "The form is protected by reCAPTCHA",
                    "96",
                )
            ],
            profile=TEST_PROFILE,
        )

        payload = build_retry_alert_payload(items[0], {"status": "opened"}, attempted_at="2026-08-01T12:00:00")

        self.assertEqual(payload["kind"], "manual")
        self.assertIn("CAPTCHA", payload["blocker"])

    def test_blocked_retry_queue_alert_is_clean_hebrew(self) -> None:
        payload = build_blocked_alert(
            {
                "company": "IAI",
                "title": "קניין/ית רכש",
                "link": "https://example.com",
                "score": 81,
                "fit": "תואר ראשון; ניסיון רכש; Excel; אנגלית גבוהה",
                "location": "אשדוד",
                "site": "IAI Careers",
                "reason": "נדרש reCAPTCHA",
                "next_step": "להשלים ידנית",
            }
        )
        message = build_message(payload)

        self.assertIn("נדרשת הגשה עצמאית", message)
        self.assertIn("תואר ראשון", message)
        self.assertNotIn("????", message)
        self.assertNotIn("×", message)


if __name__ == "__main__":
    unittest.main()
