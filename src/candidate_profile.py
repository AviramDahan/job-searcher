from __future__ import annotations

import re
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    from .submission_failures import FailureKind
except ImportError:
    from submission_failures import FailureKind


class FactIssueSeverity(str, Enum):
    RESOLVED = "resolved"
    HUMAN_REQUIRED = "human_required"
    DO_NOT_APPLY = "do_not_apply"


@dataclass(frozen=True)
class SystemSkillFact:
    name: str
    aliases: tuple[str, ...]
    has_experience: bool | None


@dataclass(frozen=True)
class CandidateProfile:
    full_name: str
    national_id: str | None
    has_relatives_at_company: bool | None
    has_driving_license: bool | None
    has_car: bool | None
    can_arrive_independently: bool | None
    marketing_consent_approved: bool | None
    approved_salary_expectation: int | None
    system_skills: tuple[SystemSkillFact, ...]


@dataclass(frozen=True)
class CandidateFactIssue:
    kind: FailureKind
    code: str
    label: str
    severity: FactIssueSeverity
    reason: str
    next_step: str


@dataclass(frozen=True)
class CandidateFactAssessment:
    issues: tuple[CandidateFactIssue, ...]

    @property
    def resolved(self) -> tuple[CandidateFactIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == FactIssueSeverity.RESOLVED)

    @property
    def blockers(self) -> tuple[CandidateFactIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity != FactIssueSeverity.RESOLVED)

    @property
    def has_disqualifying_blocker(self) -> bool:
        return any(issue.severity == FactIssueSeverity.DO_NOT_APPLY for issue in self.issues)

    @property
    def has_human_blocker(self) -> bool:
        return any(issue.severity == FactIssueSeverity.HUMAN_REQUIRED for issue in self.issues)

    @property
    def first_blocker(self) -> CandidateFactIssue | None:
        for severity in (FactIssueSeverity.DO_NOT_APPLY, FactIssueSeverity.HUMAN_REQUIRED):
            for issue in self.issues:
                if issue.severity == severity:
                    return issue
        return None


STOP_REASON_FACT_KINDS = {
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MARKETING_CONSENT,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.SALARY_REQUIRED,
    FailureKind.SENSITIVE_FIELD,
}


def merge_candidate_fact_assessments(*assessments: CandidateFactAssessment) -> CandidateFactAssessment:
    issues: list[CandidateFactIssue] = []
    seen: set[tuple[str, FactIssueSeverity]] = set()
    for assessment in assessments:
        for issue in assessment.issues:
            key = (issue.code, issue.severity)
            if key in seen:
                continue
            seen.add(key)
            issues.append(issue)
    return CandidateFactAssessment(tuple(issues))


def assess_job_candidate_facts(
    source_text: str,
    stop_reason: str = "",
    profile: CandidateProfile = None,
) -> CandidateFactAssessment:
    active_profile = profile or KOREN_DAHAN_PROFILE
    source_assessment = assess_candidate_facts(source_text, profile=active_profile)
    if not stop_reason:
        return source_assessment

    stop_assessment = assess_candidate_facts(stop_reason, profile=active_profile)
    stop_fact_issues = [issue for issue in stop_assessment.issues if issue.kind in STOP_REASON_FACT_KINDS]
    return merge_candidate_fact_assessments(source_assessment, CandidateFactAssessment(tuple(stop_fact_issues)))


def default_system_skills() -> tuple[SystemSkillFact, ...]:
    return (
        SystemSkillFact("SAP", ("sap",), False),
        SystemSkillFact("ERP", ("erp",), False),
        SystemSkillFact("MRP", ("mrp",), False),
        SystemSkillFact("Priority", ("priority", "פריוריטי"), None),
        SystemSkillFact("Power BI", ("power bi", "מערכת bi"), None),
        SystemSkillFact("MS Project", ("ms project",), None),
        SystemSkillFact("Gantt", ("gantt", "גאנט", "גאנטים"), None),
        SystemSkillFact("Nibit", ("nibit",), None),
        SystemSkillFact("חשבשבת", ("חשבשבת",), None),
        SystemSkillFact("Canva", ("canva",), None),
        SystemSkillFact("ChatGPT", ("chatgpt", "chat gpt"), None),
    )


def parse_optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "כן"}:
        return True
    if normalized in {"0", "false", "no", "n", "לא"}:
        return False
    return None


def parse_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


def load_profile_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def load_candidate_profile(path: Path | None = None) -> CandidateProfile:
    profile_path = path or Path(os.environ.get("CANDIDATE_PROFILE_PATH", "data/private/candidate_profile.local.json"))
    payload = load_profile_payload(profile_path)
    system_overrides = payload.get("system_skills", {})
    if not isinstance(system_overrides, dict):
        system_overrides = {}

    skills = []
    for skill in default_system_skills():
        override = system_overrides.get(skill.name)
        skills.append(
            SystemSkillFact(
                name=skill.name,
                aliases=skill.aliases,
                has_experience=parse_optional_bool(override) if skill.name in system_overrides else skill.has_experience,
            )
        )

    national_id = os.environ.get("CANDIDATE_NATIONAL_ID") or payload.get("national_id")
    relatives = os.environ.get("CANDIDATE_HAS_RELATIVES_AT_COMPANY")
    relatives_value = parse_optional_bool(relatives) if relatives is not None else parse_optional_bool(payload.get("has_relatives_at_company"))
    driving_license = os.environ.get("CANDIDATE_HAS_DRIVING_LICENSE")
    driving_license_value = (
        parse_optional_bool(driving_license) if driving_license is not None else parse_optional_bool(payload.get("has_driving_license"))
    )
    car = os.environ.get("CANDIDATE_HAS_CAR")
    car_value = parse_optional_bool(car) if car is not None else parse_optional_bool(payload.get("has_car"))
    independent_arrival = os.environ.get("CANDIDATE_CAN_ARRIVE_INDEPENDENTLY")
    independent_arrival_value = (
        parse_optional_bool(independent_arrival)
        if independent_arrival is not None
        else parse_optional_bool(payload.get("can_arrive_independently"))
    )
    marketing_consent = os.environ.get("CANDIDATE_MARKETING_CONSENT_APPROVED")
    marketing_consent_value = (
        parse_optional_bool(marketing_consent)
        if marketing_consent is not None
        else parse_optional_bool(payload.get("marketing_consent_approved"))
    )
    salary = os.environ.get("CANDIDATE_APPROVED_SALARY_EXPECTATION")
    salary_value = parse_optional_int(salary) if salary is not None else parse_optional_int(payload.get("approved_salary_expectation"))
    return CandidateProfile(
        full_name=str(payload.get("full_name") or os.environ.get("CANDIDATE_FULL_NAME") or "קורן דהן"),
        national_id=str(national_id).strip() if national_id else None,
        has_relatives_at_company=relatives_value,
        has_driving_license=driving_license_value,
        has_car=car_value,
        can_arrive_independently=independent_arrival_value,
        marketing_consent_approved=marketing_consent_value,
        approved_salary_expectation=salary_value,
        system_skills=tuple(skills),
    )


KOREN_DAHAN_PROFILE = load_candidate_profile()


ID_TERMS = (
    "תעודת זהות",
    "מספר תעודת",
    "מספר זהות",
    "identity number",
    "id number",
    "national id",
)

RELATIVE_TERMS = (
    "קרובי משפחה",
    "קרוב משפחה",
    "בן משפחה",
    "בת משפחה",
    "relatives",
    "family member",
)

DRIVING_OR_CAR_TERMS = (
    "רישיון",
    "רשיון",
    "רכב",
    "הגעה עצמאית",
    "ניידות",
    "driving license",
    "driver license",
    "car",
    "independent arrival",
)

SALARY_TERMS = (
    "ציפיות שכר",
    "שכר מספר",
    "שכר",
    "salary expectation",
    "expected salary",
    "salary",
)

WORK_MODEL_TERMS = (
    "היברידי",
    "ימי הגעה",
    "מספר ימי",
    "hybrid",
    "office days",
)

WORK_MODEL_AMBIGUITY_TERMS = (
    "לא מצוין",
    "לא צוין",
    "לא מפורט",
    "לא ברור",
    "אין פירוט",
    "לא ידוע",
    "not specified",
    "unclear",
    "unknown",
)

APPROVED_HYBRID_LIMIT_TERMS = (
    "עד פעמיים",
    "עד 2",
    "2 ימים",
    "יומיים",
    "up to two",
    "2 days",
    "two days",
)

LEGAL_TERMS = (
    "הצהרה",
    "הצהרת",
    "תנאי שימוש",
    "declaration",
)

MARKETING_CONSENT_TERMS = (
    "תוכן שיווקי",
    "צדדים שלישיים",
    "הסכמה שיווקית",
    "marketing consent",
    "third-party consent",
    "third party consent",
)

PREVIOUS_APPLICATION_TERMS = (
    "האם הגשת מועמדות בעבר",
    "הגשת מועמדות בעבר",
    "עבר מועמדות",
    "מועמדות בעבר",
    "applied before",
    "previous application",
    "previously applied",
)

OPTIONAL_MARKERS = (
    "יתרון",
    "יתרון בלבד",
    "advantage",
    "preferred",
    "nice to have",
    "optional",
    "an advantage",
)

MANDATORY_MARKERS = (
    "חובה",
    "נדרש",
    "נדרשת",
    "נדרשים",
    "דרוש",
    "דרושה",
    "לפחות",
    "required",
    "must",
    "mandatory",
    "minimum",
)

REQUIRED_SKILL_CONTEXT_TERMS = (
    "ניסיון",
    "נסיון",
    "ידע",
    "שליטה",
    "מיומנות",
    "בקיאות",
    "experience",
    "knowledge",
    "proficiency",
    "skilled",
)

MISMATCHED_MANDATORY_DEGREE_RULES = (
    (
        "industrial_engineering_degree_required",
        "Industrial Engineering and Management",
        (
            r"תואר(?:\s+ראשון)?\s+ב?הנדסת\s+תעש(?:י|יי)ה\s+וניהול\s*[-–:]?\s*(?:חובה|נדרש|נדרשת)",
            r"(?:חובה|נדרש|נדרשת)\s*[-–:]?\s*תואר(?:\s+ראשון)?\s+ב?הנדסת\s+תעש(?:י|יי)ה\s+וניהול",
            r"industrial engineering(?:\s+and\s+management)?\s+(?:degree\s+)?(?:required|mandatory)",
        ),
    ),
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    text_lower = normalize_text(text)
    return any(term.lower() in text_lower for term in terms)


def fragments_containing(text: str, aliases: tuple[str, ...]) -> list[str]:
    parts = re.split(r"[\n\r.,;|•،]+", text or "")
    matches: list[str] = []
    for part in parts:
        normalized = normalize_text(part)
        if any(alias.lower() in normalized for alias in aliases):
            matches.append(part.strip())
    return matches


def has_required_skill_context(fragment: str, aliases: tuple[str, ...]) -> bool:
    normalized = normalize_text(fragment)
    for alias in aliases:
        escaped = re.escape(alias.lower())
        for marker in REQUIRED_SKILL_CONTEXT_TERMS:
            marker = re.escape(marker.lower())
            if re.search(rf"{marker}.{{0,45}}{escaped}", normalized) or re.search(rf"{escaped}.{{0,45}}{marker}", normalized):
                return True
    return False


def is_optional_fragment(fragment: str, aliases: tuple[str, ...]) -> bool:
    normalized = normalize_text(fragment)
    if any(marker in normalized for marker in MANDATORY_MARKERS):
        return False
    if has_required_skill_context(fragment, aliases):
        return False
    return any(marker in normalized for marker in OPTIONAL_MARKERS)


def mandatory_degree_issues(text: str) -> list[CandidateFactIssue]:
    normalized = normalize_text(text)
    issues: list[CandidateFactIssue] = []
    for code, label, patterns in MISMATCHED_MANDATORY_DEGREE_RULES:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.MISSING_CANDIDATE_FACT,
                    code=code,
                    label=label,
                    severity=FactIssueSeverity.DO_NOT_APPLY,
                    reason=f"{label} is listed as a mandatory degree, but the verified candidate profile has B.A. Economics and Management.",
                    next_step="Do not submit unless the live posting clearly says this degree is only an advantage/preferred field.",
                )
            )
    return issues


def required_skill_issue(skill: SystemSkillFact, fragment: str) -> CandidateFactIssue | None:
    if is_optional_fragment(fragment, skill.aliases):
        return None

    if skill.has_experience is False:
        return CandidateFactIssue(
            kind=FailureKind.UNVERIFIED_SYSTEM_SKILL,
            code=f"missing_required_{skill.name.lower().replace(' ', '_')}",
            label=skill.name,
            severity=FactIssueSeverity.DO_NOT_APPLY,
            reason=f"{skill.name} appears to be a required skill, and the candidate has confirmed she has no experience with it.",
            next_step=f"Do not submit unless the live posting says {skill.name} is only an advantage/preferred skill.",
        )

    if skill.has_experience is None:
        return CandidateFactIssue(
            kind=FailureKind.UNVERIFIED_SYSTEM_SKILL,
            code=f"unverified_required_{skill.name.lower().replace(' ', '_')}",
            label=skill.name,
            severity=FactIssueSeverity.HUMAN_REQUIRED,
            reason=f"{skill.name} appears to be a required skill, but it is not verified in the candidate profile.",
            next_step=f"Ask whether the candidate has experience with {skill.name}, or verify that it is only an advantage in the live posting.",
        )

    return CandidateFactIssue(
        kind=FailureKind.UNVERIFIED_SYSTEM_SKILL,
        code=f"verified_required_{skill.name.lower().replace(' ', '_')}",
        label=skill.name,
        severity=FactIssueSeverity.RESOLVED,
        reason=f"{skill.name} is verified in the candidate profile.",
        next_step="Use the verified candidate profile answer.",
    )


def assess_candidate_facts(text: str, profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> CandidateFactAssessment:
    issues: list[CandidateFactIssue] = []

    if has_any(text, ID_TERMS):
        if profile.national_id:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="national_id_available",
                    label="תעודת זהות",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="The candidate's national ID was explicitly provided by the operator.",
                    next_step="Fill the national ID only when the official application form requires it.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="national_id_missing",
                    label="תעודת זהות",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The form asks for national ID, but the candidate profile does not include it.",
                    next_step="Ask the operator for the national ID before continuing.",
                )
            )

    if has_any(text, RELATIVE_TERMS):
        if profile.has_relatives_at_company is not None:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="relatives_answer_available",
                    label="קרובי משפחה בחברה",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="The operator confirmed the candidate has no relatives at the company.",
                    next_step="Answer 'No' / 'לא' when this disclosure is mandatory.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="relatives_answer_missing",
                    label="קרובי משפחה בחברה",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The form asks about relatives at the company, but no verified answer exists.",
                    next_step="Ask the operator before continuing.",
                )
            )

    if has_any(text, DRIVING_OR_CAR_TERMS):
        if profile.has_driving_license and profile.has_car and profile.can_arrive_independently:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="driving_or_car_available",
                    label="רישיון/רכב/ניידות",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="Driving license, car, and independent arrival are verified in the candidate profile.",
                    next_step="Use the verified candidate profile answer.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SENSITIVE_FIELD,
                    code="driving_or_car_unverified",
                    label="רישיון/רכב/ניידות",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The role or form mentions driving, car, mobility, or independent arrival, which is not verified for the candidate.",
                    next_step="Ask whether the candidate has a driving license, car, and independent arrival capability before applying.",
                )
            )

    if has_any(text, SALARY_TERMS):
        if profile.approved_salary_expectation:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SALARY_REQUIRED,
                    code="numeric_salary_approved",
                    label="ציפיות שכר",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="A numeric salary expectation was approved in the candidate profile.",
                    next_step="Use the approved salary only when a numeric salary field is mandatory.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.SALARY_REQUIRED,
                    code="numeric_salary_unapproved",
                    label="ציפיות שכר",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="Numeric salary expectations are not approved in the candidate profile.",
                    next_step="Continue only if the form accepts flexible/free text; otherwise ask for an approved numeric salary range.",
                )
            )

    if has_any(text, WORK_MODEL_TERMS):
        if has_any(text, WORK_MODEL_AMBIGUITY_TERMS):
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.WORK_MODEL_UNKNOWN,
                    code="work_model_unverified",
                    label="מודל עבודה",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The job depends on office-days, commute, or hybrid details that are not fully verified.",
                    next_step="Ask for approval unless the live posting clearly meets the approved location/hybrid policy.",
                )
            )
        elif has_any(text, APPROVED_HYBRID_LIMIT_TERMS):
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.WORK_MODEL_UNKNOWN,
                    code="hybrid_limit_matches_policy",
                    label="מודל עבודה",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="The hybrid office-days requirement matches the approved search policy.",
                    next_step="Proceed if the rest of the role matches.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.WORK_MODEL_UNKNOWN,
                    code="work_model_unverified",
                    label="מודל עבודה",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The job depends on office-days, commute, or hybrid details that are not fully verified.",
                    next_step="Ask for approval unless the live posting clearly meets the approved location/hybrid policy.",
                )
            )

    if has_any(text, LEGAL_TERMS):
        issues.append(
            CandidateFactIssue(
                kind=FailureKind.LEGAL_DECLARATION,
                code="legal_declaration_unverified",
                label="הצהרה משפטית",
                severity=FactIssueSeverity.HUMAN_REQUIRED,
                reason="The form mentions a legal declaration or terms acceptance.",
                next_step="Pause for explicit operator approval before accepting.",
            )
        )

    if has_any(text, MARKETING_CONSENT_TERMS):
        if profile.marketing_consent_approved:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.MARKETING_CONSENT,
                    code="marketing_consent_approved",
                    label="הסכמה שיווקית",
                    severity=FactIssueSeverity.RESOLVED,
                    reason="The operator approved the Drushim marketing/third-party consent policy for this candidate.",
                    next_step="Proceed through the registration/application flow when this consent is required.",
                )
            )
        else:
            issues.append(
                CandidateFactIssue(
                    kind=FailureKind.MARKETING_CONSENT,
                    code="marketing_consent_unapproved",
                    label="הסכמה שיווקית",
                    severity=FactIssueSeverity.HUMAN_REQUIRED,
                    reason="The form requires marketing or third-party consent that is not approved in the candidate profile.",
                    next_step="Ask for explicit approval before continuing.",
                )
            )

    if has_any(text, PREVIOUS_APPLICATION_TERMS):
        issues.append(
            CandidateFactIssue(
                kind=FailureKind.MISSING_CANDIDATE_FACT,
                code="previous_application_unverified",
                label="הגשת מועמדות בעבר",
                severity=FactIssueSeverity.HUMAN_REQUIRED,
                reason="The official form asks whether the candidate previously applied, and this answer is not verified in the candidate profile.",
                next_step="Ask the operator whether the candidate submitted an application to this employer after the date shown on the form.",
            )
        )

    issues.extend(mandatory_degree_issues(text))

    for skill in profile.system_skills:
        seen_codes: set[str] = set()
        for fragment in fragments_containing(text, skill.aliases):
            issue = required_skill_issue(skill, fragment)
            if issue and issue.code not in seen_codes:
                issues.append(issue)
                seen_codes.add(issue.code)

    return CandidateFactAssessment(tuple(issues))


def safe_form_answers(profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> dict[str, str]:
    answers: dict[str, str] = {}
    if profile.national_id:
        answers["national_id"] = profile.national_id
    if profile.has_relatives_at_company is not None:
        answers["has_relatives_at_company"] = "לא" if not profile.has_relatives_at_company else "כן"
    if profile.has_driving_license is not None:
        answers["has_driving_license"] = "כן" if profile.has_driving_license else "לא"
    if profile.has_car is not None:
        answers["has_car"] = "כן" if profile.has_car else "לא"
    if profile.can_arrive_independently is not None:
        answers["can_arrive_independently"] = "כן" if profile.can_arrive_independently else "לא"
    if profile.marketing_consent_approved is not None:
        answers["marketing_consent_approved"] = "כן" if profile.marketing_consent_approved else "לא"
    if profile.approved_salary_expectation is not None:
        answers["approved_salary_expectation"] = str(profile.approved_salary_expectation)
    return answers
