from __future__ import annotations

import unittest

from src.site_adapters import adapter_for_url, route_submission_failure
from src.submission_failures import AutomationAction, FailureKind, classify_failure


class SubmissionFailureClassifierTests(unittest.TestCase):
    def test_radware_is_security_gate(self) -> None:
        result = classify_failure("AllJobs blocked the browser and direct requests showed Radware", "https://www.alljobs.co.il/Search/UploadSingle.aspx?JobID=1")
        self.assertEqual(result.kind, FailureKind.CAPTCHA_OR_SECURITY)
        self.assertEqual(result.action, AutomationAction.FILL_UNTIL_HUMAN_GATE)
        self.assertTrue(result.requires_human)

    def test_successfactors_login_gets_persistent_session_action(self) -> None:
        result = classify_failure("SuccessFactors requires account creation and the Retype Email field did not accept automation", "https://jobs.dsv.com/job/example")
        self.assertEqual(result.kind, FailureKind.LOGIN_OR_ACCOUNT)
        self.assertEqual(result.action, AutomationAction.RETRY_WITH_PERSISTENT_SESSION)
        self.assertTrue(result.can_improve_with_code)

    def test_jobify_email_code_beats_resolved_mobility_text(self) -> None:
        result = classify_failure(
            "Jobify דורש כניסה באמצעות קוד אימות למייל; הדרישה כוללת ניידות והגעה עצמאית.",
            "https://jobify360.co.il/jobs/example",
        )

        self.assertEqual(result.kind, FailureKind.LOGIN_OR_ACCOUNT)
        self.assertIn(FailureKind.SENSITIVE_FIELD, result.signals)

    def test_invalid_password_login_requires_human_gate(self) -> None:
        result = classify_failure(
            "ניסיון התחברות עם הסיסמה שסופקה נכשל, ונדרש להתחבר/לאפס סיסמה.",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=9812089",
        )

        self.assertEqual(result.kind, FailureKind.LOGIN_OR_ACCOUNT)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)
        self.assertTrue(result.requires_human)

    def test_existing_account_with_failed_password_requires_human_gate(self) -> None:
        result = classify_failure(
            "הסיסמה שסופקה כבר נכשלה והרשמה החזירה שהמייל קיים במערכת.",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=9812089",
        )

        self.assertEqual(result.kind, FailureKind.LOGIN_OR_ACCOUNT)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_marketing_consent_is_not_auto_accepted(self) -> None:
        result = classify_failure("Drushim registration includes third-party marketing consent", "https://www.drushim.co.il/job/1")
        self.assertEqual(result.kind, FailureKind.MARKETING_CONSENT)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)
        self.assertFalse(result.can_improve_with_code)

    def test_linkedin_closed_job_is_do_not_apply(self) -> None:
        result = classify_failure("LinkedIn shows the job is no longer accepting applications", "https://il.linkedin.com/jobs/view/example-1234567890")
        self.assertEqual(result.kind, FailureKind.CLOSED_JOB)
        self.assertEqual(result.action, AutomationAction.DO_NOT_APPLY)

    def test_site_adapter_routes_known_domain(self) -> None:
        adapter = adapter_for_url("https://jobs.iai.co.il/job/76048804/")
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.name, "IAI Careers")

    def test_route_combines_site_and_failure(self) -> None:
        route = route_submission_failure("The form is protected by reCAPTCHA", "https://jobs.iai.co.il/job/76048804/")
        self.assertEqual(route.adapter.name, "IAI Careers")
        self.assertEqual(route.failure.kind, FailureKind.CAPTCHA_OR_SECURITY)
        self.assertEqual(route.recommended_action, AutomationAction.FILL_UNTIL_HUMAN_GATE)

    def test_multiple_signals_are_preserved(self) -> None:
        result = classify_failure("No direct form was found and the role also requires independent arrival by car", "https://jobify360.co.il/jobs/example")
        self.assertIn(FailureKind.NO_DIRECT_FORM, result.signals)
        self.assertIn(FailureKind.SENSITIVE_FIELD, result.signals)

    def test_salary_policy_is_human_gate(self) -> None:
        result = classify_failure("The posting requires numeric salary expectations", "https://www.jobmaster.co.il/jobs/checknum.asp?key=1")
        self.assertEqual(result.kind, FailureKind.SALARY_REQUIRED)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_minimum_salary_numeric_value_is_human_gate(self) -> None:
        result = classify_failure(
            "מסך onboarding של שכר מינימלי עם ערך מספרי 18,000 ₪.",
            "https://jobify360.co.il/ob-salary",
        )

        self.assertEqual(result.kind, FailureKind.SALARY_REQUIRED)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_mandatory_industrial_experience_beats_mobility_text(self) -> None:
        result = classify_failure(
            "קיימת דרישת חובה לניסיון בסביבה תעשייתית יצרנית ובעבודה תפעולית בשטח; ניידות חובה; SAP/ERP יתרון.",
            "https://jobdetails.nestle.com/job/example/1411622433/",
        )

        self.assertEqual(result.kind, FailureKind.EXPERIENCE_AMBIGUITY)
        self.assertIn(FailureKind.SENSITIVE_FIELD, result.signals)
        self.assertIn(FailureKind.UNVERIFIED_SYSTEM_SKILL, result.signals)

    def test_hebrew_minimum_three_years_is_experience_ambiguity(self) -> None:
        result = classify_failure(
            "דרישות: ניסיון של 3 שנים לפחות ברכש כולל מו״מ בארץ ובחו״ל.",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=9842627",
        )

        self.assertEqual(result.kind, FailureKind.EXPERIENCE_AMBIGUITY)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_generated_experience_interpretation_reason_stays_human_gate(self) -> None:
        result = classify_failure(
            "Approval required by submission engine: The requirement depends on how the candidate's experience is interpreted.",
            "https://www.drushim.co.il/job/38010396/c1da841d/",
        )

        self.assertEqual(result.kind, FailureKind.EXPERIENCE_AMBIGUITY)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_up_to_three_years_is_not_blocked_as_experience_ambiguity(self) -> None:
        result = classify_failure(
            "משרה ג׳וניור לבעלי ניסיון עד 3 שנים ברכש, עבודה מול ספקים ו-Excel.",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=1",
        )

        self.assertNotEqual(result.kind, FailureKind.EXPERIENCE_AMBIGUITY)
        self.assertNotIn(FailureKind.EXPERIENCE_AMBIGUITY, result.signals)

    def test_unverified_source_question_is_missing_candidate_fact(self) -> None:
        result = classify_failure(
            "הטופס דורש בחירת מקור פרסום מתוך אפשרויות מוגבלות שלא ניתן לאמת, וכלי העלאת הקובץ נחסם.",
            "https://survey.gov.il/he/misrotashd",
        )

        self.assertEqual(result.kind, FailureKind.MISSING_CANDIDATE_FACT)
        self.assertIn(FailureKind.FORM_AUTOMATION_UNRELIABLE, result.signals)

    def test_english_identity_and_relatives_are_sensitive_fields(self) -> None:
        result = classify_failure("The form requires national ID and relatives-at-company disclosure", "https://survey.gov.il/he/example")
        self.assertEqual(result.kind, FailureKind.SENSITIVE_FIELD)
        self.assertIn(FailureKind.SENSITIVE_FIELD, result.signals)

    def test_previous_application_question_is_missing_candidate_fact(self) -> None:
        result = classify_failure(
            "טופס ההגשה הרשמי דורש תשובה לשאלה האם הגשת מועמדות בעבר אחרי 1/1/2013 לפני שליחה.",
            "https://www.tfaforms.com/4851745?tfa_4776808320092=701Py00000XHZg0",
        )

        self.assertEqual(result.kind, FailureKind.MISSING_CANDIDATE_FACT)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)

    def test_temporary_role_is_policy_gate(self) -> None:
        result = classify_failure(
            "נדרש אישור לפני הגשה: המשרה נראית זמנית או קצרה ודורשת בדיקה לפני הגשה.",
            "https://www.jobmaster.co.il/jobs/checknum.asp?key=9840352",
        )

        self.assertEqual(result.kind, FailureKind.MISSING_CANDIDATE_FACT)
        self.assertEqual(result.action, AutomationAction.HUMAN_APPROVAL_REQUIRED)


if __name__ == "__main__":
    unittest.main()
