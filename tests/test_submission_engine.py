from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.candidate_profile import CandidateProfile, SystemSkillFact
from src.job_records import COMPANY, COVER, FIT, LINK, LOCATION, MANUAL_REQUIRED, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, TITLE
from src.submission_engine import (
    SubmissionDecision,
    SubmissionRunMode,
    SubmissionRunStatus,
    adapter_for_job,
    cover_letter_for_application,
    plan_jobs,
    row_to_job,
    run_plan,
    select_next_plan,
)


def profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Candidate",
        national_id=None,
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
            SystemSkillFact("Canva", ("canva",), None),
            SystemSkillFact("ChatGPT", ("chatgpt", "chat gpt"), None),
        ),
    )


def row(**overrides: str) -> dict[str, str]:
    base = {
        COMPANY: "Acme",
        TITLE: "Procurement Specialist",
        LOCATION: "Sderot",
        LINK: "https://www.jobmaster.co.il/jobs/checknum.asp?key=111",
        SCORE: "88",
        REQUIREMENTS: "Procurement, suppliers, quotes, Excel",
        FIT: "Procurement and supplier experience",
        STATUS: "נדרש אישור",
        STOP_REASON: "",
    }
    base.update(overrides)
    return base


class SubmissionEngineTests(unittest.TestCase):
    def test_jobmaster_pending_row_is_ready_for_auto_plan(self) -> None:
        plans = plan_jobs([row()], profile=profile(), min_score=70)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].site, "JobMaster")
        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_AUTO.value)
        self.assertTrue(plans[0].can_attempt)

    def test_explicit_pending_approval_blocks_drushim_company_fallback(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://www.drushim.co.il/job/37978704/213d6a45/",
                        STOP_REASON: "נדרש אישור לפני הגשה: המיקום עובר למודיעין ולא מופיע מודל היברידי מאושר.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertTrue(plans[0].requires_human)

    def test_synced_pending_approval_blocks_jobmaster_auto_submission(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        STOP_REASON: "Approval required by submission engine: requires 3 years of experience. Next: ask operator.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertTrue(plans[0].requires_human)

    def test_far_location_policy_overrides_old_pending_approval_reason(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "ראשון לציון",
                        STOP_REASON: "Approval required by submission engine: old secondary-location approval needed.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertIn("רחוק משדרות", plans[0].reason)

    def test_dashboard_approved_location_allows_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preferences_path = Path(tmp) / "location_preferences.json"
            preferences_path.write_text(
                json.dumps(
                    {
                        "location_preferences": {
                            "approved_locations": [
                                {"key": "rehovot", "label": "רחובות", "terms": ["רחובות", "rehovot"], "approved": True}
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JOB_SEARCH_LOCATION_PREFERENCES": str(preferences_path)}, clear=False):
                plans = plan_jobs([row(**{LOCATION: "רחובות"})], profile=profile(), min_score=70)

        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_AUTO.value)
        self.assertTrue(plans[0].can_attempt)

    def test_salary_requirement_adds_approved_salary_to_cover_letter(self) -> None:
        job = row_to_job(
            row(
                **{
                    REQUIREMENTS: "Please include salary expectations.",
                    COVER: "Hello, I would like to apply.",
                }
            )
        )

        cover = cover_letter_for_application(job, profile=profile())

        self.assertIn("13,000", cover)
        self.assertIn("Hello, I would like to apply.", cover)

    def test_cover_letter_placeholder_generates_human_message(self) -> None:
        job = row_to_job(
            row(
                **{
                    TITLE: "Economist",
                    REQUIREMENTS: "Budget control and Excel analysis.",
                    COVER: "לא נשלח",
                }
            )
        )

        cover = cover_letter_for_application(job, profile=profile())

        self.assertNotIn("לא נשלח", cover)
        self.assertIn("בעלת תואר בכלכלה וניהול", cover)
        self.assertIn("Excel", cover)

    def test_hybrid_policy_text_does_not_resolve_missing_office_days(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "Tel Aviv - hybrid",
                        REQUIREMENTS: "Hybrid role from Tel Aviv.",
                        STOP_REASON: "Office days not specified. Search policy allows national hybrid only up to two office days.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_hybrid_up_to_two_days_matches_policy(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "Tel Aviv - hybrid",
                        REQUIREMENTS: "Hybrid role with up to two office days per week.",
                        STOP_REASON: "",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_AUTO.value)
        self.assertTrue(plans[0].can_attempt)

    def test_far_location_blocks_jobmaster_auto_submission(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "Haifa",
                        REQUIREMENTS: "Procurement, suppliers, quotes, Excel",
                        STOP_REASON: "",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertIn("המיקום", plans[0].reason)

    def test_generated_stop_reason_does_not_make_far_location_hybrid_safe(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "כוכב יאיר צור יגאל",
                        REQUIREMENTS: "תואר ראשון בכלכלה, Excel וניתוח דוחות.",
                        STOP_REASON: "נדרש אישור לפני הגשה: המשרה היברידית, אך לא מופיע שמספר ההגעות למשרד הוא עד פעמיים בשבוע.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)

    def test_at_least_two_office_days_is_not_auto_approved_hybrid(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LOCATION: "Tel Aviv - hybrid",
                        REQUIREMENTS: "Hybrid role with at least two office days per week.",
                        STOP_REASON: "",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_required_experience_not_explicit_in_cv_blocks_submission(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        STOP_REASON: "Required construction procurement experience is not explicit in CV.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_unverified_canva_chatgpt_requirement_blocks_submission(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        REQUIREMENTS: "High proficiency with Office, Canva and ChatGPT.",
                        STOP_REASON: "",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertTrue(any("Canva" in blocker or "ChatGPT" in blocker for blocker in plans[0].blockers))

    def test_linkedin_prefers_company_fallback(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://www.linkedin.com/jobs/view/procurement-buyer-at-example-4444111111",
                        STOP_REASON: "External apply source.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].site, "LinkedIn")
        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value)
        self.assertTrue(plans[0].can_attempt)

    def test_drushim_uses_company_fallback_not_direct_submit(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://www.drushim.co.il/job/37979255/1959bdf9/",
                        STOP_REASON: "Registration requires third-party marketing consent",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].site, "Drushim")
        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value)
        self.assertTrue(plans[0].can_attempt)

    def test_jobnet_is_not_marked_auto_until_submit_adapter_exists(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://www.jobnet.co.il/jobs?positionid=13300382",
                        STOP_REASON: "",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].site, "Jobnet")
        self.assertEqual(plans[0].decision, SubmissionDecision.NOT_SUPPORTED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_linkedin_captcha_gate_is_not_forced_to_company_fallback(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        STATUS: MANUAL_REQUIRED,
                        LINK: "https://www.linkedin.com/jobs/view/procurement-buyer-at-example-4444111111",
                        STOP_REASON: "Manual gate: LinkedIn application requires CAPTCHA/reCAPTCHA.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].site, "LinkedIn")
        self.assertEqual(plans[0].decision, SubmissionDecision.HUMAN_GATE.value)
        self.assertFalse(plans[0].can_attempt)
        self.assertTrue(plans[0].requires_human)

    def test_manual_required_row_is_never_marked_runnable(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        STATUS: MANUAL_REQUIRED,
                        LINK: "https://www.drushim.co.il/job/37905896/3d25ce42/",
                        STOP_REASON: "נדרשת הגשה ידנית דרך Drushim.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.HUMAN_GATE.value)
        self.assertFalse(plans[0].can_attempt)

    def test_jobify_policy_blocker_is_not_forced_to_company_fallback(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://jobify360.co.il/jobs/example-id",
                        REQUIREMENTS: "Canva required, procurement and suppliers.",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].site, "Jobify")
        self.assertEqual(plans[0].decision, SubmissionDecision.POLICY_REQUIRED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_submit_mode_selects_real_submit_adapter_not_company_fallback(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        LINK: "https://jobify360.co.il/jobs/example-id",
                        SCORE: "95",
                        COMPANY: "Jobify Company",
                    }
                ),
                row(
                    **{
                        LINK: "https://www.jobmaster.co.il/jobs/checknum.asp?key=222",
                        SCORE: "80",
                        COMPANY: "JobMaster Company",
                    }
                ),
            ],
            profile=profile(),
            min_score=70,
        )

        selected = select_next_plan(plans, SubmissionRunMode.SUBMIT)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.site, "JobMaster")

    def test_submitted_row_is_not_planned_unless_requested(self) -> None:
        self.assertEqual(plan_jobs([row(**{STATUS: SUBMITTED})], profile=profile()), [])

        plans = plan_jobs([row(**{STATUS: SUBMITTED})], profile=profile(), include_submitted=True)

        self.assertEqual(plans[0].decision, SubmissionDecision.ALREADY_SUBMITTED.value)
        self.assertFalse(plans[0].can_attempt)

    def test_rejected_high_score_row_is_never_attempted(self) -> None:
        plans = plan_jobs([row(**{STATUS: REJECTED, SCORE: "92"})], profile=profile(), min_score=70)

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)

    def test_rejected_jobify_high_score_row_is_never_attempted(self) -> None:
        plans = plan_jobs(
            [
                row(
                    **{
                        STATUS: REJECTED,
                        SCORE: "92",
                        LINK: "https://jobify360.co.il/jobs/example-id",
                    }
                )
            ],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)

    def test_required_denied_system_skill_blocks_submission(self) -> None:
        plans = plan_jobs(
            [row(**{REQUIREMENTS: "ERP חובה, procurement and suppliers", FIT: "Procurement background"})],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.DO_NOT_APPLY.value)
        self.assertFalse(plans[0].can_attempt)

    def test_approved_numeric_salary_does_not_block_jobmaster(self) -> None:
        plans = plan_jobs(
            [row(**{STOP_REASON: "The form asks for expected salary.", REQUIREMENTS: "Procurement and Excel"})],
            profile=profile(),
            min_score=70,
        )

        self.assertEqual(plans[0].decision, SubmissionDecision.READY_FOR_AUTO.value)
        self.assertTrue(plans[0].can_attempt)
        self.assertIn("approved", plans[0].reason)

    def test_evidence_only_run_saves_metadata_without_browser(self) -> None:
        plans = plan_jobs([row()], profile=profile(), min_score=70)
        with tempfile.TemporaryDirectory() as tmp:
            result = __import__("asyncio").run(run_plan(plans[0], SubmissionRunMode.EVIDENCE_ONLY, Path(tmp)))
            self.assertEqual(result.status, SubmissionRunStatus.EVIDENCE_SAVED.value)
            self.assertIsNotNone(result.evidence)
            self.assertTrue(Path(str(result.evidence)).exists())

    def test_adapter_for_unknown_site_is_unsupported_adapter(self) -> None:
        job = row_to_job(row(**{LINK: "https://unknown.example/jobs/1"}))

        self.assertEqual(adapter_for_job(job).name, "Unsupported")


if __name__ == "__main__":
    unittest.main()
