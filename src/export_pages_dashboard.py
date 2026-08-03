from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .action_insights import build_insights
    from .job_records import COMPANY, CV, DATE, FIT, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, SUITABLE_STATUSES, TITLE, job_key, load_rows
except ImportError:
    from action_insights import build_insights
    from job_records import COMPANY, CV, DATE, FIT, LINK, LOCATION, MANUAL_REQUIRED, PENDING, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, SUBMITTED, SUITABLE_STATUSES, TITLE, job_key, load_rows


DEFAULT_TIMEZONE = "Asia/Jerusalem"


def score_value(value: str) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def now_string(timezone: str = DEFAULT_TIMEZONE) -> str:
    return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")


def parse_summary_count(path: Path, label: str, default: int) -> int:
    if not path.exists():
        return default
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if label in line:
            digits = "".join(char for char in line.split(":", 1)[-1] if char.isdigit())
            return int(digits) if digits else default
    return default


def serialize_row(row: dict[str, str]) -> dict[str, str | int]:
    return {
        "key": job_key(row),
        "date": row.get(DATE, ""),
        "company": row.get(COMPANY, ""),
        "title": row.get(TITLE, ""),
        "location": row.get(LOCATION, ""),
        "link": row.get(LINK, ""),
        "score": score_value(row.get(SCORE, "")),
        "requirements": row.get(REQUIREMENTS, ""),
        "fit": row.get(FIT, ""),
        "status": row.get(STATUS, ""),
        "stop_reason": row.get(STOP_REASON, ""),
        "cv": row.get(CV, ""),
    }


def build_payload(csv_path: Path, summary_path: Path, candidate_name: str, timezone: str = DEFAULT_TIMEZONE) -> dict:
    rows = load_rows(csv_path)
    counts = Counter(row.get(STATUS, "") for row in rows)
    scanned = parse_summary_count(summary_path, "מספר המשרות שנסרקו", default=len(rows))
    jobs = sorted((serialize_row(row) for row in rows), key=lambda item: (int(item["score"]), str(item["date"])), reverse=True)
    return {
        "generated_at": now_string(timezone),
        "candidate": {"full_name": candidate_name},
        "counts": {
            "scanned": scanned,
            "documented": len(rows),
            "submitted": counts[SUBMITTED],
            "pending": counts[PENDING],
            "manual_required": counts[MANUAL_REQUIRED],
            "rejected": counts[REJECTED],
            "suitable": sum(counts[status] for status in SUITABLE_STATUSES),
        },
        "insights": build_insights(rows),
        "jobs": jobs,
    }


def write_payload(payload: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a read-only GitHub Pages dashboard snapshot.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--out", type=Path, default=Path("docs/assets/job-data.json"))
    parser.add_argument("--candidate-name", default="קורן דהן")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    payload = build_payload(args.csv, args.summary, args.candidate_name, args.timezone)
    write_payload(payload, args.out)
    print(json.dumps({"ok": True, "out": str(args.out), "jobs": len(payload["jobs"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
