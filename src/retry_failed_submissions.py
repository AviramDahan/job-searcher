from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

try:
    from .browser_session import build_session_config, save_evidence
    from .candidate_profile import CandidateProfile, KOREN_DAHAN_PROFILE, assess_candidate_facts
    from .job_records import COMPANY, FIT, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, is_action_required_status, job_key, load_rows
    from .manual_submission_report import SITE_AUTOMATION_FAILURES
    from .send_job_status_alerts import build_message, send
    from .site_adapters import route_submission_failure
    from .submission_failures import AutomationAction, FailureKind
except ImportError:
    from browser_session import build_session_config, save_evidence
    from candidate_profile import CandidateProfile, KOREN_DAHAN_PROFILE, assess_candidate_facts
    from job_records import COMPANY, FIT, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, is_action_required_status, job_key, load_rows
    from manual_submission_report import SITE_AUTOMATION_FAILURES
    from send_job_status_alerts import build_message, send
    from site_adapters import route_submission_failure
    from submission_failures import AutomationAction, FailureKind


class RetryMode(str, Enum):
    AUTO_RETRYABLE = "auto_retryable"
    HUMAN_GATE = "human_gate"
    COMPANY_FALLBACK = "company_fallback"
    POLICY_REQUIRED = "policy_required"
    NOT_SYSTEM_FAILURE = "not_system_failure"


GENERIC_POLICY_BLOCKER_SIGNALS = {
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.SALARY_REQUIRED,
    FailureKind.WORK_MODEL_UNKNOWN,
    FailureKind.EXPERIENCE_AMBIGUITY,
}


@dataclass(frozen=True)
class RetryItem:
    key: str
    score: int
    company: str
    title: str
    location: str
    link: str
    requirements: str
    fit: str
    site: str
    failure_kind: str
    signals: list[str]
    action: str
    mode: str
    can_resend_now: bool
    requires_human: bool
    reason: str
    next_step: str
    stop_reason: str
    candidate_facts: list[str]
    candidate_blockers: list[str]


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def _score(row: dict[str, str]) -> int:
    try:
        return int(row.get(SCORE, "0") or "0")
    except ValueError:
        return 0


def _site_failure_signal(signals: tuple[FailureKind, ...], primary: FailureKind) -> FailureKind | None:
    for signal in signals or (primary,):
        if signal in SITE_AUTOMATION_FAILURES:
            return signal
    return None


def _generic_policy_blocker_signal(signals: tuple[FailureKind, ...]) -> FailureKind | None:
    for signal in signals:
        if signal in GENERIC_POLICY_BLOCKER_SIGNALS:
            return signal
    return None


def _generic_policy_signal_is_resolved(signal: FailureKind | None, fact_assessment) -> bool:
    if signal is None:
        return False
    if signal == FailureKind.UNVERIFIED_SYSTEM_SKILL:
        return bool(fact_assessment.resolved) and not fact_assessment.blockers
    return False


def _has_resolved_fact(fact_assessment, code: str) -> bool:
    return any(issue.code == code for issue in fact_assessment.resolved)


def _fact_context(row: dict[str, str]) -> str:
    return " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, ""), row.get(TITLE, "")] if part)


def _retry_mode(site_signal: FailureKind | None, action: AutomationAction) -> RetryMode:
    if site_signal is None:
        return RetryMode.NOT_SYSTEM_FAILURE
    if site_signal == FailureKind.MARKETING_CONSENT:
        return RetryMode.POLICY_REQUIRED
    if site_signal == FailureKind.CAPTCHA_OR_SECURITY:
        return RetryMode.HUMAN_GATE
    if site_signal == FailureKind.LOGIN_OR_ACCOUNT and action == AutomationAction.HUMAN_APPROVAL_REQUIRED:
        return RetryMode.HUMAN_GATE
    if site_signal == FailureKind.NO_DIRECT_FORM:
        return RetryMode.COMPANY_FALLBACK
    if action == AutomationAction.RETRY_WITH_PERSISTENT_SESSION:
        return RetryMode.AUTO_RETRYABLE
    if action == AutomationAction.FILL_UNTIL_HUMAN_GATE:
        return RetryMode.HUMAN_GATE
    if action == AutomationAction.USE_COMPANY_SITE_FALLBACK:
        return RetryMode.COMPANY_FALLBACK
    return RetryMode.POLICY_REQUIRED


RESOLVED_FACT_RETRY_KINDS = {
    FailureKind.SENSITIVE_FIELD,
    FailureKind.UNVERIFIED_SYSTEM_SKILL,
    FailureKind.MARKETING_CONSENT,
}


def build_retry_items(rows: list[dict[str, str]], profile: CandidateProfile = KOREN_DAHAN_PROFILE) -> list[RetryItem]:
    items: list[RetryItem] = []
    for row in rows:
        if not is_action_required_status(row.get(STATUS, "")):
            continue
        stop_reason = row.get(STOP_REASON, "")
        fact_assessment = assess_candidate_facts(_fact_context(row), profile=profile)
        if fact_assessment.has_disqualifying_blocker:
            continue

        route = route_submission_failure(
            reason=stop_reason,
            link=row.get(LINK, ""),
            title=row.get(TITLE, ""),
            company=row.get(COMPANY, ""),
        )
        site_signal = _site_failure_signal(route.failure.signals, route.failure.kind)
        mode = _retry_mode(site_signal, route.recommended_action)
        action = route.recommended_action
        marketing_consent_resolved = site_signal == FailureKind.MARKETING_CONSENT and _has_resolved_fact(
            fact_assessment, "marketing_consent_approved"
        )
        if marketing_consent_resolved:
            mode = RetryMode.AUTO_RETRYABLE
            action = AutomationAction.RETRY_WITH_PERSISTENT_SESSION

        if (
            mode == RetryMode.NOT_SYSTEM_FAILURE
            and fact_assessment.resolved
            and not fact_assessment.blockers
            and route.failure.kind in RESOLVED_FACT_RETRY_KINDS
        ):
            mode = RetryMode.AUTO_RETRYABLE
            action = AutomationAction.RETRY_WITH_PERSISTENT_SESSION

        if mode == RetryMode.NOT_SYSTEM_FAILURE:
            continue

        candidate_blocker = fact_assessment.first_blocker
        generic_policy_signal = _generic_policy_blocker_signal(route.failure.signals)
        if _generic_policy_signal_is_resolved(generic_policy_signal, fact_assessment):
            generic_policy_signal = None
        policy_signal = candidate_blocker.kind if candidate_blocker else generic_policy_signal
        if candidate_blocker or generic_policy_signal:
            mode = RetryMode.POLICY_REQUIRED

        adapter_name = route.adapter.name if route.adapter else "Unknown"
        reason = route.failure.reason
        next_step = route.failure.next_step
        if candidate_blocker:
            reason = candidate_blocker.reason
            next_step = candidate_blocker.next_step
        elif generic_policy_signal:
            reason = "The job has a system submission failure, but also includes a requirement or declaration that is not verified for the candidate."
            next_step = "Verify the flagged requirement or policy item before retrying the application."
        elif mode == RetryMode.AUTO_RETRYABLE and adapter_name == "Jobnet":
            mode = RetryMode.HUMAN_GATE
            action = AutomationAction.FILL_UNTIL_HUMAN_GATE
            reason = "Jobnet direct forms are not yet covered by a validated submit adapter."
            next_step = "Send a manual handoff or inspect the SendCv form before adding a safe Jobnet adapter."
        elif mode == RetryMode.AUTO_RETRYABLE and adapter_name == "Drushim":
            mode = RetryMode.COMPANY_FALLBACK
            action = AutomationAction.USE_COMPANY_SITE_FALLBACK
            reason = "Drushim is usable for discovery, but direct submit is not yet automated safely."
            next_step = "Search for the same role on the official company career page; if no direct form exists, send manual handoff."

        can_resend_now = mode in {RetryMode.AUTO_RETRYABLE, RetryMode.COMPANY_FALLBACK}

        items.append(
            RetryItem(
                key=job_key(row),
                score=_score(row),
                company=row.get(COMPANY, ""),
                title=row.get(TITLE, ""),
                location=row.get(LOCATION, ""),
                link=row.get(LINK, ""),
                requirements=row.get(REQUIREMENTS, ""),
                fit=row.get(FIT, ""),
                site=adapter_name,
                failure_kind=(policy_signal or site_signal or route.failure.kind).value,
                signals=[signal.value for signal in route.failure.signals],
                action=(AutomationAction.HUMAN_APPROVAL_REQUIRED if policy_signal else action).value,
                mode=mode.value,
                can_resend_now=can_resend_now,
                requires_human=(
                    (route.requires_human and not marketing_consent_resolved)
                    or mode in {RetryMode.HUMAN_GATE.value, RetryMode.POLICY_REQUIRED.value}
                ),
                reason=reason,
                next_step=next_step,
                stop_reason=row.get(STOP_REASON, ""),
                candidate_facts=[issue.reason for issue in fact_assessment.resolved],
                candidate_blockers=[issue.reason for issue in fact_assessment.blockers],
            )
        )
    return sorted(items, key=lambda item: (not item.can_resend_now, -item.score, item.site, item.title))


def load_attempt_log(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def save_attempt_log(path: Path, log: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def pending_retry_items(items: list[RetryItem], attempt_log: dict[str, dict], include_human_gates: bool = False) -> list[RetryItem]:
    pending = []
    for item in items:
        last = attempt_log.get(item.key)
        if last and last.get("status") in {"submitted", "blocked_for_human", "policy_required"}:
            continue
        if item.mode == RetryMode.HUMAN_GATE.value and not include_human_gates:
            continue
        if item.mode == RetryMode.POLICY_REQUIRED.value:
            continue
        pending.append(item)
    return pending


def load_alert_log(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def save_alert_log(path: Path, log: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def build_retry_alert_payload(item: RetryItem, result: dict, attempted_at: str | None = None) -> dict:
    attempted_at = attempted_at or datetime.now().isoformat(timespec="seconds")
    retry_status = result.get("status", "")
    if retry_status == "submitted":
        return {
            "kind": "submitted",
            "company": item.company,
            "title": item.title,
            "link": item.link,
            "score": item.score,
            "submitted_at": attempted_at,
            "matched_requirements": item.fit or item.requirements,
            "company_info": f"מיקום: {item.location}; מקור: {item.site}",
        }

    if item.requires_human or item.mode in {RetryMode.HUMAN_GATE.value, RetryMode.POLICY_REQUIRED.value}:
        return {
            "kind": "manual",
            "company": item.company,
            "title": item.title,
            "link": item.link,
            "score": item.score,
            "matched_requirements": item.fit or item.requirements,
            "company_info": f"מיקום: {item.location}; מקור: {item.site}",
            "blocker": item.reason,
            "recommendation": item.next_step,
        }

    return {
        "kind": "retry",
        "company": item.company,
        "title": item.title,
        "link": item.link,
        "score": item.score,
        "attempted_at": attempted_at,
        "matched_requirements": item.fit or item.requirements,
        "company_info": f"מיקום: {item.location}; מקור: {item.site}",
        "retry_result": f"{retry_status or 'unknown'}; evidence: {result.get('evidence', '')}",
        "recommendation": item.next_step,
    }


def send_retry_alert(item: RetryItem, result: dict, alert_log_path: Path, resend_alerts: bool = False) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise SystemExit("Missing TELEGRAM_CHAT_ID")

    log = load_alert_log(alert_log_path)
    alert_key = f"{item.key}:{result.get('status', 'unknown')}"
    if alert_key in log and not resend_alerts:
        return {"sent": False, "skipped": True, "reason": "already_alerted", "alert_key": alert_key}

    attempted_at = datetime.now().isoformat(timespec="seconds")
    payload = build_retry_alert_payload(item, result, attempted_at=attempted_at)
    response = send(token, chat_id, build_message(payload))
    log[alert_key] = {
        "alert_key": alert_key,
        "key": item.key,
        "alerted_at": attempted_at,
        "kind": payload.get("kind"),
        "status": result.get("status"),
        "ok": response.get("ok", False),
        "message_id": response.get("result", {}).get("message_id"),
        "company": item.company,
        "title": item.title,
    }
    save_alert_log(alert_log_path, log)
    return {"sent": True, "ok": response.get("ok", False), "alert_key": alert_key, "message_id": log[alert_key]["message_id"]}


def render_markdown(items: list[RetryItem]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.mode] = counts.get(item.mode, 0) + 1

    lines = [
        "# Retry Queue",
        "",
        "This queue contains only failures related to application mechanics, site behavior, or submit flow.",
        "",
        "## Counts",
        "",
    ]
    for mode, count in sorted(counts.items()):
        lines.append(f"- `{mode}`: {count}")

    for mode in [RetryMode.AUTO_RETRYABLE.value, RetryMode.COMPANY_FALLBACK.value, RetryMode.HUMAN_GATE.value, RetryMode.POLICY_REQUIRED.value]:
        group = [item for item in items if item.mode == mode]
        if not group:
            continue
        lines.extend(["", f"## {mode}"])
        for item in group:
            lines.append(f"- {item.score}/100 - {item.company} - [{item.title}]({item.link}) - {item.site}")
            lines.append(f"  Key: `{item.key}`")
            lines.append(f"  Failure: `{item.failure_kind}`")
            lines.append(f"  Action: `{item.action}`")
            lines.append(f"  Requirements: {item.requirements}")
            lines.append(f"  Fit: {item.fit}")
            if item.candidate_facts:
                lines.append(f"  Verified facts: {'; '.join(item.candidate_facts)}")
            if item.candidate_blockers:
                lines.append(f"  Candidate blockers: {'; '.join(item.candidate_blockers)}")
            lines.append(f"  Next: {item.next_step}")
    return "\n".join(lines) + "\n"


async def open_retry_session(item: RetryItem, root: Path, evidence_only: bool = False) -> dict:
    try:
        from .browser_session import launch_persistent_context  # type: ignore
    except ImportError:
        from browser_session import launch_persistent_context  # type: ignore

    config = build_session_config(item.link, root=root, site_name=item.site)
    if evidence_only:
        evidence = save_evidence(
            config=config,
            job_key=item.key,
            url=item.link,
            stage="retry-plan",
            reason=item.reason,
            metadata=asdict(item),
        )
        return {"status": "evidence_saved", "evidence": evidence.metadata_path}

    playwright, context = await launch_persistent_context(config)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(item.link, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        evidence = save_evidence(
            config=config,
            job_key=item.key,
            url=item.link,
            stage="retry-opened",
            reason=item.reason,
            html=await page.content(),
            screenshot_bytes=await page.screenshot(full_page=True),
            metadata={**asdict(item), "page_title": await page.title(), "current_url": page.url},
        )
        return {"status": "opened", "evidence": evidence.metadata_path}
    finally:
        await context.close()
        await playwright.stop()


def write_outputs(items: list[RetryItem], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8-sig")
    md_path.write_text(render_markdown(items), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and operate a retry queue for system-related application failures.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--json", type=Path, default=Path("outputs/retry_queue.json"))
    parser.add_argument("--md", type=Path, default=Path("outputs/retry_queue.md"))
    parser.add_argument("--attempt-log", type=Path, default=Path("data/runtime/retry_attempt_log.json"))
    parser.add_argument("--telegram-log", type=Path, default=Path("data/runtime/retry_telegram_log.json"))
    parser.add_argument("--open-next", action="store_true", help="Open the next retryable job in a persistent browser and save evidence.")
    parser.add_argument("--include-human-gates", action="store_true", help="Allow opening CAPTCHA/security human-gate jobs.")
    parser.add_argument("--evidence-only", action="store_true", help="Create evidence metadata without launching a browser.")
    parser.add_argument("--notify", action="store_true", help="Send a Telegram alert after opening or planning a retry item.")
    parser.add_argument("--resend-alerts", action="store_true", help="Allow sending the same retry-status alert again.")
    args = parser.parse_args()

    rows = load_rows(args.csv)
    items = build_retry_items(rows)
    write_outputs(items, args.json, args.md)

    if args.open_next:
        import asyncio

        attempt_log = load_attempt_log(args.attempt_log)
        queue = pending_retry_items(items, attempt_log, include_human_gates=args.include_human_gates)
        if not queue:
            print_json({"queue": len(items), "opened": None, "reason": "no_pending_retryable_items"})
            return 0

        item = queue[0]
        result = asyncio.run(open_retry_session(item, root=Path("."), evidence_only=args.evidence_only))
        alert_result = None
        if args.notify:
            alert_result = send_retry_alert(item, result, args.telegram_log, resend_alerts=args.resend_alerts)
        attempt_log[item.key] = {
            "key": item.key,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "status": result["status"],
            "item": asdict(item),
            "result": result,
            "telegram": alert_result,
        }
        save_attempt_log(args.attempt_log, attempt_log)
        print_json({"queue": len(items), "opened": asdict(item), "result": result, "telegram": alert_result})
        return 0

    print_json({"retry_items": len(items), "json": str(args.json), "md": str(args.md)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
