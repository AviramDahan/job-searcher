from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class LocationDecision(str, Enum):
    IN_SCOPE = "in_scope"
    APPROVAL_REQUIRED = "approval_required"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class LocationAssessment:
    decision: LocationDecision
    reason: str
    matched_terms: tuple[str, ...]
    score_points: int


PRIMARY_LOCATION_TERMS = (
    "שדרות",
    "sderot",
    "נתיבות",
    "netivot",
    "אשקלון",
    "ashkelon",
    "קריית גת",
    "קרית גת",
    "kiryat gat",
    "באר שבע",
    'ב"ש',
    "beer sheva",
    "be'er sheva",
    "beersheba",
    "אשדוד",
    "ashdod",
    "יבנה",
    "yavne",
    "אופקים",
    "ofakim",
    "קריית מלאכי",
    "קרית מלאכי",
    "kiryat malachi",
    "באר טוביה",
    "beer tuvya",
    "תימורים",
    "timorim",
    "להבים",
    "lehavim",
    "דרום",
    "south district",
)

SECONDARY_LOCATION_TERMS = (
    "רחובות",
    "rehovot",
    "נס ציונה",
    "ness ziona",
    "גדרה",
    "gedera",
    "גן יבנה",
    "gan yavne",
    "לוד",
    "lod",
    "רמלה",
    "ramla",
    "ראשון לציון",
    "rishon lezion",
    "rishon letsiyon",
)

UNKNOWN_LOCATION_TERMS = (
    "מספר מקומות",
    "כל הארץ",
    "פריסה ארצית",
    "nationwide",
    "multiple locations",
    "several locations",
)

HYBRID_TERMS = (
    "היברידי",
    "היברידית",
    "hybrid",
    "עבודה מהבית",
    "עבודה מרחוק",
    "remote",
)

LIMITED_HYBRID_PATTERNS = (
    re.compile(r"עד\s*(?:פעמיים|2)\s*(?:בשבוע|ימי הגעה|הגעות)", re.IGNORECASE),
    re.compile(r"(?:יום|יומיים|2\s*ימים|1-2)\s*(?:בשבוע)?\s*(?:מהמשרד|במשרד|במשרדי החברה)", re.IGNORECASE),
    re.compile(r"(?:up to\s*)?(?:2|two)\s*(?:office|onsite)?\s*days?\s*(?:per week|weekly|a week)", re.IGNORECASE),
    re.compile(r"(?:office|onsite)\s*(?:up to\s*)?(?:2|two)\s*days?\s*(?:per week|weekly|a week)?", re.IGNORECASE),
)

HYBRID_OVER_LIMIT_PATTERNS = (
    re.compile(r"לפחות\s*(?:יומיים|2)\s*(?:בשבוע|ימי הגעה|הגעות)?", re.IGNORECASE),
    re.compile(r"at least\s*(?:2|two)\s*(?:office|onsite)?\s*days?", re.IGNORECASE),
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def lower_text(value: str) -> str:
    return clean_text(value).lower()


def matching_terms(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    lowered = lower_text(text)
    return tuple(term for term in terms if term.lower() in lowered)


def has_limited_hybrid(text: str) -> bool:
    if any(pattern.search(text or "") for pattern in HYBRID_OVER_LIMIT_PATTERNS):
        return False
    return any(pattern.search(text or "") for pattern in LIMITED_HYBRID_PATTERNS)


def assess_location(location: str, context: str = "") -> LocationAssessment:
    clean_location = clean_text(location)
    combined = clean_text(f"{clean_location} {context}")

    primary_matches = matching_terms(combined, PRIMARY_LOCATION_TERMS)
    if primary_matches:
        return LocationAssessment(
            decision=LocationDecision.IN_SCOPE,
            reason=f"מיקום באזורי היעד: {', '.join(primary_matches[:3])}.",
            matched_terms=primary_matches,
            score_points=20,
        )

    if has_limited_hybrid(combined):
        return LocationAssessment(
            decision=LocationDecision.IN_SCOPE,
            reason="מודל היברידי מתאים למדיניות: עד שתי הגעות שבועיות למשרד.",
            matched_terms=("hybrid_up_to_two_days",),
            score_points=16,
        )

    secondary_matches = matching_terms(clean_location, SECONDARY_LOCATION_TERMS)
    if secondary_matches:
        return LocationAssessment(
            decision=LocationDecision.APPROVAL_REQUIRED,
            reason=(
                "מיקום באזור משני מחוץ לרשימת היעד הראשית "
                f"({', '.join(secondary_matches[:3])}); נדרש אישור מרחק או מודל עבודה לפני הגשה."
            ),
            matched_terms=secondary_matches,
            score_points=8,
        )

    hybrid_matches = matching_terms(combined, HYBRID_TERMS)
    if hybrid_matches:
        return LocationAssessment(
            decision=LocationDecision.APPROVAL_REQUIRED,
            reason="המשרה היברידית, אך לא מופיע שמספר ההגעות למשרד הוא עד פעמיים בשבוע.",
            matched_terms=hybrid_matches,
            score_points=8,
        )

    if not clean_location or matching_terms(clean_location, UNKNOWN_LOCATION_TERMS):
        return LocationAssessment(
            decision=LocationDecision.APPROVAL_REQUIRED,
            reason="המיקום לא מספיק ברור; נדרש אישור לפני הגשה.",
            matched_terms=matching_terms(clean_location, UNKNOWN_LOCATION_TERMS),
            score_points=0,
        )

    return LocationAssessment(
        decision=LocationDecision.OUT_OF_SCOPE,
        reason=f"נפסל: המיקום '{clean_location}' אינו באזורי החיפוש המאושרים ולא מופיע מודל היברידי מתאים.",
        matched_terms=(),
        score_points=0,
    )
