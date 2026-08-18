from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class FailureKind(str, Enum):
    LOGIN_OR_ACCOUNT = "login_or_account"
    CAPTCHA_OR_SECURITY = "captcha_or_security"
    FORM_AUTOMATION_UNRELIABLE = "form_automation_unreliable"
    NO_DIRECT_FORM = "no_direct_form"
    MARKETING_CONSENT = "marketing_consent"
    SENSITIVE_FIELD = "sensitive_field"
    LEGAL_DECLARATION = "legal_declaration"
    MISSING_CANDIDATE_FACT = "missing_candidate_fact"
    SALARY_REQUIRED = "salary_required"
    WORK_MODEL_UNKNOWN = "work_model_unknown"
    UNVERIFIED_SYSTEM_SKILL = "unverified_system_skill"
    EXPERIENCE_AMBIGUITY = "experience_ambiguity"
    CLOSED_JOB = "closed_job"
    UNKNOWN = "unknown"


class AutomationAction(str, Enum):
    RETRY_WITH_PERSISTENT_SESSION = "retry_with_persistent_session"
    FILL_UNTIL_HUMAN_GATE = "fill_until_human_gate"
    USE_COMPANY_SITE_FALLBACK = "use_company_site_fallback"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    DO_NOT_APPLY = "do_not_apply"
    INVESTIGATE = "investigate"


@dataclass(frozen=True)
class FailureClassification:
    kind: FailureKind
    action: AutomationAction
    can_improve_with_code: bool
    requires_human: bool
    reason: str
    next_step: str
    signals: tuple[FailureKind, ...] = ()


SECURITY_TERMS = (
    "captcha",
    "recaptcha",
    "radware",
    "cloudflare",
    "בדיקת אבטחה",
)

LOGIN_TERMS = (
    "התחברות",
    "הרשמה",
    "חשבון",
    "סיסמה",
    "סיסמא",
    "קוד אימות",
    "אימות למייל",
    "כתובת המייל",
    "כתובת האימייל",
    "מייל כבר קיים",
    "successfactors",
    "linkedin",
    "tap",
    "password",
    "verification code",
    "email code",
    "email already exists",
    "existing email",
    "account state",
    "site session",
    "application path",
    "login required",
    "requires login",
    "login before",
)

LOGIN_HUMAN_TERMS = (
    "הסיסמה שסופקה",
    "הסיסמא שסופקה",
    "הסיסמה שסופקה נכשל",
    "הסיסמא שסופקה נכשל",
    "סיסמה לא חוקית",
    "סיסמא לא חוקית",
    "לאפס סיסמה",
    "איפוס סיסמה",
    "המייל קיים",
    "קיים במערכת",
    "נדרש קוד ידני",
    "קוד ידני",
    "invalid password",
    "password reset",
    "manual code",
)

FORM_UNRELIABLE_TERMS = (
    "לא קלט",
    "לא איפשר",
    "הקפיא",
    "קפא",
    "דפדפן הצדדי",
    "דורש השלמה ידנית סופית",
    "נחסם",
    "העלאת הקובץ",
)

NO_DIRECT_FORM_TERMS = (
    "לא נמצא טופס",
    "לא נמצא טופס ישיר",
    "מייל חיצוני",
    "מקור ההגשה",
    "no direct form",
    "external email",
)

MARKETING_CONSENT_TERMS = (
    "תוכן שיווקי",
    "צדדים שלישיים",
    "הסכמה שיווקית",
    "marketing consent",
    "third-party consent",
    "third party consent",
)

SENSITIVE_FIELD_TERMS = (
    "תעודת זהות",
    "קרובי משפחה",
    "national id",
    "identity number",
    "id number",
    "relatives",
    "family member",
    "רישיון",
    "רכב",
    "הגעה עצמאית",
    "ניידות",
    "car",
    "driving license",
    "driver license",
    "independent arrival",
)

SALARY_TERMS = (
    "ציפיות שכר",
    "שכר מספר",
    "שכר מינימלי",
    "ערך מספרי",
    "salary expectation",
    "expected salary",
    "minimum salary",
    "numeric salary",
)

WORK_MODEL_TERMS = (
    "היברידי",
    "ימי הגעה",
    "מספר ימי",
    "עד פעמיים",
    "hybrid",
    "office days",
)

LEGAL_TERMS = (
    "הצהרה",
    "הצהרת",
    "תנאי שימוש",
)

MISSING_FACT_TERMS = (
    "שאלה שאין לה תשובה",
    "לא ניתן לאמת",
    "מקור פרסום",
    "אפשרויות מוגבלות",
    "מידע חסר",
    "האם הגשת מועמדות בעבר",
    "הגשת מועמדות בעבר",
    "עבר מועמדות",
    "מועמדות בעבר",
    "משרה זמנית",
    "זמנית או קצרה",
    "החלפה לחל",
    "החלפה לחופשת לידה",
    "משרת סטודנט",
    "סטודנט/ית פעיל",
    "סטודנטית פעילה",
    "סטודנט לתואר",
    "סטודנטית לתואר",
    "missing mandatory answer",
    "unverified answer",
    "unknown source",
    "applied before",
    "previous application",
    "previously applied",
    "temporary role",
    "short-term",
    "student position",
    "active student",
)

SYSTEM_SKILL_TERMS = (
    "priority",
    "erp",
    "mrp",
    "sap",
    "power bi",
    "מערכת bi",
    "nibit",
    "חשבשבת",
    "פריוריטי",
    "ms project",
    "canva",
    "chatgpt",
    "chat gpt",
    "כלי ai",
    "כלי בינה מלאכותית",
    "ai tools",
    "חילן",
    "hilan",
)

EXPERIENCE_TERMS = (
    "דרישת חובה לניסיון",
    "דרישת ניסיון",
    "תלוי בפרשנות ניסיון",
    "פרשנות ניסיון",
    "לא מופיע בקורות החיים",
    "לא מופיעה בקורות החיים",
    "לא מופיע במפורש",
    "לא מופיעה במפורש",
    "לא מופיע בקו\"ח",
    "לא מופיעה בקו\"ח",
    "ניסיון בסביבה תעשייתית",
    "ניסיון בסביבת ייצור",
    "ניסיון תעשייתי",
    "ניסיון בתעשיה יצרנית",
    "ניסיון בתעשייה יצרנית",
    "סביבה תעשייתית",
    "תעשיה יצרנית",
    "תעשייה יצרנית",
    "סביבת ייצור",
    "עבודה תפעולית בשטח",
    "רכש בענף הבנייה",
    "רכש בענף הבניה",
    "ארגון גדול",
    "ככלכלן",
    "כשכלכלן",
    "3 שנות",
    "5 שנות",
    "4 years",
    "5 years",
    "four years",
    "five years",
    "industrial environment",
    "manufacturing industry",
    "manufacturing environment",
    "production environment",
    "field operations",
    "operational field",
    "not explicit in cv",
    "not explicit in resume",
    "not shown on cv",
    "not shown in resume",
    "depends on how the candidate's experience is interpreted",
    "experience is interpreted",
    "experience mapping",
)

SAFE_EXPERIENCE_RANGE_PATTERNS = (
    r"\b(?:up to|0\s*[-–]\s*3)\s*(?:years?|yrs?)\b",
    r"(?:עד|0\s*[-–]\s*3)\s*3?\s*(?:שנים|שנות)",
)

REQUIRED_EXPERIENCE_PATTERNS = (
    r"(?:לפחות|מינימום|מעל)\s*(?:3|4|5|שלוש|ארבע|חמש)\s*(?:שנים|שנות)",
    r"(?:3|4|5)\s*\+\s*(?:שנים|שנות)",
    r"(?:ניסיון|נסיון)\s+של\s+(?:3|4|5|שלוש|ארבע|חמש)\s*(?:שנים|שנות)",
    r"(?:ניסיון|נסיון)[^.;\n]{0,120}[-–:]\s*(?:3|4|5|שלוש|ארבע|חמש)\s*(?:שנים|שנות)",
    r"(?:3|4|5|שלוש|ארבע|חמש)\s*(?:שנים|שנות)\s+(?:לפחות|ניסיון|נסיון|חובה|בתפקיד|ברכש)",
    r"(?:at least|minimum|min\.?|over)\s*(?:3|4|5)\s*(?:years?|yrs?)",
    r"(?:3|4|5)\s*\+\s*(?:years?|yrs?)",
    r"(?:experience|experienced)[^.;\n]{0,120}[-–:]\s*(?:3|4|5)\s*(?:years?|yrs?)",
    r"(?:3|4|5)\s*(?:years?|yrs?)\s+(?:minimum|required|of experience|experience)",
    r"(?:three|four|five)\s+(?:years?|yrs?)\s+(?:minimum|required|of experience|experience)",
    r"(?:experience|experienced)\s+(?:as|in)\s+(?:an?\s+)?(?:economist|pmo|project controller)",
    r"(?:ניסיון|נסיון)\s+(?:כ|בתפקיד)\s*(?:כלכלן|כלכלנית|pmo|PMO|project controller)",
)

CLOSED_JOB_TERMS = (
    "כבר לא מקבלת",
    "כבר אינה מקבלת",
    "לא מקבלת בקשות",
    "no longer accepting",
    "no longer accepts",
    "closed",
    "expired",
)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    text_lower = text.lower()
    return any(term.lower() in text_lower for term in terms)


def _has_regex(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _without_safe_experience_ranges(text: str) -> str:
    cleaned = text
    for pattern in SAFE_EXPERIENCE_RANGE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _has_experience_ambiguity(text: str) -> bool:
    candidate_text = _without_safe_experience_ranges(text)
    return _has_any(candidate_text, EXPERIENCE_TERMS) or _has_regex(candidate_text, REQUIRED_EXPERIENCE_PATTERNS)


def detect_failure_signals(reason: str, link: str = "", title: str = "", company: str = "") -> tuple[FailureKind, ...]:
    text = " ".join(part for part in [reason, link, title, company, urlparse(link).netloc] if part)
    signals: list[FailureKind] = []
    checks = (
        (FailureKind.CLOSED_JOB, CLOSED_JOB_TERMS),
        (FailureKind.CAPTCHA_OR_SECURITY, SECURITY_TERMS),
        (FailureKind.MARKETING_CONSENT, MARKETING_CONSENT_TERMS),
        (FailureKind.SENSITIVE_FIELD, SENSITIVE_FIELD_TERMS),
        (FailureKind.SALARY_REQUIRED, SALARY_TERMS),
        (FailureKind.WORK_MODEL_UNKNOWN, WORK_MODEL_TERMS),
        (FailureKind.LEGAL_DECLARATION, LEGAL_TERMS),
        (FailureKind.MISSING_CANDIDATE_FACT, MISSING_FACT_TERMS),
        (FailureKind.LOGIN_OR_ACCOUNT, LOGIN_TERMS + LOGIN_HUMAN_TERMS),
        (FailureKind.FORM_AUTOMATION_UNRELIABLE, FORM_UNRELIABLE_TERMS),
        (FailureKind.NO_DIRECT_FORM, NO_DIRECT_FORM_TERMS),
        (FailureKind.UNVERIFIED_SYSTEM_SKILL, SYSTEM_SKILL_TERMS),
    )
    for kind, terms in checks:
        if _has_any(text, terms):
            signals.append(kind)
    if _has_experience_ambiguity(text):
        signals.append(FailureKind.EXPERIENCE_AMBIGUITY)
    return tuple(signals)


def classify_failure(reason: str, link: str = "", title: str = "", company: str = "") -> FailureClassification:
    text = " ".join(part for part in [reason, link, title, company, urlparse(link).netloc] if part)
    signals = detect_failure_signals(reason=reason, link=link, title=title, company=company)

    if _has_any(text, CLOSED_JOB_TERMS):
        return FailureClassification(
            FailureKind.CLOSED_JOB,
            AutomationAction.DO_NOT_APPLY,
            can_improve_with_code=True,
            requires_human=False,
            reason="The job is no longer accepting applications.",
            next_step="Filter closed jobs earlier and remove them from submission queues.",
            signals=signals,
        )

    if _has_any(text, SECURITY_TERMS):
        return FailureClassification(
            FailureKind.CAPTCHA_OR_SECURITY,
            AutomationAction.FILL_UNTIL_HUMAN_GATE,
            can_improve_with_code=True,
            requires_human=True,
            reason="The site presented CAPTCHA or an anti-automation security layer.",
            next_step="Use a persistent browser, fill all safe fields, capture evidence, then pause for a human to pass the challenge.",
            signals=signals,
        )

    if _has_any(text, MARKETING_CONSENT_TERMS):
        return FailureClassification(
            FailureKind.MARKETING_CONSENT,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=False,
            requires_human=True,
            reason="The form requires consent beyond a normal application submission.",
            next_step="Ask for an explicit policy decision before checking marketing or third-party consent boxes.",
            signals=signals,
        )

    if _has_any(text, SALARY_TERMS):
        return FailureClassification(
            FailureKind.SALARY_REQUIRED,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The form or posting requires salary expectations that were not approved in advance.",
            next_step="Store an approved salary policy or keep this as a human gate when a numeric value is required.",
            signals=signals,
        )

    if _has_any(text, WORK_MODEL_TERMS):
        return FailureClassification(
            FailureKind.WORK_MODEL_UNKNOWN,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The job depends on work model, office days, commute, or hybrid constraints that are not confirmed.",
            next_step="Capture office-days and commute tolerance as candidate facts, then reuse them during filtering.",
            signals=signals,
        )

    if _has_any(text, LEGAL_TERMS):
        return FailureClassification(
            FailureKind.LEGAL_DECLARATION,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=False,
            requires_human=True,
            reason="The form includes a legal declaration or terms acceptance that should not be signed blindly.",
            next_step="Pause and ask the candidate/operator to approve the declaration.",
            signals=signals,
        )

    if _has_any(text, MISSING_FACT_TERMS):
        return FailureClassification(
            FailureKind.MISSING_CANDIDATE_FACT,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The form requires an answer that is not verified in the candidate profile or source evidence.",
            next_step="Ask the operator for the missing answer before retrying this application.",
            signals=signals,
        )

    if _has_any(text, LOGIN_HUMAN_TERMS):
        return FailureClassification(
            FailureKind.LOGIN_OR_ACCOUNT,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The site requires account recovery, a manual verification code, or credentials that are not currently valid.",
            next_step="Ask the operator to log in, reset the password, or provide the verification code before retrying.",
            signals=signals,
        )

    if _has_any(text, LOGIN_TERMS):
        return FailureClassification(
            FailureKind.LOGIN_OR_ACCOUNT,
            AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
            can_improve_with_code=True,
            requires_human=False,
            reason="The application path depends on login, account state, or a site session.",
            next_step="Use a persistent Playwright profile per site and verify login before entering the application flow.",
            signals=signals,
        )

    if _has_any(text, FORM_UNRELIABLE_TERMS):
        return FailureClassification(
            FailureKind.FORM_AUTOMATION_UNRELIABLE,
            AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
            can_improve_with_code=True,
            requires_human=False,
            reason="The form did not behave reliably in one-off automation.",
            next_step="Retry with a site adapter, stable selectors, screenshot evidence, and field-level verification after typing.",
            signals=signals,
        )

    if _has_any(text, NO_DIRECT_FORM_TERMS):
        return FailureClassification(
            FailureKind.NO_DIRECT_FORM,
            AutomationAction.USE_COMPANY_SITE_FALLBACK,
            can_improve_with_code=True,
            requires_human=True,
            reason="The source did not expose a reliable direct application form.",
            next_step="Search for the same role on the official company career page before sending a manual handoff.",
            signals=signals,
        )

    if _has_experience_ambiguity(text):
        return FailureClassification(
            FailureKind.EXPERIENCE_AMBIGUITY,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The requirement depends on how the candidate's experience is interpreted.",
            next_step="Create reusable experience mappings, for example whether budget-control work counts as economist experience.",
            signals=signals,
        )

    if _has_any(text, SYSTEM_SKILL_TERMS):
        return FailureClassification(
            FailureKind.UNVERIFIED_SYSTEM_SKILL,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The job requires a system/tool skill that has not been verified for the candidate.",
            next_step="Add candidate facts for each system; if verified, future forms can proceed without stopping.",
            signals=signals,
        )

    if _has_any(text, SENSITIVE_FIELD_TERMS):
        return FailureClassification(
            FailureKind.SENSITIVE_FIELD,
            AutomationAction.HUMAN_APPROVAL_REQUIRED,
            can_improve_with_code=True,
            requires_human=True,
            reason="The form asks for a sensitive or unverified candidate fact.",
            next_step="Store the verified fact in the candidate profile, then allow future submissions to reuse it.",
            signals=signals,
        )

    return FailureClassification(
        FailureKind.UNKNOWN,
        AutomationAction.INVESTIGATE,
        can_improve_with_code=True,
        requires_human=True,
        reason="The blocker does not match a known failure pattern.",
        next_step="Inspect the page and add a new classifier rule if this repeats.",
        signals=signals,
    )
