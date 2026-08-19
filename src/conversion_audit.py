from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .action_insights import build_insights
    from .job_records import LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, SUBMITTED, load_rows, summarize_counts
except ImportError:
    from action_insights import build_insights
    from job_records import LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, SUBMITTED, load_rows, summarize_counts


def source_from_link(link: str) -> str:
    lowered = (link or "").lower()
    if "jobmaster.co.il" in lowered:
        return "JobMaster"
    if "drushim.co.il" in lowered:
        return "Drushim"
    if "alljobs.co.il" in lowered:
        return "AllJobs"
    if "jobnet.co.il" in lowered:
        return "Jobnet"
    if "linkedin." in lowered:
        return "LinkedIn"
    if "jobs.iai.co.il" in lowered:
        return "IAI official"
    if "jobs.dsv.com" in lowered:
        return "DSV official"
    if "nestle" in lowered:
        return "Nestle official"
    return "Other/company"


def pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, list) else []


def parse_summary_scanned(path: Path, default: int) -> int:
    if not path.exists():
        return default
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if "מספר המשרות שנסרקו" in line:
            digits = "".join(ch for ch in line.split(":", 1)[-1] if ch.isdigit())
            return int(digits) if digits else default
    return default


def build_source_quality(rows: list[dict[str, str]]) -> list[dict]:
    by_source: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        src = source_from_link(row.get(LINK, ""))
        by_source[src]["total"] += 1
        by_source[src][row.get(STATUS, "")] += 1
    result = []
    for src, counts in by_source.items():
        total = counts["total"]
        submitted = counts[SUBMITTED]
        actionable = counts[PENDING] + counts[MANUAL_REQUIRED]
        result.append(
            {
                "source": src,
                "total": total,
                "submitted": submitted,
                "pending": counts[PENDING],
                "manual_required": counts[MANUAL_REQUIRED],
                "rejected": counts[REJECTED],
                "submission_rate": pct(submitted, total),
                "actionable_rate": pct(actionable, total),
            }
        )
    return sorted(result, key=lambda item: (item["submitted"], item["actionable_rate"], -item["rejected"]), reverse=True)


def plan_summary(plans: list[dict]) -> dict:
    decisions = Counter(str(plan.get("decision", "")) for plan in plans)
    sites = Counter(str(plan.get("site", "")) for plan in plans)
    return {
        "plans": len(plans),
        "runnable": sum(1 for plan in plans if plan.get("can_attempt")),
        "decisions": dict(decisions),
        "sites": dict(sites),
    }


def retry_summary(retry_items: list[dict]) -> dict:
    return {
        "items": len(retry_items),
        "modes": dict(Counter(str(item.get("mode", "")) for item in retry_items)),
        "sites": dict(Counter(str(item.get("site", "")) for item in retry_items)),
    }


def recommendations(audit: dict) -> list[str]:
    recs: list[str] = []
    plan = audit["submission_plan"]
    blockers = audit["insights"].get("blocker_counts", [])
    blocker_by_category = {item["category"]: item["count"] for item in blockers}
    if plan["runnable"] == 0:
        recs.append("אין כרגע משרות בטוחות להגשה אוטומטית; עדיף להסיר חסמי מדיניות/אתר לפני הרחבת סריקה נוספת.")
    if blocker_by_category.get("secondary_location", 0) >= 20:
        recs.append("קיימות פסילות מיקום היסטוריות רבות; יש להסתמך על בחירות המיקום העדכניות מהדשבורד ולרענן ניקוד לפני החלטת הגשה.")
    if blocker_by_category.get("site_adapter_gap", 0) >= 5:
        recs.append("לתעדף fallback לאתרי חברה עבור Drushim ו-Jobnet במקום לסרוק שוב ושוב את אותם אגרגטורים.")
    if blocker_by_category.get("security_gate", 0) > 0:
        recs.append("משרות עם CAPTCHA/Radware יישארו בהעברה ידנית; אין לנסות לעקוף חסמי אבטחה.")
    if blocker_by_category.get("system_skill_gap", 0) >= 10:
        recs.append("להמשיך להחמיר בזיהוי מערכות חובה; SAP/ERP/MRP נשארים חסם כשזו דרישת חובה, ולשאול רק כשמדובר ביתרון לא ברור.")
    return recs[:8]


def build_audit(rows: list[dict[str, str]], scanned: int, plans: list[dict], retry_items: list[dict]) -> dict:
    row_counts = summarize_counts(rows)
    insights = build_insights(rows)
    audit = {
        "counts": {
            **row_counts,
            "scanned": scanned,
            "documented_rate_from_scanned": pct(row_counts["total"], scanned),
            "suitable_rate_from_documented": pct(row_counts["suitable"], row_counts["total"]),
            "submitted_rate_from_suitable": pct(row_counts["submitted"], row_counts["suitable"]),
            "submitted_rate_from_documented": pct(row_counts["submitted"], row_counts["total"]),
        },
        "submission_plan": plan_summary(plans),
        "retry_queue": retry_summary(retry_items),
        "source_quality": build_source_quality(rows),
        "insights": insights,
    }
    audit["recommendations"] = recommendations(audit)
    return audit


def render_markdown(audit: dict) -> str:
    counts = audit["counts"]
    lines = [
        "# בדיקת המרות מהסריקה להגשה",
        "",
        "## משפך",
        "",
        f"- נסרקו: {counts['scanned']}",
        f"- תועדו: {counts['total']} ({counts['documented_rate_from_scanned']}% מהנסרקות)",
        f"- מתאימות או דורשות פעולה: {counts['suitable']} ({counts['suitable_rate_from_documented']}% מהמתועדות)",
        f"- הוגשו: {counts['submitted']} ({counts['submitted_rate_from_suitable']}% מהמתאימות; {counts['submitted_rate_from_documented']}% מהמתועדות)",
        f"- ממתינות לאישור: {counts['pending']}",
        f"- דורשות הגשה ידנית: {counts['manual_required']}",
        f"- נפסלו: {counts['rejected']}",
        "",
        "## מנוע ההגשה",
        "",
        f"- החלטות: {audit['submission_plan']['plans']}",
        f"- ניתנות לטיפול כעת: {audit['submission_plan']['runnable']}",
    ]
    for decision, count in sorted(audit["submission_plan"]["decisions"].items()):
        lines.append(f"- `{decision}`: {count}")

    lines.extend(["", "## חסמים מרכזיים", ""])
    for blocker in audit["insights"].get("blocker_counts", [])[:10]:
        lines.append(f"- {blocker['category']}: {blocker['count']} - {blocker['recommendation']}")

    lines.extend(["", "## איכות מקורות", ""])
    for item in audit["source_quality"]:
        lines.append(
            f"- {item['source']}: סה\"כ {item['total']}, הוגשו {item['submitted']}, "
            f"ממתינות {item['pending']}, ידניות {item['manual_required']}, נפסלו {item['rejected']}, "
            f"שיעור הגשה {item['submission_rate']}%"
        )

    lines.extend(["", "## המלצות", ""])
    for recommendation in audit["recommendations"]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines) + "\n"


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze why scans are not converting into submissions.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--submission-plan", type=Path, default=Path("outputs/submission_engine_plan.json"))
    parser.add_argument("--retry-queue", type=Path, default=Path("outputs/retry_queue.json"))
    parser.add_argument("--json", type=Path, default=Path("outputs/conversion_audit.json"))
    parser.add_argument("--md", type=Path, default=Path("outputs/conversion_audit.md"))
    args = parser.parse_args()

    rows = load_rows(args.csv)
    scanned = parse_summary_scanned(args.summary, default=len(rows))
    audit = build_audit(rows, scanned, load_json_list(args.submission_plan), load_json_list(args.retry_queue))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    args.md.write_text(render_markdown(audit), encoding="utf-8")
    print_json({"ok": True, "json": str(args.json), "md": str(args.md), "recommendations": audit["recommendations"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
