from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

try:
    from .job_records import (
        COMPANY,
        LINK,
        LOCATION,
        MANUAL_REQUIRED,
        PENDING,
        REJECTED,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        TITLE,
        job_key,
        score_int,
    )
    from .public_text import public_hebrew_text
except ImportError:
    from job_records import (
        COMPANY,
        LINK,
        LOCATION,
        MANUAL_REQUIRED,
        PENDING,
        REJECTED,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        TITLE,
        job_key,
        score_int,
    )
    from public_text import public_hebrew_text


@dataclass(frozen=True)
class BlockerRule:
    category: str
    label: str
    patterns: tuple[str, ...]
    recommendation: str
    priority: int


BLOCKER_RULES = (
    BlockerRule(
        category="security_gate",
        label="CAPTCHA / חסם אבטחה",
        patterns=("captcha", "recaptcha", "hcaptcha", "radware", "cloudflare"),
        recommendation="להשלים ידנית את שלב האבטחה או להגיש מהטלפון/המחשב של קורן.",
        priority=100,
    ),
    BlockerRule(
        category="manual_form",
        label="טופס שאינו ניתן להשלמה אוטומטית",
        patterns=("הגשה ידנית", "השלמה ידנית", "לא ניתן להשלים אוטומטית", "כלי העלאת הקובץ", "no direct form"),
        recommendation="להיכנס לקישור, להעלות את קובץ ה-CV המאושר ולסמן בדשבורד שהוגש ידנית.",
        priority=95,
    ),
    BlockerRule(
        category="site_adapter_gap",
        label="חסר adapter בטוח לאתר",
        patterns=("adapter", "sendcv", "jobnet direct", "drushim", "נדרש מעבר מנוע ההגשה"),
        recommendation="להעדיף טופס חברה רשמי; אם אין, להשאיר להגשה ידנית עד שנבנה adapter מאומת לאתר.",
        priority=90,
    ),
    BlockerRule(
        category="secondary_location",
        label="מיקום מחוץ למדיניות או מפסילות היסטוריות",
        patterns=("מיקום באזור משני", "ראשון לציון", "רחובות", "לוד", "רמלה", "נס ציונה", "יבנה"),
        recommendation="להסתמך על בחירות המיקום העדכניות בדשבורד; פסילות היסטוריות דורשות רענון ניקוד לפני החלטה.",
        priority=85,
    ),
    BlockerRule(
        category="unclear_location",
        label="מיקום לא מספיק ברור",
        patterns=("המיקום לא מספיק ברור", "מספר מקומות"),
        recommendation="לפתוח את המשרה ולבדוק מיקום אמיתי לפני הגשה.",
        priority=80,
    ),
    BlockerRule(
        category="experience_interpretation",
        label="פרשנות ניסיון",
        patterns=("3 שנים", "3 שנות", "שלוש שנים", "שלוש שנות", "2-3", "2–3", "שנתיים-שלוש", "ניסיון סביב 3", "ניסיון ככלכלן"),
        recommendation="להגיש רק אם אפשר להסביר בכנות שהניסיון התקציבי/רכש עומד בדרישת החובה.",
        priority=78,
    ),
    BlockerRule(
        category="system_skill_gap",
        label="מערכת/כלי שלא אומת",
        patterns=("sap", "erp", "mrp", "power bi", "ms project", "nibit", "פריוריטי", "priority"),
        recommendation="לא להגיש אוטומטית כשהכלי הוא דרישת חובה; אפשר לבדוק ידנית אם הוא רק יתרון.",
        priority=76,
    ),
    BlockerRule(
        category="temporary_or_scope",
        label="זמני או מחוץ לליבת היעד",
        patterns=("זמני", "זמנית", "חל\"ד", "החלפה", "מחסן", "מכירות", "שירות לקוחות", "הנהלת חשבונות"),
        recommendation="להגיש רק אם התפקיד מתאים במיוחד ויש סיכוי ממשי להמשך.",
        priority=60,
    ),
    BlockerRule(
        category="policy_or_missing_fact",
        label="מידע חסר או הצהרה",
        patterns=("שכר", "הצהרה", "אימות", "קוד", "מקור פרסום", "סיווג", "שאלת סינון", "דרישת חובה לא ודאית"),
        recommendation="לא לענות בשם קורן בלי אישור עובדתי מפורש.",
        priority=72,
    ),
    BlockerRule(
        category="low_score_or_hard_reject",
        label="התאמה נמוכה או חסם קשיח",
        patterns=("מתחת לסף", "נפסל", "דרישת הניסיון גבוהה", "אינו באזורי החיפוש", "משרה סגורה"),
        recommendation="לא להשקיע בהגשה; עדיף להרחיב מקורות או קריטריונים מאושרים.",
        priority=20,
    ),
)


def row_text(row: dict[str, str]) -> str:
    return " ".join(
        str(row.get(field, ""))
        for field in (COMPANY, TITLE, LOCATION, STATUS, STOP_REASON)
    ).lower()


def categories_for_row(row: dict[str, str]) -> list[BlockerRule]:
    text = row_text(row)
    matches = [
        rule
        for rule in BLOCKER_RULES
        if any(pattern.lower() in text for pattern in rule.patterns)
    ]
    if matches:
        return sorted(matches, key=lambda rule: rule.priority, reverse=True)
    if row.get(STATUS) == MANUAL_REQUIRED:
        return [
            BlockerRule(
                category="manual_form",
                label="טופס שאינו ניתן להשלמה אוטומטית",
                patterns=(),
                recommendation="להיכנס לקישור, להעלות את קובץ ה-CV המאושר ולסמן בדשבורד שהוגש ידנית.",
                priority=95,
            )
        ]
    if row.get(STATUS) == PENDING:
        return [
            BlockerRule(
                category="policy_or_missing_fact",
                label="מידע חסר או הצהרה",
                patterns=(),
                recommendation="לא לענות בשם קורן בלי אישור עובדתי מפורש.",
                priority=72,
            )
        ]
    return []


def compact_job(row: dict[str, str], category: str = "") -> dict[str, Any]:
    return {
        "key": job_key(row),
        "score": score_int(row),
        "company": row.get(COMPANY, ""),
        "title": row.get(TITLE, ""),
        "location": row.get(LOCATION, ""),
        "link": row.get(LINK, ""),
        "status": row.get(STATUS, ""),
        "category": category,
        "reason": public_hebrew_text(row.get(STOP_REASON, ""))[:360],
    }


def top_rows(rows: list[dict[str, str]], status: str, categories: set[str] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    selected: list[tuple[BlockerRule, dict[str, str]]] = []
    for row in rows:
        if row.get(STATUS) != status:
            continue
        rules = categories_for_row(row)
        if not rules:
            continue
        primary = rules[0]
        if categories and primary.category not in categories:
            continue
        selected.append((primary, row))
    selected.sort(key=lambda item: (score_int(item[1]), item[0].priority), reverse=True)
    return [compact_job(row, primary.category) for primary, row in selected[:limit]]


def blocker_counts(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    labels: dict[str, str] = {}
    recommendations: dict[str, str] = {}
    highest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get(STATUS) not in {PENDING, MANUAL_REQUIRED, REJECTED}:
            continue
        rules = categories_for_row(row)
        if not rules:
            continue
        primary = rules[0]
        counter[primary.category] += 1
        labels[primary.category] = primary.label
        recommendations[primary.category] = primary.recommendation
        current = highest.get(primary.category)
        if current is None or score_int(row) > int(current["score"]):
            highest[primary.category] = compact_job(row, primary.category)

    return [
        {
            "category": category,
            "label": labels[category],
            "count": count,
            "recommendation": recommendations[category],
            "sample_job": highest.get(category, {}),
        }
        for category, count in counter.most_common()
    ]


def build_next_actions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    manual = top_rows(rows, MANUAL_REQUIRED, limit=5)
    location = top_rows(rows, PENDING, {"unclear_location"}, limit=5)
    experience = top_rows(rows, PENDING, {"experience_interpretation"}, limit=5)
    systems = top_rows(rows, PENDING, {"system_skill_gap"}, limit=5)
    adapter = top_rows(rows, PENDING, {"site_adapter_gap"}, limit=5)

    actions: list[dict[str, Any]] = []
    if manual:
        actions.append(
            {
                "title": "להשלים קודם משרות ידניות עם ציון גבוה",
                "impact": f"{len(manual)} משרות מובילות כבר עברו התאמה ונעצרו בעיקר בגלל CAPTCHA, חסם אתר או העלאת קובץ.",
                "recommendation": "לפתוח מהדשבורד, להגיש ידנית עם ה-CV המאושר, ואז לסמן כהוגש ידנית.",
                "jobs": manual,
            }
        )
    if location:
        actions.append(
            {
                "title": "לברר רק מיקומים לא ברורים",
                "impact": f"{len(location)} משרות מובילות נעצרו כי המיקום לא מספיק ברור.",
                "recommendation": "לסנכרן את בחירות המיקום מהדשבורד ולרענן ניקוד לפני שמסמנים מיקום כפסול.",
                "jobs": location,
            }
        )
    if experience:
        actions.append(
            {
                "title": "למפות ניסיון גבולי לדרישות חובה",
                "impact": f"{len(experience)} משרות מובילות נעצרו בגלל דרישת ניסיון סביב 3 שנים או תיאור תפקיד כלכלי.",
                "recommendation": "לקבל מקורן ניסוח עובדתי שמבהיר אילו שנות ניסיון רכש/תקציבים אפשר להציג בביטחון.",
                "jobs": experience,
            }
        )
    if systems:
        actions.append(
            {
                "title": "לבדוק כלים שלא אומתו",
                "impact": f"{len(systems)} משרות מובילות כוללות כלי כמו SAP/ERP/MRP/Power BI או Priority.",
                "recommendation": "SAP/ERP/MRP לא מאושרים ולכן לא מגישים כשהם חובה; אם הכלי רק יתרון, אפשר לשקול הגשה ידנית.",
                "jobs": systems,
            }
        )
    if adapter:
        actions.append(
            {
                "title": "להמיר מודעות מטופס מתווך לטופס חברה",
                "impact": f"{len(adapter)} משרות מובילות הגיעו ממקור שעדיין אין לו הגשה אוטומטית בטוחה.",
                "recommendation": "לחפש את אותה משרה באתר החברה הרשמי ולהגיש משם כשאין CAPTCHA או שאלות חסרות.",
                "jobs": adapter,
            }
        )

    if not actions:
        actions.append(
            {
                "title": "להרחיב מקורות חיפוש",
                "impact": "אין כרגע משרות פעולה מובילות מתוך המאגר הקיים.",
                "recommendation": "להוסיף סריקה ישירה של אתרי קריירה רשמיים וחיפושי web ממוקדים בדרום.",
                "jobs": [],
            }
        )
    return actions[:5]


def build_insights(rows: list[dict[str, str]]) -> dict[str, Any]:
    counts = Counter(row.get(STATUS, "") for row in rows)
    high_action_rows = [
        row
        for row in rows
        if row.get(STATUS) in {PENDING, MANUAL_REQUIRED} and score_int(row) >= 70
    ]
    return {
        "snapshot": {
            "submitted": counts[SUBMITTED],
            "pending": counts[PENDING],
            "manual_required": counts[MANUAL_REQUIRED],
            "rejected": counts[REJECTED],
            "high_score_actionable": len(high_action_rows),
            "safe_auto_submit_now": 0,
        },
        "blocker_counts": blocker_counts(rows),
        "next_actions": build_next_actions(rows),
    }
