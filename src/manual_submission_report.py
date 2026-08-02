from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .candidate_profile import FactIssueSeverity, assess_candidate_facts
    from .job_records import COMPANY, FIT, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, is_action_required_status, load_rows, score_int
    from .site_adapters import route_submission_failure
    from .submission_failures import AutomationAction, FailureKind
except ImportError:
    from candidate_profile import FactIssueSeverity, assess_candidate_facts
    from job_records import COMPANY, FIT, LINK, LOCATION, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, is_action_required_status, load_rows, score_int
    from site_adapters import route_submission_failure
    from submission_failures import AutomationAction, FailureKind


SITE_AUTOMATION_FAILURES = {
    FailureKind.LOGIN_OR_ACCOUNT,
    FailureKind.CAPTCHA_OR_SECURITY,
    FailureKind.FORM_AUTOMATION_UNRELIABLE,
    FailureKind.NO_DIRECT_FORM,
    FailureKind.MARKETING_CONSENT,
}

GENERIC_POLICY_BLOCKER_SIGNALS = {
    FailureKind.LEGAL_DECLARATION,
    FailureKind.MISSING_CANDIDATE_FACT,
    FailureKind.SALARY_REQUIRED,
    FailureKind.WORK_MODEL_UNKNOWN,
    FailureKind.EXPERIENCE_AMBIGUITY,
}


def generic_policy_blocker_signal(signals: tuple[FailureKind, ...]) -> FailureKind | None:
    for signal in signals:
        if signal in GENERIC_POLICY_BLOCKER_SIGNALS:
            return signal
    return None


def has_resolved_fact(fact_assessment, code: str) -> bool:
    return any(issue.code == code for issue in fact_assessment.resolved)


def fact_context(row: dict[str, str]) -> str:
    return " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, ""), row.get(TITLE, "")] if part)


def classify_pending_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    pending = [row for row in rows if is_action_required_status(row.get(STATUS, ""))]
    items = []
    for row in pending:
        context_reason = " ".join(part for part in [row.get(STOP_REASON, ""), row.get(REQUIREMENTS, "")] if part)
        route = route_submission_failure(
            reason=context_reason,
            link=row.get(LINK, ""),
            title=row.get(TITLE, ""),
            company=row.get(COMPANY, ""),
        )
        signals = route.failure.signals or (route.failure.kind,)
        fact_assessment = assess_candidate_facts(fact_context(row))
        candidate_blocker = fact_assessment.first_blocker
        marketing_consent_resolved = FailureKind.MARKETING_CONSENT in signals and has_resolved_fact(
            fact_assessment, "marketing_consent_approved"
        )
        generic_policy_blocker = generic_policy_blocker_signal(signals)
        policy_blocker = candidate_blocker.kind if candidate_blocker else generic_policy_blocker
        adjusted_action = route.recommended_action
        if marketing_consent_resolved and not policy_blocker:
            adjusted_action = AutomationAction.RETRY_WITH_PERSISTENT_SESSION
        if candidate_blocker and candidate_blocker.severity == FactIssueSeverity.DO_NOT_APPLY:
            adjusted_action = AutomationAction.DO_NOT_APPLY
        elif policy_blocker:
            adjusted_action = AutomationAction.HUMAN_APPROVAL_REQUIRED
        items.append(
            {
                "row": row,
                "route": route,
                "fact_assessment": fact_assessment,
                "candidate_blocker": candidate_blocker,
                "policy_blocker": policy_blocker,
                "adjusted_action": adjusted_action,
                "is_site_automation_failure": any(kind in SITE_AUTOMATION_FAILURES for kind in signals),
            }
        )
    return items


def site_failure_kind(item: dict[str, object]) -> FailureKind:
    route = item["route"]
    signals = route.failure.signals or (route.failure.kind,)
    for signal in signals:
        if signal in SITE_AUTOMATION_FAILURES:
            return signal
    return route.failure.kind


def render_report(rows: list[dict[str, str]]) -> str:
    items = classify_pending_rows(rows)
    site_failures = [item for item in items if item["is_site_automation_failure"]]
    non_site_blockers = [item for item in items if not item["is_site_automation_failure"]]
    by_kind = Counter(site_failure_kind(item).value for item in site_failures)
    by_site = Counter((item["route"].adapter.name if item["route"].adapter else "Unknown") for item in site_failures)
    by_action = Counter(item["adjusted_action"].value for item in site_failures)

    lines = [
        "# Manual Submission Failure Analysis",
        "",
        "This report focuses on jobs that were relevant but did not complete automatically.",
        "",
        "## Counts",
        "",
        f"- Pending rows: {len(items)}",
        f"- Site/automation submission failures: {len(site_failures)}",
        f"- Non-site blockers, such as missing candidate facts or unverified skills: {len(non_site_blockers)}",
        "",
        "## Failure Kinds",
    ]
    for kind, count in by_kind.most_common():
        lines.append(f"- `{kind}`: {count}")

    lines.extend(["", "## Sites"])
    for site, count in by_site.most_common():
        lines.append(f"- `{site}`: {count}")

    lines.extend(["", "## Recommended Actions"])
    for action, count in by_action.most_common():
        lines.append(f"- `{action}`: {count}")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in site_failures:
        grouped[site_failure_kind(item).value].append(item)

    lines.extend(["", "## Site/Automation Failures"])
    for kind in sorted(grouped):
        lines.extend(["", f"### {kind}"])
        group = sorted(grouped[kind], key=lambda item: score_int(item["row"]), reverse=True)
        for item in group:
            row = item["row"]
            route = item["route"]
            adapter_name = route.adapter.name if route.adapter else "Unknown"
            lines.append(
                f"- {row.get(SCORE, '')}/100 - {row.get(COMPANY, '')} - "
                f"[{row.get(TITLE, '')}]({row.get(LINK, '')}) - {row.get(LOCATION, '')}"
            )
            lines.append(f"  Site: `{adapter_name}`")
            lines.append(f"  Action: `{item['adjusted_action'].value}`")
            if item["policy_blocker"]:
                lines.append(f"  Policy blocker: `{item['policy_blocker'].value}`")
            if item["fact_assessment"].resolved:
                facts = "; ".join(issue.reason for issue in item["fact_assessment"].resolved)
                lines.append(f"  Verified facts: {facts}")
            if item["fact_assessment"].blockers:
                blockers = "; ".join(issue.reason for issue in item["fact_assessment"].blockers)
                lines.append(f"  Candidate blockers: {blockers}")
            lines.append(f"  Why it failed: {route.failure.reason}")
            if item["candidate_blocker"]:
                lines.append(f"  Fix: {item['candidate_blocker'].next_step}")
            elif item["policy_blocker"]:
                lines.append("  Fix: Verify the flagged requirement or policy item before retrying the application.")
            else:
                lines.append(f"  Fix: {route.failure.next_step}")

    lines.extend(["", "## Non-Site Blockers"])
    for item in sorted(non_site_blockers, key=lambda item: score_int(item["row"]), reverse=True):
        row = item["row"]
        route = item["route"]
        fact_assessment = item["fact_assessment"]
        detail = route.failure.next_step
        if fact_assessment.first_blocker:
            detail = fact_assessment.first_blocker.next_step
        lines.append(
            f"- {row.get(SCORE, '')}/100 - {row.get(COMPANY, '')} - "
            f"[{row.get(TITLE, '')}]({row.get(LINK, '')}) - `{route.failure.kind.value}` - {detail}"
        )

    lines.extend(
        [
            "",
            "## Implementation Priorities",
            "",
            "1. Use persistent browser sessions for JobMaster, LinkedIn, DSV/SuccessFactors, and Drushim.",
            "2. Add field-level verification after typing into brittle forms, especially SuccessFactors.",
            "3. For AllJobs and IAI, fill safe fields and pause at Radware/reCAPTCHA instead of marking the whole job as manually failed.",
            "4. Search official company career pages before sending manual alerts for aggregator-only jobs.",
            "5. Use verified identity, relatives-at-company, driving/car, system-skill, and approved-consent answers from the candidate profile; keep legal declarations and unresolved salary/work-model facts as explicit gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze pending rows and explain why they required manual submission.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--out", type=Path, default=Path("outputs/manual_submission_failure_analysis.md"))
    args = parser.parse_args()

    rows = load_rows(args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(rows), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
