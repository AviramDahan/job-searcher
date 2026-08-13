from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BROKEN_TEXT_PATTERN = re.compile(r"\?{2,}")


@dataclass
class Check:
    name: str
    ok: bool
    status: str
    details: dict[str, object]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_file_exists(path: Path, name: str) -> Check:
    return Check(name, path.exists(), "ok" if path.exists() else "missing", {"path": str(path)})


def check_job_data(path: Path) -> Check:
    if not path.exists():
        return Check("job_data", False, "missing", {"path": str(path)})
    try:
        data = read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return Check("job_data", False, "invalid_json", {"path": str(path), "error": str(exc)})
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    jobs = data.get("jobs", [])
    has_broken = bool(BROKEN_TEXT_PATTERN.search(text))
    ok = isinstance(jobs, list) and len(jobs) > 0 and not has_broken
    status = "ok" if ok else "invalid"
    return Check(
        "job_data",
        ok,
        status,
        {
            "path": str(path),
            "jobs": len(jobs) if isinstance(jobs, list) else 0,
            "generated_at": data.get("generated_at", ""),
            "contains_replacement_question_runs": has_broken,
        },
    )


def check_csv(path: Path) -> Check:
    if not path.exists():
        return Check("applications_csv", False, "missing", {"path": str(path)})
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except UnicodeDecodeError as exc:
        return Check("applications_csv", False, "encoding_error", {"path": str(path), "error": str(exc)})
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    has_broken = bool(BROKEN_TEXT_PATTERN.search(text))
    ok = len(rows) > 0 and not has_broken
    return Check(
        "applications_csv",
        ok,
        "ok" if ok else "invalid",
        {"path": str(path), "rows": len(rows), "contains_replacement_question_runs": has_broken},
    )


def fetch_json(url: str, timeout: int = 20) -> tuple[int, dict | None, str]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 JobSearcher/1.0",
            "Origin": "https://aviramdahan.github.io",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body else None
            return response.status, payload, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        payload = None
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            pass
        return exc.code, payload, body
    except (URLError, TimeoutError) as exc:
        return 0, None, str(exc)


def check_remote_json(url: str, name: str, require_ok: bool = True) -> Check:
    status_code, payload, body = fetch_json(url)
    has_broken = bool(BROKEN_TEXT_PATTERN.search(body))
    response_ok = 200 <= status_code < 300 and payload is not None and not has_broken
    payload_ok = payload.get("ok") is not False if isinstance(payload, dict) else True
    ok = response_ok and (payload_ok if require_ok else True)
    status = "ok" if response_ok and payload_ok else "degraded" if response_ok else "failed"
    return Check(
        name,
        ok,
        status,
        {
            "url": url,
            "status_code": status_code,
            "payload_ok": payload.get("ok") if isinstance(payload, dict) else None,
            "payload_error": payload.get("error") if isinstance(payload, dict) else None,
            "contains_replacement_question_runs": has_broken,
        },
    )


def dashboard_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def build_checks(args: argparse.Namespace) -> list[Check]:
    checks = [
        check_file_exists(args.summary, "summary_md"),
        check_job_data(args.job_data),
        check_csv(args.csv),
    ]

    config = dashboard_config(args.dashboard_config)
    endpoint = str(config.get("updatesEndpoint") or "").strip()
    if endpoint:
        if endpoint.startswith("/"):
            endpoint = "https://job-searcher-live-dashboard.aviramsdahan.chatgpt.site" + endpoint
        separator = "&" if "?" in endpoint else "?"
        checks.append(check_remote_json(endpoint + separator + "action=health", "cloud_sync_health", require_ok=True))
        checks.append(check_remote_json(endpoint + separator + "action=listUpdates", "cloud_sync_state", require_ok=args.strict_sync))
    else:
        checks.append(Check("cloud_sync_config", False, "missing", {"path": str(args.dashboard_config)}))

    if args.github_pages_json:
        checks.append(check_remote_json(args.github_pages_json, "github_pages_job_data", require_ok=False))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Job Searcher health checks without printing secrets.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--job-data", type=Path, default=Path("docs/assets/job-data.json"))
    parser.add_argument("--dashboard-config", type=Path, default=Path("docs/assets/dashboard-config.json"))
    parser.add_argument("--github-pages-json", default="")
    parser.add_argument("--strict-sync", action="store_true", help="Fail when cloud sync state is unavailable or degraded.")
    args = parser.parse_args()

    checks = build_checks(args)
    hard_failures = [check for check in checks if not check.ok and (args.strict_sync or not check.name.startswith("cloud_sync"))]
    has_degraded = any(check.status != "ok" for check in checks)
    payload = {
        "ok": not hard_failures,
        "status": "failed" if hard_failures else "degraded" if has_degraded else "ok",
        "checks": [asdict(check) for check in checks],
    }
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
