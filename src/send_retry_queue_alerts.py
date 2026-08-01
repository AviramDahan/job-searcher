from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from .send_job_status_alerts import build_message, send
except ImportError:
    from send_job_status_alerts import build_message, send


def load_log(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def save_log(path: Path, log: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def build_blocked_alert(item: dict) -> dict:
    return {
        "kind": "manual",
        "company": item.get("company", ""),
        "title": item.get("title", ""),
        "link": item.get("link", ""),
        "score": item.get("score", ""),
        "matched_requirements": item.get("fit") or item.get("requirements", ""),
        "company_info": f"מיקום: {item.get('location', '')}; מקור: {item.get('site', '')}",
        "blocker": item.get("reason", ""),
        "recommendation": item.get("next_step", ""),
    }


def blocked_items(items: list[dict]) -> list[dict]:
    return [item for item in items if not item.get("can_resend_now")]


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Telegram alerts for blocked retry-queue items.")
    parser.add_argument("--queue", type=Path, default=Path("outputs/retry_queue.json"))
    parser.add_argument("--log", type=Path, default=Path("data/runtime/retry_queue_alert_log.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mark-existing", action="store_true")
    parser.add_argument("--resend", action="store_true")
    args = parser.parse_args()

    items = json.loads(args.queue.read_text(encoding="utf-8-sig"))
    queue = blocked_items(items)
    log = load_log(args.log)
    now = datetime.now().isoformat(timespec="seconds")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    sent = skipped = marked = 0

    previews = []
    for item in queue:
        alert_key = f"{item.get('key')}:{item.get('mode')}:{item.get('failure_kind')}"
        if alert_key in log and not args.resend:
            skipped += 1
            continue

        payload = build_blocked_alert(item)
        if args.dry_run:
            previews.append({"alert_key": alert_key, "message": build_message(payload)})
            continue

        if args.mark_existing:
            log[alert_key] = {"alert_key": alert_key, "alerted_at": now, "mode": "marked_existing", "title": item.get("title", "")}
            marked += 1
            continue

        if not token:
            raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
        if not chat_id:
            raise SystemExit("Missing TELEGRAM_CHAT_ID")

        response = send(token, chat_id, build_message(payload))
        log[alert_key] = {
            "alert_key": alert_key,
            "alerted_at": now,
            "mode": "sent",
            "ok": response.get("ok", False),
            "message_id": response.get("result", {}).get("message_id"),
            "title": item.get("title", ""),
            "company": item.get("company", ""),
        }
        sent += 1

    if args.dry_run:
        print_json({"blocked_retry_items": len(queue), "previews": previews})
        return 0

    save_log(args.log, log)
    print_json({"blocked_retry_items": len(queue), "sent": sent, "skipped": skipped, "marked": marked})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
