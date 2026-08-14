from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

try:
    from .job_records import CV, LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, STOP_REASON, SUBMITTED, job_key, load_rows, write_rows
    from .public_text import public_hebrew_text
    from .submission_engine import SubmissionDecision
except ImportError:
    from job_records import CV, LINK, MANUAL_REQUIRED, PENDING, REJECTED, STATUS, STOP_REASON, SUBMITTED, job_key, load_rows, write_rows
    from public_text import public_hebrew_text
    from submission_engine import SubmissionDecision


PROTECTED_REASON_MARKERS = (
    "dashboard",
    "Manual gate:",
    "Manual submission required:",
    "Official fallback checked",
    "נדרשת הגשה ידנית:",
    "נבדק fallback רשמי",
    "Rejected:",
    "הוגש ידנית",
    "הוגש בהצלחה",
    "בחירה ידנית",
    "לאחר בדיקת מקור רשמי",
    "נדרש השלמה ידנית",
    "נעצר:",
)


@dataclass
class SyncStats:
    rows_seen: int = 0
    plans_seen: int = 0
    changed: int = 0
    marked_rejected: int = 0
    marked_manual_required: int = 0
    marked_pending_policy: int = 0
    marked_pending_adapter_gap: int = 0
    skipped_submitted: int = 0
    skipped_protected: int = 0


def _plan_by_key(plans: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for plan in plans:
        key = str(plan.get("job", {}).get("key", "")).strip()
        if key:
            result[key] = plan
    return result


def _protected(row: dict[str, str]) -> bool:
    reason = row.get(STOP_REASON, "")
    return any(marker in reason for marker in PROTECTED_REASON_MARKERS)


def _clean_reason(plan: dict) -> str:
    reason = str(plan.get("reason", "") or "").strip()
    next_step = str(plan.get("next_step", "") or "").strip()
    if " Next:" in reason:
        return public_hebrew_text(reason)
    if reason and next_step:
        return public_hebrew_text(f"{reason} Next: {next_step}")
    return public_hebrew_text(reason or next_step)


def _with_prefix(prefix: str, reason: str) -> str:
    return reason if reason.startswith(prefix) else f"{prefix} {reason}"


def _target_for_decision(plan: dict) -> tuple[str | None, str | None, str | None]:
    decision = str(plan.get("decision", "") or "")
    reason = _clean_reason(plan)
    if decision == SubmissionDecision.DO_NOT_APPLY.value:
        return REJECTED, _with_prefix("נפסל:", reason), ""
    if decision == SubmissionDecision.HUMAN_GATE.value:
        return MANUAL_REQUIRED, _with_prefix("נדרשת הגשה ידנית:", reason), "לא צורף - נדרשת השלמה ידנית"
    if decision == SubmissionDecision.POLICY_REQUIRED.value:
        return PENDING, _with_prefix("נדרש אישור לפני הגשה:", reason), None
    if decision == SubmissionDecision.NOT_SUPPORTED.value:
        return PENDING, _with_prefix("חסר adapter בטוח לאתר:", reason), None
    return None, None, None


def sync_rows(rows: list[dict[str, str]], plans: list[dict]) -> SyncStats:
    stats = SyncStats(rows_seen=len(rows), plans_seen=len(plans))
    plans_by_key = _plan_by_key(plans)
    for row in rows:
        if row.get(STATUS) == SUBMITTED:
            stats.skipped_submitted += 1
            continue
        plan = plans_by_key.get(job_key(row))
        if not plan:
            continue
        target_status, target_reason, target_cv = _target_for_decision(plan)
        if not target_status or not target_reason:
            continue
        if row.get(STATUS) == MANUAL_REQUIRED and target_status != MANUAL_REQUIRED:
            stats.skipped_protected += 1
            continue
        if row.get(STATUS) == REJECTED and target_status != REJECTED:
            stats.skipped_protected += 1
            continue
        if _protected(row) and row.get(STATUS) in {REJECTED, MANUAL_REQUIRED}:
            stats.skipped_protected += 1
            continue

        changed = False
        if row.get(STATUS) != target_status:
            row[STATUS] = target_status
            changed = True
        if row.get(STOP_REASON, "") != target_reason:
            row[STOP_REASON] = target_reason
            changed = True
        if target_cv is not None and row.get(CV, "") != target_cv:
            row[CV] = target_cv
            changed = True
        if changed:
            stats.changed += 1
            if target_status == REJECTED:
                stats.marked_rejected += 1
            elif target_status == MANUAL_REQUIRED:
                stats.marked_manual_required += 1
            elif target_status == PENDING and str(plan.get("decision")) == SubmissionDecision.POLICY_REQUIRED.value:
                stats.marked_pending_policy += 1
            elif target_status == PENDING:
                stats.marked_pending_adapter_gap += 1
    return stats


def load_plans(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, list) else []


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync submission-engine decisions back into the CSV tracker.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--plan", type=Path, default=Path("outputs/submission_engine_plan.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.csv)
    plans = load_plans(args.plan)
    before = Counter(row.get(STATUS, "") for row in rows)
    stats = sync_rows(rows, plans)
    after = Counter(row.get(STATUS, "") for row in rows)
    if stats.changed and not args.dry_run:
        write_rows(args.csv, rows)
    print_json({"stats": asdict(stats), "before": dict(before), "after": dict(after), "dry_run": args.dry_run})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
