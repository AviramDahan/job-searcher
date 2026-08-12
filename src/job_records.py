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
BROKEN_QUESTION_RUN_RE = re.compile(r"\?{3,}")

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
    if "tfaforms.com" in parsed.netloc.lower() and "tfa_4776808320092" in query and query["tfa_4776808320092"]:
        return f"bgu:{query['tfa_4776808320092'][0]}"

    drushim_id = re.search(r"/job/(\d+)(?:/|$)", parsed.path)
    if drushim_id and "drushim.co.il" in parsed.netloc.lower():
        return f"drushim:{drushim_id.group(1)}"

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


def sanitize_field_value(value: object) -> str:
    cleaned = BROKEN_QUESTION_RUN_RE.sub("", str(value or ""))
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def sanitize_row(row: dict[str, str]) -> dict[str, str]:
    return {header: sanitize_field_value(row.get(header, "")) for header in HEADERS}


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(sanitize_row(row) for row in rows)


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


def _duplicate_rank(row: dict[str, str]) -> tuple[int, int, int]:
    status_rank = {
        SUBMITTED: 4,
        MANUAL_REQUIRED: 3,
        PENDING: 2,
        REJECTED: 1,
    }
    filled_fields = sum(1 for value in row.values() if value)
    return (status_rank.get(row.get(STATUS, ""), 0), score_int(row), filled_fields)


def deduplicate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best_by_key: dict[str, dict[str, str]] = {}
    ordered_keys: list[str] = []
    for row in rows:
        key = job_key(row)
        if key not in best_by_key:
            best_by_key[key] = row
            ordered_keys.append(key)
            continue
        if _duplicate_rank(row) > _duplicate_rank(best_by_key[key]):
            best_by_key[key] = row
    return [best_by_key[key] for key in ordered_keys]


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
    parser.add_argument("--dedupe", action="store_true", help="Remove duplicate rows using stable job keys.")
    args = parser.parse_args()

    rows = load_rows(args.csv_path)
    before = len(rows)
    if args.dedupe:
        rows = deduplicate_rows(rows)
        write_rows(args.csv_path, rows)
    payload = summarize_counts(rows)
    if args.dedupe:
        payload["deduplicated_rows_removed"] = before - len(rows)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
