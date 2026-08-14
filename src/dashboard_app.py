from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

try:
    from .action_insights import build_insights
    from .candidate_profile import load_candidate_profile
    from .conversion_audit import build_audit, load_json_list
    from .job_records import (
        COMPANY,
        COVER,
        CV,
        DATE,
        FIT,
        HEADERS,
        LINK,
        LOCATION,
        MANUAL_REQUIRED,
        PENDING,
        REJECTED,
        REQUIREMENTS,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        SUITABLE_STATUSES,
        TITLE,
        is_action_required_status,
        job_key,
        load_rows,
        score_int,
        write_rows,
    )
    from .location_policy import location_policy_payload
    from .public_text import public_hebrew_text
    from .rebuild_summary import render as render_summary
    from .send_job_status_alerts import build_message, send
    from .site_adapters import route_submission_failure
    from .submission_engine import plan_jobs
except ImportError:
    from action_insights import build_insights
    from candidate_profile import load_candidate_profile
    from conversion_audit import build_audit, load_json_list
    from job_records import (
        COMPANY,
        COVER,
        CV,
        DATE,
        FIT,
        HEADERS,
        LINK,
        LOCATION,
        MANUAL_REQUIRED,
        PENDING,
        REJECTED,
        REQUIREMENTS,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        SUITABLE_STATUSES,
        TITLE,
        is_action_required_status,
        job_key,
        load_rows,
        score_int,
        write_rows,
    )
    from location_policy import location_policy_payload
    from public_text import public_hebrew_text
    from rebuild_summary import render as render_summary
    from send_job_status_alerts import build_message, send
    from site_adapters import route_submission_failure
    from submission_engine import plan_jobs


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(__file__).resolve().with_name("dashboard_static")
DEFAULT_TIMEZONE = "Asia/Jerusalem"


@dataclass(frozen=True)
class DashboardPaths:
    csv: Path
    summary: Path
    manual_log: Path
    retry_queue: Path
    dashboard_log: Path
    submission_plan: Path | None = None
    location_preferences: Path | None = None


def resolve_project_path(value: str | Path, root: Path = PROJECT_ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def default_paths(root: Path = PROJECT_ROOT) -> DashboardPaths:
    return DashboardPaths(
        csv=resolve_project_path(os.environ.get("JOB_APPLICATIONS_CSV", "outputs/job_applications.csv"), root),
        summary=resolve_project_path(os.environ.get("JOB_SEARCH_SUMMARY", "outputs/job_search_summary.md"), root),
        manual_log=resolve_project_path(os.environ.get("MANUAL_ALERT_LOG", "outputs/manual_alert_log.json"), root),
        retry_queue=resolve_project_path(os.environ.get("RETRY_QUEUE_JSON", "outputs/retry_queue.json"), root),
        dashboard_log=resolve_project_path(os.environ.get("DASHBOARD_ALERT_LOG", "data/runtime/dashboard_alert_log.json"), root),
        submission_plan=resolve_project_path(os.environ.get("SUBMISSION_ENGINE_PLAN_JSON", "outputs/submission_engine_plan.json"), root),
        location_preferences=resolve_project_path(os.environ.get("LOCATION_PREFERENCES_JSON", "outputs/location_preferences.json"), root),
    )


def now_string(timezone: str = DEFAULT_TIMEZONE) -> str:
    return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")


def parse_summary_value(path: Path, label: str, default: int = 0) -> int:
    if not path.exists():
        return default
    marker = f"- {label}:"
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(marker):
            digits = "".join(ch for ch in line.split(":", 1)[1] if ch.isdigit())
            return int(digits) if digits else default
    return default


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def append_note(value: str, note: str, timestamp: str) -> str:
    clean_note = " ".join((note or "").split())
    if not clean_note:
        return value or ""
    suffix = f"הערת dashboard [{timestamp}]: {clean_note}"
    return f"{value}\n{suffix}" if value else suffix


def row_by_key(rows: list[dict[str, str]], key: str) -> dict[str, str] | None:
    for row in rows:
        if job_key(row) == key:
            return row
    return None


def failure_details(row: dict[str, str]) -> dict[str, str]:
    if not is_action_required_status(row.get(STATUS, "")):
        return {"kind": "", "next_step": ""}
    route = route_submission_failure(
        reason=public_hebrew_text(row.get(STOP_REASON, "")),
        link=row.get(LINK, ""),
        title=public_hebrew_text(row.get(TITLE, "")),
        company=public_hebrew_text(row.get(COMPANY, "")),
    )
    return {"kind": route.failure.kind.value, "next_step": public_hebrew_text(route.failure.next_step)}


def serialize_job(row: dict[str, str]) -> dict[str, Any]:
    details = failure_details(row)
    return {
        "key": job_key(row),
        "date": row.get(DATE, ""),
        "company": public_hebrew_text(row.get(COMPANY, "")),
        "title": public_hebrew_text(row.get(TITLE, "")),
        "location": public_hebrew_text(row.get(LOCATION, "")),
        "link": row.get(LINK, ""),
        "score": score_int(row),
        "score_raw": row.get(SCORE, ""),
        "requirements": public_hebrew_text(row.get(REQUIREMENTS, "")),
        "fit": public_hebrew_text(row.get(FIT, "")),
        "status": row.get(STATUS, ""),
        "stop_reason": public_hebrew_text(row.get(STOP_REASON, "")),
        "cover": public_hebrew_text(row.get(COVER, "")),
        "cv": public_hebrew_text(row.get(CV, "")),
        "failure_kind": details["kind"],
        "next_step": details["next_step"],
    }


def manual_alert_summary(path: Path) -> dict[str, int]:
    data = load_json(path, {})
    if isinstance(data, list):
        entries = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        entries = [item for item in data.values() if isinstance(item, dict)]
    else:
        entries = []
    counts = Counter(item.get("mode", "") for item in entries)
    return {
        "logged": len(entries),
        "sent": counts["sent"],
        "skipped": sum(count for mode, count in counts.items() if mode.startswith("skipped")),
        "failed": len([item for item in entries if item.get("mode") == "sent" and item.get("ok") is not True]),
    }


def retry_queue_summary(path: Path) -> dict[str, Any]:
    items = load_json(path, [])
    if not isinstance(items, list):
        items = []
    modes = Counter(str(item.get("mode", "")) for item in items if isinstance(item, dict))
    return {"total": len(items), "modes": dict(modes)}


def location_preferences_path(paths: DashboardPaths) -> Path:
    return paths.location_preferences or paths.summary.with_name("location_preferences.json")


def normalize_location_preferences(data: Any) -> dict[str, Any]:
    preferences = data.get("location_preferences", data) if isinstance(data, dict) else {}
    approved = preferences.get("approved_locations", {}) if isinstance(preferences, dict) else {}
    if isinstance(approved, list):
        approved_items = {str(item.get("key", "")): item for item in approved if isinstance(item, dict) and item.get("key")}
    elif isinstance(approved, dict):
        approved_items = {
            str(key): ({**value, "key": str(value.get("key") or key)} if isinstance(value, dict) else value)
            for key, value in approved.items()
        }
    else:
        approved_items = {}
    try:
        radius_km = int(float(str(preferences.get("radius_km") or preferences.get("radiusKm") or "0").strip()))
    except (TypeError, ValueError):
        radius_km = 0
    return {"approved_locations": approved_items, "radius_km": max(0, min(radius_km, 250))}


def save_location_preference(paths: DashboardPaths, payload: dict[str, Any]) -> dict[str, Any]:
    path = location_preferences_path(paths)
    preferences = normalize_location_preferences(load_json(path, {}))
    key = " ".join(str(payload.get("city_key", "")).split()).strip()
    label = " ".join(str(payload.get("city_label", "")).split()).strip()
    if not key:
        raise ValueError("missing_city_key")
    if not label:
        raise ValueError("missing_city_label")

    terms = payload.get("city_terms", [])
    if isinstance(terms, str):
        terms = [item.strip() for item in terms.split("|") if item.strip()]
    elif isinstance(terms, list):
        terms = [" ".join(str(item).split()).strip() for item in terms if " ".join(str(item).split()).strip()]
    else:
        terms = []
    approved = str(payload.get("approved", "")).strip().lower() in {"1", "true", "yes", "y", "כן", "approved"}
    if approved:
        preferences["approved_locations"][key] = {
            "key": key,
            "label": label,
            "terms": list(dict.fromkeys([label, key, *terms])),
            "approved": True,
            "updatedAt": now_string(),
            "source": "local-dashboard",
        }
    else:
        preferences["approved_locations"].pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": True, "location_preferences": preferences}, ensure_ascii=False, indent=2), encoding="utf-8")
    return preferences


def save_location_radius(paths: DashboardPaths, payload: dict[str, Any]) -> dict[str, Any]:
    path = location_preferences_path(paths)
    preferences = normalize_location_preferences(load_json(path, {}))
    try:
        radius_km = int(float(str(payload.get("radius_km", "0")).strip()))
    except (TypeError, ValueError):
        raise ValueError("invalid_radius_km") from None
    preferences["radius_km"] = max(0, min(radius_km, 250))
    preferences["radius_updated_at"] = now_string()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ok": True, "location_preferences": preferences}, ensure_ascii=False, indent=2), encoding="utf-8")
    return preferences


def dashboard_state(paths: DashboardPaths, timezone: str = DEFAULT_TIMEZONE) -> dict[str, Any]:
    rows = load_rows(paths.csv)
    counts = Counter(row.get(STATUS, "") for row in rows)
    scanned = parse_summary_value(paths.summary, "מספר המשרות שנסרקו", default=len(rows))
    candidate = load_candidate_profile()
    jobs = sorted((serialize_job(row) for row in rows), key=lambda item: (item["score"], item["date"]), reverse=True)
    submission_plan_path = paths.submission_plan or paths.retry_queue.with_name("submission_engine_plan.json")
    return {
        "generated_at": now_string(timezone),
        "candidate": {"full_name": candidate.full_name},
        "paths": {
            "csv": str(paths.csv),
            "summary": str(paths.summary),
            "manual_log": str(paths.manual_log),
            "retry_queue": str(paths.retry_queue),
            "submission_plan": str(submission_plan_path),
        },
        "telegram": {
            "configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
            "manual_alerts": manual_alert_summary(paths.manual_log),
        },
        "retry_queue": retry_queue_summary(paths.retry_queue),
        "counts": {
            "scanned": scanned,
            "documented": len(rows),
            "submitted": counts[SUBMITTED],
            "pending": counts[PENDING],
            "manual_required": counts[MANUAL_REQUIRED],
            "rejected": counts[REJECTED],
            "suitable": sum(counts[status] for status in SUITABLE_STATUSES),
        },
        "location_policy": location_policy_payload(),
        "location_preferences": normalize_location_preferences(load_json(location_preferences_path(paths), {})),
        "insights": build_insights(rows),
        "conversion": build_audit(rows, scanned, load_json_list(submission_plan_path), load_json_list(paths.retry_queue)),
        "jobs": jobs,
    }


def rebuild_summary_file(paths: DashboardPaths, telegram_alerts: int = 0, scanned_count: int | None = None) -> None:
    rows = load_rows(paths.csv)
    scanned = scanned_count if scanned_count is not None else parse_summary_value(paths.summary, "מספר המשרות שנסרקו", default=len(rows))
    paths.summary.parent.mkdir(parents=True, exist_ok=True)
    paths.summary.write_text(render_summary(rows, scanned, telegram_alerts, DEFAULT_TIMEZONE), encoding="utf-8-sig")


def update_job(paths: DashboardPaths, key: str, action: str, note: str = "", cv_filename: str = "") -> dict[str, Any]:
    rows = load_rows(paths.csv)
    row = row_by_key(rows, key)
    if row is None:
        raise KeyError(key)

    timestamp = now_string()
    if action == "add_note":
        row[STOP_REASON] = append_note(row.get(STOP_REASON, ""), note, timestamp)
    elif action == "mark_submitted":
        row[DATE] = timestamp.split(" ", 1)[0]
        row[STATUS] = SUBMITTED
        row[STOP_REASON] = append_note(row.get(STOP_REASON, ""), note or "סומן כהוגש ידנית דרך dashboard.", timestamp)
        if cv_filename:
            row[CV] = cv_filename
    elif action == "mark_rejected":
        row[DATE] = timestamp.split(" ", 1)[0]
        row[STATUS] = REJECTED
        row[STOP_REASON] = append_note(row.get(STOP_REASON, ""), note or "סומן כנפסל דרך dashboard.", timestamp)
    else:
        raise ValueError(f"Unsupported action: {action}")

    for header in HEADERS:
        row.setdefault(header, "")
    write_rows(paths.csv, rows)
    rebuild_summary_file(paths)
    return serialize_job(row)


def build_alert_payload(row: dict[str, str], timestamp: str | None = None) -> dict[str, Any]:
    status = row.get(STATUS, "")
    if status == SUBMITTED:
        return {
            "kind": "submitted",
            "submitted_at": timestamp or now_string(),
            "company": public_hebrew_text(row.get(COMPANY, "")),
            "title": public_hebrew_text(row.get(TITLE, "")),
            "score": row.get(SCORE, ""),
            "link": row.get(LINK, ""),
            "matched_requirements": public_hebrew_text(row.get(FIT, "")),
            "company_info": public_hebrew_text(f"מיקום: {row.get(LOCATION, '')}; דרישות מרכזיות: {row.get(REQUIREMENTS, '')}"),
        }

    return {
        "kind": "manual",
        "company": public_hebrew_text(row.get(COMPANY, "")),
        "title": public_hebrew_text(row.get(TITLE, "")),
        "score": row.get(SCORE, ""),
        "link": row.get(LINK, ""),
        "matched_requirements": public_hebrew_text(row.get(FIT, "")),
        "company_info": public_hebrew_text(f"מיקום: {row.get(LOCATION, '')}"),
        "blocker": public_hebrew_text(row.get(STOP_REASON, "")),
        "recommendation": failure_details(row).get("next_step") or "להמשיך רק לאחר אימות החסם מול המועמדת או האתר.",
    }


def save_dashboard_alert_log(paths: DashboardPaths, entry: dict[str, Any]) -> None:
    log = load_json(paths.dashboard_log, [])
    if not isinstance(log, list):
        log = []
    log.append(entry)
    paths.dashboard_log.parent.mkdir(parents=True, exist_ok=True)
    paths.dashboard_log.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def resend_telegram(paths: DashboardPaths, key: str) -> dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram env is missing")

    rows = load_rows(paths.csv)
    row = row_by_key(rows, key)
    if row is None:
        raise KeyError(key)

    payload = build_alert_payload(row)
    response = send(token, chat_id, build_message(payload))
    entry = {
        "sent_at": now_string(),
        "key": key,
        "company": row.get(COMPANY, ""),
        "title": row.get(TITLE, ""),
        "status": row.get(STATUS, ""),
        "ok": response.get("ok", False),
        "message_id": response.get("result", {}).get("message_id"),
        "migrated_to_chat_id": response.get("_migrated_to_chat_id"),
    }
    save_dashboard_alert_log(paths, entry)
    return entry


def plan_job_submission(paths: DashboardPaths, key: str) -> dict[str, Any]:
    rows = load_rows(paths.csv)
    row = row_by_key(rows, key)
    if row is None:
        raise KeyError(key)
    plans = plan_jobs([row], min_score=0, include_submitted=True)
    if not plans:
        raise RuntimeError("submission engine could not plan this job")
    return {
        "job_key": key,
        "plan": {
            "site": plans[0].site,
            "adapter": plans[0].adapter,
            "decision": plans[0].decision,
            "action": plans[0].action,
            "can_attempt": plans[0].can_attempt,
            "requires_human": plans[0].requires_human,
            "reason": plans[0].reason,
            "next_step": plans[0].next_step,
            "verified_facts": plans[0].verified_facts,
            "blockers": plans[0].blockers,
        },
    }


def read_request_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def make_handler(paths: DashboardPaths, timezone: str = DEFAULT_TIMEZONE) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "JobSearcherDashboard/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))

        def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def send_file(self, path: Path, content_type: str | None = None) -> None:
            if not path.exists() or not path.is_file():
                self.send_json({"ok": False, "error": "not_found"}, status=404)
                return
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            route = unquote(parsed.path)
            if route in {"/", "/dashboard"}:
                self.send_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
                return
            if route == "/api/state":
                self.send_json({"ok": True, "state": dashboard_state(paths, timezone)})
                return
            if route.startswith("/assets/"):
                asset = (STATIC_ROOT / route.removeprefix("/assets/")).resolve()
                if STATIC_ROOT.resolve() not in asset.parents and asset != STATIC_ROOT.resolve():
                    self.send_json({"ok": False, "error": "bad_asset_path"}, status=400)
                    return
                self.send_file(asset)
                return
            self.send_json({"ok": False, "error": "not_found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            route = unquote(parsed.path)
            try:
                payload = read_request_json(self)
                if route == "/api/jobs/update":
                    job = update_job(
                        paths=paths,
                        key=str(payload.get("key", "")),
                        action=str(payload.get("action", "")),
                        note=str(payload.get("note", "")),
                        cv_filename=str(payload.get("cv_filename", "")),
                    )
                    self.send_json({"ok": True, "job": job, "state": dashboard_state(paths, timezone)})
                    return
                if route == "/api/jobs/telegram":
                    result = resend_telegram(paths, str(payload.get("key", "")))
                    self.send_json({"ok": True, "telegram": result})
                    return
                if route == "/api/jobs/engine-plan":
                    result = plan_job_submission(paths, str(payload.get("key", "")))
                    self.send_json({"ok": True, "engine": result})
                    return
                if route == "/api/location-preferences":
                    preferences = save_location_preference(paths, payload)
                    self.send_json({"ok": True, "location_preferences": preferences, "state": dashboard_state(paths, timezone)})
                    return
                if route == "/api/location-radius":
                    preferences = save_location_radius(paths, payload)
                    self.send_json({"ok": True, "location_preferences": preferences, "state": dashboard_state(paths, timezone)})
                    return
                self.send_json({"ok": False, "error": "not_found"}, status=404)
            except KeyError:
                self.send_json({"ok": False, "error": "job_not_found"}, status=404)
            except ValueError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            except RuntimeError as exc:
                self.send_json({"ok": False, "error": str(exc)}, status=400)
            except json.JSONDecodeError:
                self.send_json({"ok": False, "error": "invalid_json"}, status=400)

    return DashboardHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Job Searcher dashboard.")
    parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "8765")))
    parser.add_argument("--csv", type=Path, default=default_paths().csv)
    parser.add_argument("--summary", type=Path, default=default_paths().summary)
    parser.add_argument("--manual-log", type=Path, default=default_paths().manual_log)
    parser.add_argument("--retry-queue", type=Path, default=default_paths().retry_queue)
    parser.add_argument("--dashboard-log", type=Path, default=default_paths().dashboard_log)
    parser.add_argument("--location-preferences", type=Path, default=default_paths().location_preferences)
    args = parser.parse_args()

    paths = DashboardPaths(
        csv=resolve_project_path(args.csv),
        summary=resolve_project_path(args.summary),
        manual_log=resolve_project_path(args.manual_log),
        retry_queue=resolve_project_path(args.retry_queue),
        dashboard_log=resolve_project_path(args.dashboard_log),
        location_preferences=resolve_project_path(args.location_preferences),
    )
    handler = make_handler(paths)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Job Searcher dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
