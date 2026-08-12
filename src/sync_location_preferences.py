from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_SYNC_ENDPOINT = "https://job-searcher-live-dashboard.aviramsdahan.chatgpt.site/api/sync"
DEFAULT_OUTPUT = Path("outputs/location_preferences.json")
DEFAULT_DASHBOARD_CONFIG = Path("docs/assets/dashboard-config.json")


class SyncEndpointError(RuntimeError):
    pass


def clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "כן", "approved"}


def parse_radius_km(value: Any) -> int:
    try:
        radius = int(float(str(value or "").strip()))
    except (TypeError, ValueError):
        return 0
    return max(0, min(radius, 250))


def normalize_location_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    preferences = payload.get("location_preferences", {})
    approved = preferences.get("approved_locations", {}) if isinstance(preferences, dict) else {}
    if isinstance(approved, dict):
        entries = approved.values()
    elif isinstance(approved, list):
        entries = approved
    else:
        entries = []

    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not parse_bool(entry.get("approved", True)):
            continue
        key = clean(entry.get("key"))
        label = clean(entry.get("label") or entry.get("city"))
        terms = entry.get("terms", [])
        if not isinstance(terms, list):
            terms = []
        clean_terms = []
        for term in [label, key, *terms]:
            term = clean(term)
            if term and term.lower() not in {item.lower() for item in clean_terms}:
                clean_terms.append(term)
        if key and label:
            normalized.append(
                {
                    "key": key,
                    "label": label,
                    "terms": clean_terms,
                    "approved": True,
                    "updatedAt": clean(entry.get("updatedAt") or entry.get("updated_at")),
                    "source": clean(entry.get("source") or "dashboard"),
                }
            )

    return {
        "ok": True,
        "generated_at": clean(payload.get("generated_at")),
        "location_preferences": {
            "approved_locations": sorted(normalized, key=lambda item: item["label"]),
            "radius_km": parse_radius_km(preferences.get("radius_km") or preferences.get("radiusKm")) if isinstance(preferences, dict) else 0,
        },
    }


def fetch_preferences(endpoint: str, timeout: int) -> dict[str, Any]:
    request = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 JobSearcher/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def require_healthy_payload(payload: dict[str, Any]) -> None:
    if payload.get("ok") is False:
        error = clean(payload.get("error")) or "sync_endpoint_unhealthy"
        raise SyncEndpointError(error)
    if clean(payload.get("storage_status")) == "alerts_only":
        warning = clean(payload.get("storage_warning")) or "sync_storage_alerts_only"
        raise SyncEndpointError(warning)


def endpoint_from_dashboard_config(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(config, dict):
        return ""
    endpoint = clean(config.get("updatesEndpoint") or config.get("endpoint"))
    if not endpoint:
        return ""
    if endpoint.startswith("/"):
        return "https://job-searcher-live-dashboard.aviramsdahan.chatgpt.site" + endpoint
    return endpoint


def resolve_endpoint(explicit_endpoint: str, dashboard_config: Path) -> str:
    explicit = clean(explicit_endpoint)
    if explicit:
        return explicit
    return endpoint_from_dashboard_config(dashboard_config) or DEFAULT_SYNC_ENDPOINT


def write_preferences(path: Path, preferences: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync dashboard-approved location preferences into a local policy file.")
    parser.add_argument("--endpoint", default="", help="Override the dashboard sync endpoint. Defaults to docs/assets/dashboard-config.json.")
    parser.add_argument("--dashboard-config", type=Path, default=DEFAULT_DASHBOARD_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    endpoint = resolve_endpoint(args.endpoint, args.dashboard_config)
    try:
        payload = fetch_preferences(endpoint, args.timeout)
        require_healthy_payload(payload)
        preferences = normalize_location_preferences(payload)
        write_preferences(args.out, preferences)
        approved_count = len(preferences["location_preferences"]["approved_locations"])
        print(json.dumps({"ok": True, "endpoint": endpoint, "out": str(args.out), "approved_locations": approved_count}, ensure_ascii=False))
        return 0
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, SyncEndpointError) as error:
        if args.strict:
            raise
        fallback = {
            "ok": False,
            "error": str(error),
            "location_preferences": {"approved_locations": [], "radius_km": 0},
        }
        if not args.out.exists():
            write_preferences(args.out, fallback)
        print(json.dumps({"ok": False, "error": str(error), "out": str(args.out), "using_existing": args.out.exists()}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
