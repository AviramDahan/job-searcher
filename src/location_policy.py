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
    {"key": "sderot", "label": "שדרות", "terms": ("שדרות", "sderot"), "lat": 31.525, "lng": 34.596, "kind": "city"},
    {"key": "netivot", "label": "נתיבות", "terms": ("נתיבות", "netivot"), "lat": 31.423, "lng": 34.589, "kind": "city"},
    {"key": "ashkelon", "label": "אשקלון", "terms": ("אשקלון", "ashkelon"), "lat": 31.668, "lng": 34.574, "kind": "city"},
    {"key": "kiryat_gat", "label": "קריית גת", "terms": ("קריית גת", "קרית גת", "kiryat gat"), "lat": 31.609, "lng": 34.764, "kind": "city"},
    {
        "key": "beer_sheva",
        "label": "באר שבע",
        "terms": ("באר שבע", 'ב"ש', "beer sheva", "be'er sheva", "beersheba"),
        "lat": 31.253,
        "lng": 34.791,
        "kind": "city",
    },
    {"key": "ashdod", "label": "אשדוד", "terms": ("אשדוד", "ashdod"), "lat": 31.802, "lng": 34.644, "kind": "city"},
    {"key": "ofakim", "label": "אופקים", "terms": ("אופקים", "ofakim"), "lat": 31.314, "lng": 34.620, "kind": "city"},
    {
        "key": "kiryat_malachi",
        "label": "קריית מלאכי",
        "terms": ("קריית מלאכי", "קרית מלאכי", "kiryat malachi"),
        "lat": 31.731,
        "lng": 34.746,
        "kind": "city",
    },
    {"key": "beer_tuvya", "label": "באר טוביה", "terms": ("באר טוביה", "beer tuvya"), "lat": 31.740, "lng": 34.720, "kind": "moshav"},
    {"key": "timorim", "label": "תימורים", "terms": ("תימורים", "timorim"), "lat": 31.715, "lng": 34.765, "kind": "moshav"},
    {"key": "lehavim", "label": "להבים", "terms": ("להבים", "lehavim"), "lat": 31.372, "lng": 34.817, "kind": "town"},
)

USER_APPROVABLE_LOCATION_OPTIONS = (
    {"key": "yavne", "label": "יבנה", "terms": ("יבנה", "yavne"), "lat": 31.878, "lng": 34.739, "kind": "city"},
    {"key": "rehovot", "label": "רחובות", "terms": ("רחובות", "rehovot"), "lat": 31.894, "lng": 34.812, "kind": "city"},
    {"key": "lod", "label": "לוד", "terms": ("לוד", "lod"), "lat": 31.951, "lng": 34.888, "kind": "city"},
    {"key": "ramla", "label": "רמלה", "terms": ("רמלה", "ramla"), "lat": 31.929, "lng": 34.865, "kind": "city"},
    {
        "key": "rishon_lezion",
        "label": "ראשון לציון",
        "terms": ("ראשון לציון", "rishon lezion", "rishon letsiyon"),
        "lat": 31.973,
        "lng": 34.792,
        "kind": "city",
    },
    {"key": "ness_ziona", "label": "נס ציונה", "terms": ("נס ציונה", "ness ziona"), "lat": 31.930, "lng": 34.798, "kind": "city"},
    {"key": "gedera", "label": "גדרה", "terms": ("גדרה", "gedera"), "lat": 31.814, "lng": 34.779, "kind": "town"},
    {"key": "gan_yavne", "label": "גן יבנה", "terms": ("גן יבנה", "gan yavne"), "lat": 31.787, "lng": 34.706, "kind": "town"},
)

NEARBY_LOCATION_OPTIONS = (
    {"key": "ibim", "label": "איבים", "terms": ("איבים", "ibim"), "lat": 31.536, "lng": 34.609, "kind": "village"},
    {"key": "nir_am", "label": "ניר עם", "terms": ("ניר עם", "nir am"), "lat": 31.519, "lng": 34.580, "kind": "kibbutz"},
    {"key": "gevim", "label": "גבים", "terms": ("גבים", "gevim"), "lat": 31.507, "lng": 34.599, "kind": "kibbutz"},
    {"key": "or_haner", "label": "אור הנר", "terms": ("אור הנר", "or haner"), "lat": 31.558, "lng": 34.596, "kind": "kibbutz"},
    {"key": "mefalsim", "label": "מפלסים", "terms": ("מפלסים", "mefalsim"), "lat": 31.501, "lng": 34.562, "kind": "kibbutz"},
    {"key": "erez", "label": "ארז", "terms": ("ארז", "erez"), "lat": 31.560, "lng": 34.565, "kind": "kibbutz"},
    {"key": "yad_mordechai", "label": "יד מרדכי", "terms": ("יד מרדכי", "yad mordechai"), "lat": 31.588, "lng": 34.559, "kind": "kibbutz"},
    {"key": "netiv_haasara", "label": "נתיב העשרה", "terms": ("נתיב העשרה", "netiv haasara"), "lat": 31.572, "lng": 34.537, "kind": "moshav"},
    {"key": "zikim", "label": "זיקים", "terms": ("זיקים", "zikim"), "lat": 31.612, "lng": 34.522, "kind": "kibbutz"},
    {"key": "carmia", "label": "כרמיה", "terms": ("כרמיה", "carmia"), "lat": 31.604, "lng": 34.542, "kind": "kibbutz"},
    {"key": "kfar_aza", "label": "כפר עזה", "terms": ("כפר עזה", "kfar aza"), "lat": 31.484, "lng": 34.532, "kind": "kibbutz"},
    {"key": "saad", "label": "סעד", "terms": ("סעד", "saad"), "lat": 31.470, "lng": 34.536, "kind": "kibbutz"},
    {"key": "alumim", "label": "עלומים", "terms": ("עלומים", "alumim"), "lat": 31.454, "lng": 34.513, "kind": "kibbutz"},
    {"key": "nahal_oz", "label": "נחל עוז", "terms": ("נחל עוז", "nahal oz"), "lat": 31.472, "lng": 34.497, "kind": "kibbutz"},
    {"key": "tkuma", "label": "תקומה", "terms": ("תקומה", "tkuma"), "lat": 31.449, "lng": 34.583, "kind": "moshav"},
    {"key": "shuva", "label": "שובה", "terms": ("שובה", "shuva"), "lat": 31.450, "lng": 34.545, "kind": "moshav"},
    {"key": "beeri", "label": "בארי", "terms": ("בארי", "beeri"), "lat": 31.424, "lng": 34.491, "kind": "kibbutz"},
    {"key": "reim", "label": "רעים", "terms": ("רעים", "reim"), "lat": 31.386, "lng": 34.459, "kind": "kibbutz"},
    {"key": "yakhini", "label": "יכיני", "terms": ("יכיני", "yakhini"), "lat": 31.482, "lng": 34.602, "kind": "moshav"},
    {"key": "bror_hayil", "label": "ברור חיל", "terms": ("ברור חיל", "bror hayil"), "lat": 31.556, "lng": 34.648, "kind": "kibbutz"},
    {"key": "dorot", "label": "דורות", "terms": ("דורות", "dorot"), "lat": 31.506, "lng": 34.646, "kind": "kibbutz"},
    {"key": "ruhama", "label": "רוחמה", "terms": ("רוחמה", "ruhama"), "lat": 31.496, "lng": 34.705, "kind": "kibbutz"},
    {"key": "mabuim", "label": "מבועים", "terms": ("מבועים", "mabuim"), "lat": 31.448, "lng": 34.655, "kind": "moshav"},
    {"key": "gilat", "label": "גילת", "terms": ("גילת", "gilat"), "lat": 31.327, "lng": 34.649, "kind": "moshav"},
    {"key": "patish", "label": "פטיש", "terms": ("פטיש", "patish"), "lat": 31.326, "lng": 34.558, "kind": "moshav"},
)

LOCATION_OPTION_ALIASES = {
    str(option["key"]): tuple(str(term) for term in option["terms"])
    for option in (*DEFAULT_APPROVED_LOCATION_OPTIONS, *USER_APPROVABLE_LOCATION_OPTIONS, *NEARBY_LOCATION_OPTIONS)
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


def option_payload(option: dict[str, Any], locked: bool = False) -> dict[str, Any]:
    payload = {
        "key": option["key"],
        "label": option["label"],
        "terms": list(option["terms"]),
        "kind": option.get("kind", "city"),
    }
    if locked:
        payload["locked"] = True
    if "lat" in option and "lng" in option:
        payload["lat"] = option["lat"]
        payload["lng"] = option["lng"]
    return payload


def location_policy_payload() -> dict[str, Any]:
    default_approved = [option_payload(option, locked=True) for option in DEFAULT_APPROVED_LOCATION_OPTIONS]
    user_approvable = [option_payload(option) for option in USER_APPROVABLE_LOCATION_OPTIONS]
    nearby_options = [option_payload(option) for option in NEARBY_LOCATION_OPTIONS]
    return {
        "home": {"key": "sderot", "label": "שדרות", "lat": 31.525, "lng": 34.596},
        "map": {
            "bounds": {"min_lat": 29.45, "max_lat": 33.35, "min_lng": 34.25, "max_lng": 35.95},
            "focus_bounds": {"min_lat": 31.25, "max_lat": 31.95, "min_lng": 34.42, "max_lng": 34.90},
            "outline": [
                {"lat": 33.25, "lng": 35.55},
                {"lat": 32.85, "lng": 35.65},
                {"lat": 32.45, "lng": 35.55},
                {"lat": 31.78, "lng": 35.42},
                {"lat": 31.35, "lng": 35.28},
                {"lat": 30.75, "lng": 35.15},
                {"lat": 30.25, "lng": 35.00},
                {"lat": 29.55, "lng": 34.88},
                {"lat": 29.50, "lng": 34.73},
                {"lat": 30.55, "lng": 34.55},
                {"lat": 31.20, "lng": 34.74},
                {"lat": 31.70, "lng": 34.56},
                {"lat": 32.10, "lng": 34.58},
                {"lat": 32.65, "lng": 34.80},
                {"lat": 33.05, "lng": 35.05},
            ],
        },
        "default_approved": default_approved,
        "user_approvable": user_approvable,
        "nearby_options": nearby_options,
        "map_points": [
            *[dict(item, policy_group="default_approved") for item in default_approved],
            *[dict(item, policy_group="user_approvable") for item in user_approvable],
            *[dict(item, policy_group="nearby_options") for item in nearby_options],
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
