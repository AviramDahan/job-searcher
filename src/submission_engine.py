from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Protocol

try:
    from .browser_session import build_session_config, save_evidence
    from .candidate_profile import CandidateProfile, KOREN_DAHAN_PROFILE, assess_candidate_facts, assess_job_candidate_facts
    from .job_records import COMPANY, COVER, CV, DATE, FIT, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, TITLE, job_key, load_rows, write_rows
    from .jobmaster_apply import JobMasterOptions, JobMasterStage, default_cv_path, expected_cv_name, run_jobmaster_application
    from .location_policy import LocationDecision, assess_location
    from .rebuild_summary import render as render_summary
    from .send_job_status_alerts import build_message, send
    from .site_adapters import SiteAdapterProfile, adapter_for_url, route_submission_failure
    from .submission_failures import AutomationAction, FailureKind
except ImportError:
    from browser_session import build_session_config, save_evidence
    from candidate_profile import CandidateProfile, KOREN_DAHAN_PROFILE, assess_candidate_facts, assess_job_candidate_facts
    from job_records import COMPANY, COVER, CV, DATE, FIT, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, TITLE, job_key, load_rows, write_rows
    from jobmaster_apply import JobMasterOptions, JobMasterStage, default_cv_path, expected_cv_name, run_jobmaster_application
    from location_policy import LocationDecision, assess_location
    from rebuild_summary import render as render_summary
    from send_job_status_alerts import build_message, send
    from site_adapters import SiteAdapterProfile, adapter_for_url, route_submission_failure
    from submission_failures import AutomationAction, FailureKind


class SubmissionDecision(str, Enum):
    READY_FOR_AUTO = "ready_for_auto"
    READY_FOR_COMPANY_FALLBACK = "ready_for_company_fallback"
    HUMAN_GATE = "human_gate"
    POLICY_REQUIRED = "policy_required"
    DO_NOT_APPLY = "do_not_apply"
    ALREADY_SUBMITTED = "already_submitted"
    NOT_SUPPORTED = "not_supported"


class SubmissionRunMode(str, Enum):
    PLAN_ONLY = "plan_only"
    EVIDENCE_ONLY = "evidence_only"
    OPEN_BROWSER = "open_browser"
    PREPARE = "prepare"
    SUBMIT = "submit"


class SubmissionRunStatus(str, Enum):
    PLANNED = "planned"
    EVIDENCE_SAVED = "evidence_saved"
    OPENED = "opened"
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    LOGIN_REQUIRED = "login_required"
    VERIFICATION_REQUIRED = "verification_required"
    CV_UNVERIFIED = "cv_unverified"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class SubmissionJob:
    key: str
    score: int
    status: str
    company: str
    title: str
    location: str
    link: str
    requirements: str
    fit: str
    stop_reason: str
    cover: str
    cv: str


@dataclass(frozen=True)
class SubmissionPlan:
    job: SubmissionJob
    site: str
    adapter: str
    decision: str
    action: str
    can_attempt: bool
    requires_human: bool
    reason: str
    next_step: str
    verified_facts: list[str]
    blockers: list[str]


@dataclass(frozen=True)
class SubmissionResult:
    key: str
    site: str
    decision: str
    status: str
    attempted_at: str
    reason: str
    next_step: str
    evidence: str | None = None
    current_url: str | None = None


class SubmissionAdapter(Protocol):
    name: str

    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        ...

    async def run(self, plan: SubmissionPlan, mode: SubmissionRunMode, root: Path) -> SubmissionResult:
        ...


def score_int(value: str) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def row_to_job(row: dict[str, str]) -> SubmissionJob:
    return SubmissionJob(
        key=job_key(row),
        score=score_int(row.get(SCORE, "")),
        status=row.get(STATUS, ""),
        company=row.get(COMPANY, ""),
        title=row.get(TITLE, ""),
        location=row.get(LOCATION, ""),
        link=row.get(LINK, ""),
        requirements=row.get(REQUIREMENTS, ""),
        fit=row.get(FIT, ""),
        stop_reason=row.get(STOP_REASON, ""),
        cover=row.get(COVER, ""),
        cv=row.get(CV, ""),
    )


def _context(job: SubmissionJob) -> str:
    return " ".join(part for part in [job.title, job.company, job.location, job.requirements, job.fit, job.stop_reason] if part)


def _candidate_fact_context(job: SubmissionJob) -> str:
    return " ".join(part for part in [job.title, job.company, job.location, job.requirements, job.fit] if part)


SALARY_CONTEXT_TERMS = (
    "ציפיות שכר",
    "צפיות שכר",
    "שכר",
    "salary expectation",
    "expected salary",
)

COVER_PLACEHOLDER_TERMS = (
    "לא נשלח",
    "לא צורף",
    "נדרש",
    "manual",
    "n/a",
)


def _mentions_salary(text: str) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in SALARY_CONTEXT_TERMS)


def _clean_cover_hint(value: str) -> str:
    clean = " ".join((value or "").split()).strip()
    if not clean or clean in {"-", "--"}:
        return ""
    lowered = clean.lower()
    if any(term.lower() in lowered for term in COVER_PLACEHOLDER_TERMS):
        return ""
    return clean


def _default_cover_letter(job: SubmissionJob, profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> str:
    title = (job.title or "").lower()
    context = _context(job).lower()
    procurement_terms = ("רכש", "קניינ", "buyer", "procurement", "sourcing", "ספק")
    finance_terms = ("כלכל", "תקציב", "בקרה", "אנליסט", "financial", "economist", "budget")

    if any(term in title for term in procurement_terms):
        fit_sentence = (
            "התפקיד מתחבר לניסיון שלי ברכש, בעבודה מול ספקים, בקבלת והשוואת הצעות מחיר, "
            "בניהול משא ומתן ובמעקב אחר הזמנות, אספקות ותשלומים."
        )
    elif any(term in title for term in finance_terms):
        fit_sentence = (
            "התפקיד מתחבר לרקע שלי בכלכלה וניהול, בבנייה ובקרה של תקציבים, "
            "בניתוח פערים ודוחות כספיים, בעבודה עם Excel ובהצגת נתונים להנהלה."
        )
    elif any(term in context for term in procurement_terms):
        fit_sentence = (
            "התפקיד מתחבר לניסיון שלי ברכש, בעבודה מול ספקים, בקבלת והשוואת הצעות מחיר, "
            "בניהול משא ומתן ובמעקב אחר הזמנות, אספקות ותשלומים."
        )
    elif any(term in context for term in finance_terms):
        fit_sentence = (
            "התפקיד מתחבר לרקע שלי בכלכלה וניהול, בבנייה ובקרה של תקציבים, "
            "בניתוח פערים ודוחות כספיים, בעבודה עם Excel ובהצגת נתונים להנהלה."
        )
    else:
        fit_sentence = (
            "התפקיד מתחבר לניסיון שלי בתחומי הרכש, התקציבים והבקרה, "
            "לעבודה מול ממשקים רבים וליכולת לנתח נתונים בצורה מסודרת."
        )

    return (
        f"שלום,\n"
        f"שמי {profile.full_name}, בעלת תואר בכלכלה וניהול וניסיון בתחומי הרכש, התקציבים והבקרה. "
        f"{fit_sentence} אשמח להגיש את מועמדותי לתפקיד ולבחון אפשרות להשתלב בצוות.\n"
        f"תודה,\n"
        f"{profile.full_name}"
    )


def cover_letter_for_application(job: SubmissionJob, profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> str:
    cover = _clean_cover_hint(job.cover) or _default_cover_letter(job, profile)
    if not profile.approved_salary_expectation or not _mentions_salary(_context(job)):
        return cover

    formatted_salary = f"{profile.approved_salary_expectation:,}"
    if _mentions_salary(cover) or str(profile.approved_salary_expectation) in cover or formatted_salary in cover:
        return cover

    salary_note = f"ציפיות השכר שלי הן {formatted_salary} ש\"ח ברוטו, גמיש בהתאם לתפקיד ולתנאים."
    return f"{cover}\n\n{salary_note}" if cover else salary_note


def _candidate_fact_lists(context: str, profile: CandidateProfile) -> tuple[list[str], list[str], bool]:
    assessment = assess_candidate_facts(context, profile=profile)
    verified = [issue.reason for issue in assessment.resolved]
    blockers = [issue.reason for issue in assessment.blockers]
    return verified, blockers, assessment.has_disqualifying_blocker


def _has_explicit_pending_approval(job: SubmissionJob) -> bool:
    reason = (job.stop_reason or "").strip()
    return job.status == PENDING and reason.startswith(("נדרש אישור לפני הגשה", "Approval required by submission engine:"))


UNSUPERSEDABLE_LIVE_FAILURES = {
    FailureKind.CLOSED_JOB,
    FailureKind.EXPERIENCE_AMBIGUITY,
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.WORK_MODEL_UNKNOWN,
}


UNSUPERSEDABLE_STOP_REASON_FAILURES = {
    FailureKind.CLOSED_JOB,
    FailureKind.EXPERIENCE_AMBIGUITY,
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.WORK_MODEL_UNKNOWN,
}


def _can_supersede_generated_pending_approval(job: SubmissionJob, assessment, location_assessment, live_route, historical_route) -> bool:
    if not _has_explicit_pending_approval(job):
        return False
    if assessment.has_disqualifying_blocker or assessment.has_human_blocker:
        return False
    if location_assessment.decision != LocationDecision.IN_SCOPE:
        return False

    historical_signals = set(historical_route.failure.signals or (historical_route.failure.kind,))
    if historical_signals & UNSUPERSEDABLE_STOP_REASON_FAILURES:
        return False

    live_signals = set(live_route.failure.signals or (live_route.failure.kind,))
    return not bool(live_signals & UNSUPERSEDABLE_LIVE_FAILURES)


def _plan_has_active_explicit_pending_approval(plan: SubmissionPlan) -> bool:
    return _has_explicit_pending_approval(plan.job) and plan.reason == plan.job.stop_reason


def _default_decision(
    job: SubmissionJob,
    route_action: AutomationAction,
    route_requires_human: bool,
    has_disqualifying_blocker: bool,
    blockers: list[str],
    explicit_pending_approval: bool,
) -> SubmissionDecision:
    if job.status == SUBMITTED:
        return SubmissionDecision.ALREADY_SUBMITTED
    if job.status == REJECTED:
        return SubmissionDecision.DO_NOT_APPLY
    if job.status == MANUAL_REQUIRED:
        return SubmissionDecision.HUMAN_GATE
    if explicit_pending_approval:
        return SubmissionDecision.POLICY_REQUIRED
    if job.score < 70:
        return SubmissionDecision.DO_NOT_APPLY
    if has_disqualifying_blocker:
        return SubmissionDecision.DO_NOT_APPLY
    if route_action == AutomationAction.DO_NOT_APPLY:
        return SubmissionDecision.DO_NOT_APPLY
    if route_action == AutomationAction.HUMAN_APPROVAL_REQUIRED:
        return SubmissionDecision.POLICY_REQUIRED
    if blockers:
        return SubmissionDecision.POLICY_REQUIRED
    if route_action == AutomationAction.USE_COMPANY_SITE_FALLBACK:
        return SubmissionDecision.READY_FOR_COMPANY_FALLBACK
    if route_requires_human and route_action != AutomationAction.RETRY_WITH_PERSISTENT_SESSION:
        return SubmissionDecision.HUMAN_GATE
    return SubmissionDecision.READY_FOR_AUTO


def _can_attempt(decision: SubmissionDecision) -> bool:
    return decision in {SubmissionDecision.READY_FOR_AUTO, SubmissionDecision.READY_FOR_COMPANY_FALLBACK}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class BrowserPlanningAdapter:
    def __init__(self, profile: SiteAdapterProfile | None = None, name: str | None = None) -> None:
        self.profile = profile
        self.name = name or (profile.name if profile else "Unsupported")

    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        context = _context(job)
        candidate_context = _candidate_fact_context(job)
        location_context = " ".join(part for part in [job.title, job.company, job.requirements, job.cover] if part)
        location_assessment = assess_location(job.location, location_context)
        assessment = assess_job_candidate_facts(candidate_context, job.stop_reason, profile=profile)
        verified_facts = [issue.reason for issue in assessment.resolved]
        blockers = [issue.reason for issue in assessment.blockers if getattr(issue, "code", "") != "work_model_unverified"]
        has_disqualifying_blocker = assessment.has_disqualifying_blocker
        route = route_submission_failure(reason=context, link=job.link, title=job.title, company=job.company)
        live_route = route_submission_failure(reason=candidate_context, link=job.link, title=job.title, company=job.company)
        explicit_pending_approval = _has_explicit_pending_approval(job)
        if _can_supersede_generated_pending_approval(job, assessment, location_assessment, live_route, route):
            route = live_route
            explicit_pending_approval = False
        route_action = route.recommended_action
        route_requires_human = route.requires_human
        resolved_gate_kinds = {issue.kind for issue in assessment.resolved}
        resolved_gate_issue = next((issue for issue in assessment.resolved if issue.kind == route.failure.kind), None)
        if route.failure.kind in resolved_gate_kinds and not blockers:
            route_action = route.adapter.default_action if route.adapter else AutomationAction.RETRY_WITH_PERSISTENT_SESSION
            route_requires_human = False
        adapter_name = route.adapter.name if route.adapter else self.name
        decision = _default_decision(
            job,
            route_action,
            route_requires_human,
            has_disqualifying_blocker,
            blockers,
            explicit_pending_approval,
        )
        if route.adapter is None and decision == SubmissionDecision.READY_FOR_AUTO:
            decision = SubmissionDecision.NOT_SUPPORTED
        if job.status not in {SUBMITTED, REJECTED} and job.score >= 70:
            if location_assessment.decision == LocationDecision.OUT_OF_SCOPE:
                decision = SubmissionDecision.DO_NOT_APPLY
            elif (
                location_assessment.decision == LocationDecision.APPROVAL_REQUIRED
                and decision in {SubmissionDecision.READY_FOR_AUTO, SubmissionDecision.READY_FOR_COMPANY_FALLBACK}
            ):
                decision = SubmissionDecision.POLICY_REQUIRED

        reason = route.failure.reason
        next_step = route.failure.next_step
        if resolved_gate_issue:
            reason = resolved_gate_issue.reason
            next_step = resolved_gate_issue.next_step
        if job.status == SUBMITTED:
            reason = "The tracker already marks this job as submitted."
            next_step = "Do not submit again unless the operator explicitly resets the row."
        elif job.status == REJECTED:
            reason = "The tracker already marks this job as rejected."
            next_step = "Do not attempt this application unless the row is manually restored after a fresh review."
        elif job.score < 70:
            reason = "The fit score is below the minimum submission threshold."
            next_step = "Keep the job rejected or rescore it after reading a live updated posting."
        elif location_assessment.decision == LocationDecision.OUT_OF_SCOPE:
            reason = location_assessment.reason
            next_step = "Do not apply unless the live posting shows an approved target location or a confirmed hybrid model of up to two weekly office visits."
        elif explicit_pending_approval:
            reason = job.stop_reason
            next_step = "Ask the operator for approval or the missing policy-sensitive answer before attempting submission."
        elif location_assessment.decision == LocationDecision.APPROVAL_REQUIRED and decision == SubmissionDecision.POLICY_REQUIRED:
            reason = location_assessment.reason
            next_step = "Ask the operator to approve the distance or work model before attempting submission."
        elif blockers:
            reason = blockers[0]
            next_step = "Ask the operator for the missing or policy-sensitive answer before attempting submission."
        elif has_disqualifying_blocker:
            next_step = "Do not apply unless the live posting proves the disqualifying requirement is not mandatory."
        elif decision == SubmissionDecision.NOT_SUPPORTED:
            reason = "No submission adapter exists for this site yet."
            next_step = "Inspect the site once, then add an adapter profile and selectors."
        elif decision == SubmissionDecision.READY_FOR_AUTO:
            next_step = "Open a persistent browser session, verify login/CV state, fill safe fields, and submit only after response confirmation."

        return SubmissionPlan(
            job=job,
            site=adapter_name,
            adapter=self.name,
            decision=decision.value,
            action=route_action.value,
            can_attempt=_can_attempt(decision),
            requires_human=decision in {SubmissionDecision.HUMAN_GATE, SubmissionDecision.POLICY_REQUIRED},
            reason=reason,
            next_step=next_step,
            verified_facts=verified_facts,
            blockers=blockers,
        )

    async def run(self, plan: SubmissionPlan, mode: SubmissionRunMode, root: Path) -> SubmissionResult:
        if mode == SubmissionRunMode.PLAN_ONLY:
            return _result(plan, SubmissionRunStatus.PLANNED)
        if not plan.can_attempt and mode != SubmissionRunMode.EVIDENCE_ONLY:
            return _result(plan, SubmissionRunStatus.BLOCKED)
        if mode == SubmissionRunMode.EVIDENCE_ONLY:
            config = build_session_config(plan.job.link, root=root, site_name=plan.site)
            evidence = save_evidence(
                config=config,
                job_key=plan.job.key,
                url=plan.job.link,
                stage=f"engine-{plan.decision}",
                reason=plan.reason,
                metadata={"plan": asdict(plan)},
            )
            return _result(plan, SubmissionRunStatus.EVIDENCE_SAVED, evidence=evidence.metadata_path)
        if mode == SubmissionRunMode.OPEN_BROWSER:
            return await _open_browser(plan, root)
        return _result(plan, SubmissionRunStatus.FAILED, reason="Unsupported run mode.")


class JobifySubmissionAdapter(BrowserPlanningAdapter):
    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        plan = super().plan(job, profile)
        if plan.decision in {SubmissionDecision.ALREADY_SUBMITTED.value, SubmissionDecision.DO_NOT_APPLY.value}:
            return plan
        if "closed" in plan.reason.lower() or "סגור" in plan.reason:
            return _replace_plan(
                plan,
                decision=SubmissionDecision.DO_NOT_APPLY,
                can_attempt=False,
                requires_human=False,
                next_step="Do not retry this Jobify posting unless the live page becomes open again.",
            )
        if plan.decision not in {SubmissionDecision.READY_FOR_AUTO.value, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value}:
            return plan
        return _replace_plan(
            plan,
            decision=SubmissionDecision.READY_FOR_COMPANY_FALLBACK,
            can_attempt=True,
            requires_human=False,
            next_step="Use Jobify as source discovery, then search and submit through the official company career page when available.",
        )


class LinkedInSubmissionAdapter(BrowserPlanningAdapter):
    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        plan = super().plan(job, profile)
        if plan.decision in {SubmissionDecision.ALREADY_SUBMITTED.value, SubmissionDecision.DO_NOT_APPLY.value}:
            return plan
        if plan.decision not in {SubmissionDecision.READY_FOR_AUTO.value, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value}:
            return plan
        return _replace_plan(
            plan,
            decision=SubmissionDecision.READY_FOR_COMPANY_FALLBACK,
            can_attempt=True,
            requires_human=False,
            next_step="Use the authenticated LinkedIn session to identify Easy Apply or the external company URL; prefer the official company form.",
        )


class JobnetSubmissionAdapter(BrowserPlanningAdapter):
    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        plan = super().plan(job, profile)
        if plan.decision in {SubmissionDecision.ALREADY_SUBMITTED.value, SubmissionDecision.DO_NOT_APPLY.value}:
            return plan
        if plan.decision not in {SubmissionDecision.READY_FOR_AUTO.value, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value}:
            return plan
        return _replace_plan(
            plan,
            decision=SubmissionDecision.NOT_SUPPORTED,
            can_attempt=False,
            requires_human=True,
            reason="Jobnet has a direct SendCv form, but the auto-submit adapter is not yet validated for mandatory questions, terms, email confirmation, and success evidence.",
            next_step="Send as manual handoff or inspect the SendCv form in a persistent browser before adding a safe Jobnet submit adapter.",
        )


class DrushimSubmissionAdapter(BrowserPlanningAdapter):
    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        plan = super().plan(job, profile)
        if plan.decision in {SubmissionDecision.ALREADY_SUBMITTED.value, SubmissionDecision.DO_NOT_APPLY.value}:
            return plan
        if plan.decision == SubmissionDecision.HUMAN_GATE.value:
            return plan
        if plan.blockers:
            return plan
        if _plan_has_active_explicit_pending_approval(plan):
            return _replace_plan(
                plan,
                decision=SubmissionDecision.POLICY_REQUIRED,
                can_attempt=False,
                requires_human=True,
                reason=plan.job.stop_reason,
                next_step="Ask the operator for approval or the missing policy-sensitive answer before attempting submission.",
            )
        fallback_reason = (
            plan.decision in {SubmissionDecision.READY_FOR_AUTO.value, SubmissionDecision.READY_FOR_COMPANY_FALLBACK.value}
            or "marketing" in plan.reason.lower()
            or "third-party" in plan.reason.lower()
            or "verified in the candidate profile" in plan.reason.lower()
            or "blocker does not match a known failure pattern" in plan.reason.lower()
            or "login" in plan.reason.lower()
            or "account state" in plan.reason.lower()
        )
        if plan.decision == SubmissionDecision.POLICY_REQUIRED.value and not fallback_reason:
            return plan
        if not fallback_reason:
            return plan
        return _replace_plan(
            plan,
            decision=SubmissionDecision.READY_FOR_COMPANY_FALLBACK,
            can_attempt=True,
            requires_human=False,
            reason="Drushim is approved as a discovery source, but no safe submit adapter exists yet for its application form.",
            next_step="Use Drushim to identify the employer and prefer an official company career form; if no direct form exists, send a manual handoff.",
        )


class JobMasterSubmissionAdapter(BrowserPlanningAdapter):
    def plan(self, job: SubmissionJob, profile: CandidateProfile) -> SubmissionPlan:
        plan = super().plan(job, profile)
        if plan.can_attempt:
            return _replace_plan(
                plan,
                next_step="Open JobMaster with the persistent profile, verify the active CV is the current PDF, fill the tailored message if available, submit, and confirm the success banner.",
            )
        return plan

    async def run(self, plan: SubmissionPlan, mode: SubmissionRunMode, root: Path) -> SubmissionResult:
        if mode in {SubmissionRunMode.PLAN_ONLY, SubmissionRunMode.EVIDENCE_ONLY, SubmissionRunMode.OPEN_BROWSER}:
            return await super().run(plan, mode, root)
        if not plan.can_attempt:
            return _result(plan, SubmissionRunStatus.BLOCKED)

        cv_path = default_cv_path()
        expected = expected_cv_name(cv_path, plan.job.cv)
        result = await run_jobmaster_application(
            JobMasterOptions(
                job_url=plan.job.link,
                job_key=plan.job.key,
                cover_letter=cover_letter_for_application(plan.job),
                cv_path=cv_path,
                expected_cv_filename=expected,
                email=os.environ.get("JOBMASTER_EMAIL", ""),
                password=os.environ.get("JOBMASTER_PASSWORD", ""),
                submit=mode == SubmissionRunMode.SUBMIT,
                root=root,
                headless=os.environ.get("JOBMASTER_HEADLESS", "").lower() in {"1", "true", "yes"},
            )
        )
        status_map = {
            JobMasterStage.FORM_PREPARED.value: SubmissionRunStatus.PREPARED,
            JobMasterStage.SUBMITTED.value: SubmissionRunStatus.SUBMITTED,
            JobMasterStage.LOGIN_REQUIRED.value: SubmissionRunStatus.LOGIN_REQUIRED,
            JobMasterStage.VERIFICATION_REQUIRED.value: SubmissionRunStatus.VERIFICATION_REQUIRED,
            JobMasterStage.CV_UNVERIFIED.value: SubmissionRunStatus.CV_UNVERIFIED,
        }
        status = status_map.get(result.stage, SubmissionRunStatus.FAILED if result.stage.endswith("failed") or result.stage == "error" else SubmissionRunStatus.BLOCKED)
        return _result(
            plan,
            status,
            reason=result.reason,
            next_step=result.next_step,
            evidence=result.evidence,
            current_url=result.current_url,
        )


def _replace_plan(
    plan: SubmissionPlan,
    decision: SubmissionDecision | None = None,
    can_attempt: bool | None = None,
    requires_human: bool | None = None,
    reason: str | None = None,
    next_step: str | None = None,
) -> SubmissionPlan:
    return SubmissionPlan(
        job=plan.job,
        site=plan.site,
        adapter=plan.adapter,
        decision=(decision.value if decision else plan.decision),
        action=plan.action,
        can_attempt=plan.can_attempt if can_attempt is None else can_attempt,
        requires_human=plan.requires_human if requires_human is None else requires_human,
        reason=plan.reason if reason is None else reason,
        next_step=plan.next_step if next_step is None else next_step,
        verified_facts=plan.verified_facts,
        blockers=plan.blockers,
    )


def _result(
    plan: SubmissionPlan,
    status: SubmissionRunStatus,
    reason: str | None = None,
    next_step: str | None = None,
    evidence: str | None = None,
    current_url: str | None = None,
) -> SubmissionResult:
    return SubmissionResult(
        key=plan.job.key,
        site=plan.site,
        decision=plan.decision,
        status=status.value,
        attempted_at=_now(),
        reason=reason or plan.reason,
        next_step=next_step or plan.next_step,
        evidence=str(evidence) if evidence else None,
        current_url=current_url,
    )


async def _open_browser(plan: SubmissionPlan, root: Path) -> SubmissionResult:
    try:
        from .browser_session import launch_persistent_context  # type: ignore
    except ImportError:
        from browser_session import launch_persistent_context  # type: ignore

    config = build_session_config(plan.job.link, root=root, site_name=plan.site)
    playwright, context = await launch_persistent_context(config)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(plan.job.link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        evidence = save_evidence(
            config=config,
            job_key=plan.job.key,
            url=plan.job.link,
            stage="engine-opened",
            reason=plan.reason,
            html=await page.content(),
            screenshot_bytes=await page.screenshot(full_page=True),
            metadata={"plan": asdict(plan), "title": await page.title(), "current_url": page.url},
        )
        return _result(plan, SubmissionRunStatus.OPENED, evidence=evidence.metadata_path, current_url=page.url)
    finally:
        await context.close()
        await playwright.stop()


def adapter_for_job(job: SubmissionJob) -> SubmissionAdapter:
    profile = adapter_for_url(job.link)
    if profile and profile.name == "Jobify":
        return JobifySubmissionAdapter(profile)
    if profile and profile.name == "LinkedIn":
        return LinkedInSubmissionAdapter(profile)
    if profile and profile.name == "Jobnet":
        return JobnetSubmissionAdapter(profile)
    if profile and profile.name == "Drushim":
        return DrushimSubmissionAdapter(profile)
    if profile and profile.name == "JobMaster":
        return JobMasterSubmissionAdapter(profile)
    return BrowserPlanningAdapter(profile=profile)


def plan_jobs(
    rows: list[dict[str, str]],
    profile: CandidateProfile = KOREN_DAHAN_PROFILE,
    min_score: int = 70,
    include_submitted: bool = False,
) -> list[SubmissionPlan]:
    plans = []
    for row in rows:
        job = row_to_job(row)
        if job.score < min_score:
            continue
        if job.status == SUBMITTED and not include_submitted:
            continue
        adapter = adapter_for_job(job)
        plans.append(adapter.plan(job, profile))
    return sorted(plans, key=lambda plan: (not plan.can_attempt, -plan.job.score, plan.site, plan.job.title))


async def run_plan(plan: SubmissionPlan, mode: SubmissionRunMode, root: Path = Path(".")) -> SubmissionResult:
    adapter = adapter_for_job(plan.job)
    return await adapter.run(plan, mode, root)


def supports_run_mode(plan: SubmissionPlan, mode: SubmissionRunMode) -> bool:
    if not plan.can_attempt:
        return False
    if mode in {SubmissionRunMode.PLAN_ONLY, SubmissionRunMode.EVIDENCE_ONLY, SubmissionRunMode.OPEN_BROWSER}:
        return True
    if mode in {SubmissionRunMode.PREPARE, SubmissionRunMode.SUBMIT}:
        return plan.site == "JobMaster" and plan.decision == SubmissionDecision.READY_FOR_AUTO.value
    return False


def select_next_plan(plans: list[SubmissionPlan], mode: SubmissionRunMode) -> SubmissionPlan | None:
    return next((plan for plan in plans if supports_run_mode(plan, mode)), None)


def render_markdown(plans: list[SubmissionPlan]) -> str:
    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.decision] = counts.get(plan.decision, 0) + 1

    lines = [
        "# Submission Engine Plan",
        "",
        f"Generated: {_now()}",
        "",
        "## Counts",
        "",
    ]
    for decision, count in sorted(counts.items()):
        lines.append(f"- `{decision}`: {count}")

    for decision in [item.value for item in SubmissionDecision]:
        group = [plan for plan in plans if plan.decision == decision]
        if not group:
            continue
        lines.extend(["", f"## {decision}"])
        for plan in group:
            lines.append(f"- {plan.job.score}/100 - {plan.job.company} - [{plan.job.title}]({plan.job.link}) - {plan.site}")
            lines.append(f"  Key: `{plan.job.key}`")
            lines.append(f"  Action: `{plan.action}`")
            lines.append(f"  Reason: {plan.reason}")
            lines.append(f"  Next: {plan.next_step}")
    return "\n".join(lines) + "\n"


def write_outputs(plans: list[SubmissionPlan], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps([asdict(plan) for plan in plans], ensure_ascii=False, indent=2), encoding="utf-8-sig")
    md_path.write_text(render_markdown(plans), encoding="utf-8")


def parse_summary_scanned_count(path: Path, default: int) -> int:
    if not path.exists():
        return default
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("- מספר המשרות שנסרקו:"):
            digits = "".join(ch for ch in line.split(":", 1)[1] if ch.isdigit())
            return int(digits) if digits else default
    return default


def rebuild_summary_file(csv_path: Path, summary_path: Path, telegram_alerts: int = 0) -> None:
    rows = load_rows(csv_path)
    scanned = parse_summary_scanned_count(summary_path, default=len(rows))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(render_summary(rows, scanned, telegram_alerts, "Asia/Jerusalem"), encoding="utf-8-sig")


def record_submission_success(csv_path: Path, plan: SubmissionPlan, result: SubmissionResult, cv_filename: str = "") -> bool:
    rows = load_rows(csv_path)
    changed = False
    today = result.attempted_at.split("T", 1)[0]
    for row in rows:
        if job_key(row) != plan.job.key:
            continue
        row[DATE] = today
        row[STATUS] = SUBMITTED
        row[STOP_REASON] = f"הוגש בהצלחה דרך JobMaster adapter; evidence: {result.evidence or ''}"
        if cv_filename:
            row[CV] = cv_filename
        changed = True
        break
    if changed:
        write_rows(csv_path, rows)
    return changed


def build_submitted_alert_payload(plan: SubmissionPlan, result: SubmissionResult) -> dict:
    return {
        "kind": "submitted",
        "submitted_at": result.attempted_at,
        "company": plan.job.company,
        "title": plan.job.title,
        "score": plan.job.score,
        "link": plan.job.link,
        "matched_requirements": plan.job.fit or plan.job.requirements,
        "company_info": f"מיקום: {plan.job.location}; מקור: {plan.site}",
    }


def notify_submission(plan: SubmissionPlan, result: SubmissionResult) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"sent": False, "reason": "telegram_env_missing"}
    response = send(token, chat_id, build_message(build_submitted_alert_payload(plan, result)))
    return {
        "sent": True,
        "ok": response.get("ok", False),
        "message_id": response.get("result", {}).get("message_id"),
        "migrated_to_chat_id": response.get("_migrated_to_chat_id"),
    }


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan and operate job submission attempts through site adapters.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--json", type=Path, default=Path("outputs/submission_engine_plan.json"))
    parser.add_argument("--md", type=Path, default=Path("outputs/submission_engine_plan.md"))
    parser.add_argument("--min-score", type=int, default=70)
    parser.add_argument("--include-submitted", action="store_true")
    parser.add_argument("--run-next", choices=[mode.value for mode in SubmissionRunMode])
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--notify", action="store_true", help="Send Telegram after a successful submit run.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    rows = load_rows(args.csv)
    plans = plan_jobs(rows, min_score=args.min_score, include_submitted=args.include_submitted)
    write_outputs(plans, args.json, args.md)

    result = None
    tracker_updated = False
    telegram = None
    if args.run_next:
        import asyncio

        run_mode = SubmissionRunMode(args.run_next)
        runnable = select_next_plan(plans, run_mode)
        if runnable:
            result_obj = asyncio.run(run_plan(runnable, run_mode, args.root))
            result = asdict(result_obj)
            if result_obj.status == SubmissionRunStatus.SUBMITTED.value:
                tracker_updated = record_submission_success(args.csv, runnable, result_obj, cv_filename=default_cv_path().name if default_cv_path() else "")
                rebuild_summary_file(args.csv, args.summary, telegram_alerts=1 if args.notify else 0)
                if args.notify:
                    telegram = notify_submission(runnable, result_obj)

    print_json(
        {
            "plans": len(plans),
            "runnable": len([plan for plan in plans if plan.can_attempt]),
            "mode_runnable": len([plan for plan in plans if supports_run_mode(plan, SubmissionRunMode(args.run_next))]) if args.run_next else None,
            "json": str(args.json),
            "md": str(args.md),
            "result": result,
            "tracker_updated": tracker_updated,
            "telegram": telegram,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
