from __future__ import annotations

import argparse
import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

try:
    from .candidate_profile import CandidateProfile, FactIssueSeverity, KOREN_DAHAN_PROFILE, assess_candidate_facts
    from .job_records import COMPANY, FIT, LINK, LOCATION, PENDING, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, job_key, load_rows
    from .send_job_status_alerts import build_message, send
    from .site_adapters import route_submission_failure
    from .submission_failures import FailureKind
except ImportError:
    from candidate_profile import CandidateProfile, FactIssueSeverity, KOREN_DAHAN_PROFILE, assess_candidate_facts
    from job_records import COMPANY, FIT, LINK, LOCATION, PENDING, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, job_key, load_rows
    from send_job_status_alerts import build_message, send
    from site_adapters import route_submission_failure
    from submission_failures import FailureKind


HUMAN_ALERT_FAILURES = {
    FailureKind.CAPTCHA_OR_SECURITY,
    FailureKind.MARKETING_CONSENT,
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.SALARY_REQUIRED,
    FailureKind.WORK_MODEL_UNKNOWN,
    FailureKind.EXPERIENCE_AMBIGUITY,
    FailureKind.UNKNOWN,
}

GENERIC_POLICY_BLOCKER_SIGNALS = {
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.SALARY_REQUIRED,
    FailureKind.WORK_MODEL_UNKNOWN,
    FailureKind.EXPERIENCE_AMBIGUITY,
}


@dataclass(frozen=True)
class ManualAlertDecision:
    should_alert: bool
    log_mode: str
    blocker: str
    recommendation: str


def load_log(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        return data
    return {item["key"]: item for item in data if isinstance(item, dict) and "key" in item}


def fact_context(row: dict[str, str]) -> str:
    return " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, ""), row.get(TITLE, "")] if part)


def manual_alert_decision(row: dict[str, str], profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> ManualAlertDecision:
    assessment = assess_candidate_facts(fact_context(row), profile=profile)
    candidate_blocker = assessment.first_blocker
    marketing_consent_resolved = any(issue.code == "marketing_consent_approved" for issue in assessment.resolved)
    if candidate_blocker and candidate_blocker.severity == FactIssueSeverity.DO_NOT_APPLY:
        return ManualAlertDecision(
            should_alert=False,
            log_mode="skipped_profile_mismatch",
            blocker=candidate_blocker.reason,
            recommendation=candidate_blocker.next_step,
        )

    if candidate_blocker:
        return ManualAlertDecision(
            should_alert=True,
            log_mode="sent",
            blocker=candidate_blocker.reason,
            recommendation=candidate_blocker.next_step,
        )

    context_reason = " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, "")] if part)
    route = route_submission_failure(
        reason=context_reason,
        link=row.get(LINK, ""),
        title=row.get(TITLE, ""),
        company=row.get(COMPANY, ""),
    )
    generic_policy_signal = next((signal for signal in route.failure.signals if signal in GENERIC_POLICY_BLOCKER_SIGNALS), None)
    if generic_policy_signal:
        return ManualAlertDecision(
            should_alert=True,
            log_mode="sent",
            blocker=row.get(STOP_REASON, "") or route.failure.reason,
            recommendation="Verify the flagged requirement or policy item before retrying the application.",
        )

    if (
        route.failure.kind in {FailureKind.SENSITIVE_FIELD, FailureKind.UNVERIFIED_SYSTEM_SKILL}
        and assessment.resolved
        and not assessment.blockers
    ):
        return ManualAlertDecision(
            should_alert=False,
            log_mode="skipped_resolved_candidate_fact",
            blocker=route.failure.reason,
            recommendation="Use the verified candidate profile answers and retry the application flow instead of sending a manual handoff.",
        )

    if route.failure.kind == FailureKind.MARKETING_CONSENT and marketing_consent_resolved:
        return ManualAlertDecision(
            should_alert=False,
            log_mode="skipped_retryable",
            blocker=route.failure.reason,
            recommendation="Marketing/third-party consent is approved in the local profile; retry the Drushim application flow.",
        )

    if route.failure.kind in {FailureKind.LOGIN_OR_ACCOUNT, FailureKind.FORM_AUTOMATION_UNRELIABLE, FailureKind.NO_DIRECT_FORM}:
        return ManualAlertDecision(
            should_alert=False,
            log_mode="skipped_retryable",
            blocker=route.failure.reason,
            recommendation=route.failure.next_step,
        )

    if route.failure.kind in HUMAN_ALERT_FAILURES:
        return ManualAlertDecision(
            should_alert=True,
            log_mode="sent",
            blocker=row.get(STOP_REASON, "") or route.failure.reason,
            recommendation=route.failure.next_step,
        )

    return ManualAlertDecision(
        should_alert=True,
        log_mode="sent",
        blocker=row.get(STOP_REASON, "") or route.failure.reason,
        recommendation="להשלים ידנית רק לאחר אימות המידע החסר מול המועמדת או מול טופס החברה.",
    )


def build_manual_alert(row: dict[str, str], decision: ManualAlertDecision | None = None) -> dict:
    decision = decision or manual_alert_decision(row)
    return {
        "kind": "manual",
        "company": row.get(COMPANY, ""),
        "title": row.get(TITLE, ""),
        "link": row.get(LINK, ""),
        "score": row.get(SCORE, ""),
        "matched_requirements": row.get(FIT, ""),
        "company_info": f"מיקום: {row.get(LOCATION, '')}",
        "blocker": decision.blocker,
        "recommendation": decision.recommendation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Telegram alerts for pending manual jobs in the CSV.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--log", type=Path, default=Path("outputs/manual_alert_log.json"))
    parser.add_argument("--mark-existing", action="store_true")
    parser.add_argument("--resend", action="store_true")
    args = parser.parse_args()

    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    rows = [row for row in load_rows(args.csv) if row.get(STATUS) == PENDING]
    log = load_log(args.log)
    now = datetime.now().isoformat(timespec="seconds")
    sent = skipped = marked = 0

    for row in rows:
        key = job_key(row)
        if key in log and not args.resend:
            skipped += 1
            continue
        decision = manual_alert_decision(row)
        if not decision.should_alert:
            log[key] = {"key": key, "alerted_at": now, "mode": decision.log_mode, "title": row.get(TITLE, ""), "reason": decision.blocker}
            skipped += 1
            continue
        if args.mark_existing:
            log[key] = {"key": key, "alerted_at": now, "mode": "marked_existing", "title": row.get(TITLE, "")}
            marked += 1
            continue
        if not token:
            raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
        if not chat_id:
            raise SystemExit("Missing TELEGRAM_CHAT_ID")
        result = send(token, chat_id, build_message(build_manual_alert(row, decision)))
        log[key] = {
            "key": key,
            "alerted_at": now,
            "mode": "sent",
            "ok": result.get("ok", False),
            "message_id": result.get("result", {}).get("message_id"),
            "title": row.get(TITLE, ""),
        }
        sent += 1

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print(json.dumps({"manual_jobs": len(rows), "sent": sent, "skipped": skipped, "marked": marked}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
