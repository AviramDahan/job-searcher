from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DATE = "תאריך"
COMPANY = "חברה"
TITLE = "שם המשרה"
LOCATION = "מיקום"
LINK = "קישור"
SCORE = "ציון התאמה"
REQUIREMENTS = "דרישות מרכזיות"
FIT = "סיבות להתאמה"
STATUS = "סטטוס"
STOP_REASON = "סיבת פסילה או עצירה"
COVER = "נוסח הפנייה שנשלח"
CV = "שם קובץ קורות החיים שצורף"

HEADERS = [
    DATE,
    COMPANY,
    TITLE,
    LOCATION,
    LINK,
    SCORE,
    REQUIREMENTS,
    FIT,
    STATUS,
    STOP_REASON,
    COVER,
    CV,
]

SUBMITTED = "הוגש"
PENDING = "נדרש אישור"
MANUAL_REQUIRED = "נדרשת הגשה ידנית"
REJECTED = "נפסל"

ACTION_REQUIRED_STATUSES = {PENDING, MANUAL_REQUIRED}
SUITABLE_STATUSES = {SUBMITTED, PENDING, MANUAL_REQUIRED}


def is_action_required_status(status: str) -> bool:
    return status in ACTION_REQUIRED_STATUSES


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def job_key(row: dict[str, str]) -> str:
    link = row.get(LINK, "")
    parsed = urlparse(link)
    query = parse_qs(parsed.query)

    if "key" in query and query["key"]:
        return f"jobmaster:{query['key'][0]}"
    if "JobID" in query and query["JobID"]:
        return f"alljobs:{query['JobID'][0]}"
    if "positionid" in query and query["positionid"]:
        return f"jobnet:{query['positionid'][0]}"

    linkedin_id = re.search(r"-(\d{8,})(?:\?|$)", link)
    if linkedin_id and "linkedin." in parsed.netloc:
        return f"linkedin:{linkedin_id.group(1)}"

    nestle_id = re.search(r"/(\d+)/?$", parsed.path)
    if nestle_id and parsed.netloc.lower() == "jobdetails.nestle.com":
        return f"nestle:{nestle_id.group(1)}"

    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return "manual:" + "|".join(
        [
            base_url,
            normalize_text(row.get(COMPANY, "")),
            normalize_text(row.get(TITLE, "")),
            normalize_text(row.get(LOCATION, "")),
        ]
    )


def score_int(row: dict[str, str]) -> int:
    try:
        return int(row.get(SCORE, "0") or "0")
    except ValueError:
        return 0


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def upsert(rows: list[dict[str, str]], row: dict[str, str]) -> bool:
    key = job_key(row)
    for existing in rows:
        if job_key(existing) == key:
            existing.update(row)
            return False
    rows.append(row)
    return True


def duplicate_keys(rows: list[dict[str, str]]) -> list[str]:
    counts = Counter(job_key(row) for row in rows)
    return [key for key, count in counts.items() if count > 1]


def summarize_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter(row.get(STATUS, "") for row in rows)
    return {
        "total": len(rows),
        "submitted": counts[SUBMITTED],
        "pending": counts[PENDING],
        "manual_required": counts[MANUAL_REQUIRED],
        "rejected": counts[REJECTED],
        "suitable": sum(counts[status] for status in SUITABLE_STATUSES),
        "duplicate_keys": len(duplicate_keys(rows)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize job application CSV files.")
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()

    rows = load_rows(args.csv_path)
    print(json.dumps(summarize_counts(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
