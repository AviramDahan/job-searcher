from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .candidate_profile import KOREN_DAHAN_PROFILE, assess_candidate_facts
    from .job_records import COMPANY, LINK, MANUAL_REQUIRED, PENDING, REQUIREMENTS, STATUS, STOP_REASON, TITLE, load_rows, write_rows
    from .site_adapters import route_submission_failure
    from .submission_failures import FailureKind
except ImportError:
    from candidate_profile import KOREN_DAHAN_PROFILE, assess_candidate_facts
    from job_records import COMPANY, LINK, MANUAL_REQUIRED, PENDING, REQUIREMENTS, STATUS, STOP_REASON, TITLE, load_rows, write_rows
    from site_adapters import route_submission_failure
    from submission_failures import FailureKind


MANUAL_REQUIRED_FAILURES = {
    FailureKind.CAPTCHA_OR_SECURITY,
    FailureKind.FORM_AUTOMATION_UNRELIABLE,
    FailureKind.NO_DIRECT_FORM,
}


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def fact_context(row: dict[str, str]) -> str:
    return " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, ""), row.get(TITLE, "")] if part)


def should_mark_manual_required(row: dict[str, str]) -> bool:
    if row.get(STATUS) != PENDING:
        return False

    assessment = assess_candidate_facts(fact_context(row), profile=KOREN_DAHAN_PROFILE)
    if assessment.has_disqualifying_blocker or assessment.first_blocker:
        return False

    route = route_submission_failure(
        reason=" ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, "")] if part),
        link=row.get(LINK, ""),
        title=row.get(TITLE, ""),
        company=row.get(COMPANY, ""),
    )
    signals = set(route.failure.signals or (route.failure.kind,))
    return bool(signals & MANUAL_REQUIRED_FAILURES)


def categorize_rows(rows: list[dict[str, str]]) -> int:
    changed = 0
    for row in rows:
        if should_mark_manual_required(row):
            row[STATUS] = MANUAL_REQUIRED
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Move true site-blocked applications into the manual-submission-required status.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    args = parser.parse_args()

    rows = load_rows(args.csv)
    changed = categorize_rows(rows)
    if changed:
        write_rows(args.csv, rows)
    print_json({"changed": changed, "csv": str(args.csv)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
