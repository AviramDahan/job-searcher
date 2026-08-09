from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
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


DEFAULT_LOCATION_PREFERENCES_PATH = Path("outputs/location_preferences.json")
LOCATION_PREFERENCES_ENV = "JOB_SEARCH_LOCATION_PREFERENCES"

DEFAULT_APPROVED_LOCATION_OPTIONS = (
    {"key": "sderot", "label": "שדרות", "terms": ("שדרות", "sderot")},
    {"key": "netivot", "label": "נתיבות", "terms": ("נתיבות", "netivot")},
    {"key": "ashkelon", "label": "אשקלון", "terms": ("אשקלון", "ashkelon")},
    {"key": "kiryat_gat", "label": "קריית גת", "terms": ("קריית גת", "קרית גת", "kiryat gat")},
    {"key": "beer_sheva", "label": "באר שבע", "terms": ("באר שבע", 'ב"ש', "beer sheva", "be'er sheva", "beersheba")},
    {"key": "ashdod", "label": "אשדוד", "terms": ("אשדוד", "ashdod")},
    {"key": "ofakim", "label": "אופקים", "terms": ("אופקים", "ofakim")},
    {"key": "kiryat_malachi", "label": "קריית מלאכי", "terms": ("קריית מלאכי", "קרית מלאכי", "kiryat malachi")},
    {"key": "beer_tuvya", "label": "באר טוביה", "terms": ("באר טוביה", "beer tuvya")},
    {"key": "timorim", "label": "תימורים", "terms": ("תימורים", "timorim")},
    {"key": "lehavim", "label": "להבים", "terms": ("להבים", "lehavim")},
)

USER_APPROVABLE_LOCATION_OPTIONS = (
    {"key": "yavne", "label": "יבנה", "terms": ("יבנה", "yavne")},
    {"key": "rehovot", "label": "רחובות", "terms": ("רחובות", "rehovot")},
    {"key": "lod", "label": "לוד", "terms": ("לוד", "lod")},
    {"key": "ramla", "label": "רמלה", "terms": ("רמלה", "ramla")},
    {"key": "rishon_lezion", "label": "ראשון לציון", "terms": ("ראשון לציון", "rishon lezion", "rishon letsiyon")},
    {"key": "ness_ziona", "label": "נס ציונה", "terms": ("נס ציונה", "ness ziona")},
    {"key": "gedera", "label": "גדרה", "terms": ("גדרה", "gedera")},
    {"key": "gan_yavne", "label": "גן יבנה", "terms": ("גן יבנה", "gan yavne")},
)

LOCATION_OPTION_ALIASES = {
    str(option["key"]): tuple(str(term) for term in option["terms"])
    for option in (*DEFAULT_APPROVED_LOCATION_OPTIONS, *USER_APPROVABLE_LOCATION_OPTIONS)
}


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
    "יבנה",
    "yavne",
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

FULL_REMOTE_TERMS = (
    "עבודה מרחוק מלאה",
    "מרחוק מלא",
    "משרה מרחוק",
    "remote only",
    "fully remote",
    "full remote",
    "100% remote",
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


def unique_terms(terms: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        clean = clean_text(str(term))
        lowered = clean.lower()
        if clean and lowered not in seen:
            seen.add(lowered)
            result.append(clean)
    return tuple(result)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "כן", "approved"}


def location_terms_from_entry(entry: Any) -> tuple[str, ...]:
    if isinstance(entry, str):
        key = clean_text(entry)
        return unique_terms((*LOCATION_OPTION_ALIASES.get(key, ()), key))
    if not isinstance(entry, dict):
        return ()
    if not parse_bool(entry.get("approved", True)):
        return ()

    key = clean_text(entry.get("key", ""))
    label = clean_text(entry.get("label", "") or entry.get("city", ""))
    terms = entry.get("terms", ())
    if not isinstance(terms, list):
        terms = ()
    return unique_terms((*LOCATION_OPTION_ALIASES.get(key, ()), label, key, *terms))


def load_approved_location_terms(preferences_path: str | Path | None = None) -> tuple[str, ...]:
    raw_path = preferences_path or os.environ.get(LOCATION_PREFERENCES_ENV) or DEFAULT_LOCATION_PREFERENCES_PATH
    path = Path(raw_path)
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ()

    preferences = payload.get("location_preferences", payload) if isinstance(payload, dict) else {}
    approved = preferences.get("approved_locations", {}) if isinstance(preferences, dict) else {}
    entries: Iterable[Any]
    if isinstance(approved, dict):
        entries = approved.values()
    elif isinstance(approved, list):
        entries = approved
    else:
        entries = ()

    terms: list[str] = []
    for entry in entries:
        terms.extend(location_terms_from_entry(entry))
    return unique_terms(terms)


def location_policy_payload() -> dict[str, Any]:
    return {
        "default_approved": [
            {"key": option["key"], "label": option["label"], "terms": list(option["terms"]), "locked": True}
            for option in DEFAULT_APPROVED_LOCATION_OPTIONS
        ],
        "user_approvable": [
            {"key": option["key"], "label": option["label"], "terms": list(option["terms"])}
            for option in USER_APPROVABLE_LOCATION_OPTIONS
        ],
    }


def has_limited_hybrid(text: str) -> bool:
    if any(pattern.search(text or "") for pattern in HYBRID_OVER_LIMIT_PATTERNS):
        return False
    return any(pattern.search(text or "") for pattern in LIMITED_HYBRID_PATTERNS)


def assess_location(
    location: str,
    context: str = "",
    approved_location_terms: Iterable[str] | None = None,
) -> LocationAssessment:
    clean_location = clean_text(location)
    combined = clean_text(f"{clean_location} {context}")
    user_terms = unique_terms(approved_location_terms if approved_location_terms is not None else load_approved_location_terms())

    primary_matches = matching_terms(combined, PRIMARY_LOCATION_TERMS)
    location_primary_matches = matching_terms(clean_location, PRIMARY_LOCATION_TERMS)
    if location_primary_matches:
        return LocationAssessment(
            decision=LocationDecision.IN_SCOPE,
            reason=f"מיקום באזורי היעד: {', '.join(location_primary_matches[:3])}.",
            matched_terms=location_primary_matches,
            score_points=20,
        )

    full_remote_matches = matching_terms(combined, FULL_REMOTE_TERMS)
    if full_remote_matches:
        return LocationAssessment(
            decision=LocationDecision.IN_SCOPE,
            reason=f"מודל עבודה מרחוק מלא מאושר לפי מדיניות המיקום: {', '.join(full_remote_matches[:3])}.",
            matched_terms=full_remote_matches,
            score_points=18,
        )

    user_approved_matches = matching_terms(clean_location, user_terms)
    if user_approved_matches:
        return LocationAssessment(
            decision=LocationDecision.IN_SCOPE,
            reason=f"מיקום אושר בדשבורד לחיפוש והגשה: {', '.join(user_approved_matches[:3])}.",
            matched_terms=user_approved_matches,
            score_points=20,
        )

    secondary_matches = matching_terms(clean_location, SECONDARY_LOCATION_TERMS)
    if secondary_matches:
        return LocationAssessment(
            decision=LocationDecision.OUT_OF_SCOPE,
            reason=(
                f"נפסל: המיקום '{clean_location}' רחוק משדרות ואינו רלוונטי לפי מדיניות המיקום המעודכנת "
                f"({', '.join(secondary_matches[:3])})."
            ),
            matched_terms=secondary_matches,
            score_points=0,
        )

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
