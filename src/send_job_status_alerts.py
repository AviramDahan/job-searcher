from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUBMITTED_TITLE = "הוגשה מועמדות"
MANUAL_TITLE = "נדרשת הגשה עצמאית / השלמה ידנית"
RETRY_TITLE = "ניסיון הגשה חוזר"
DATE_LABEL = "תאריך ושעה"
COMPANY_LABEL = "חברה"
JOB_LABEL = "משרה"
SCORE_LABEL = "ציון התאמה"
LINK_LABEL = "קישור"
MATCHED_LABEL = "דרישות שהמועמדת עומדת בהן"
COMPANY_INFO_LABEL = "מידע כללי על החברה"
BLOCKER_LABEL = "סיבת עצירה"
RECOMMENDATION_LABEL = "המלצה"
RETRY_RESULT_LABEL = "תוצאת ניסיון"


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_message(item: dict) -> str:
    matched = item.get("matched_requirements") or []
    matched_text = matched if isinstance(matched, str) else bullets(matched)

    if item.get("kind") == "submitted":
        return (
            f"{SUBMITTED_TITLE}\n"
            f"{DATE_LABEL}: {item.get('submitted_at', '')}\n"
            f"{COMPANY_LABEL}: {item['company']}\n"
            f"{JOB_LABEL}: {item['title']}\n"
            f"{SCORE_LABEL}: {item.get('score', '')}/100\n"
            f"{LINK_LABEL}: {item['link']}\n\n"
            f"{MATCHED_LABEL}:\n{matched_text}\n\n"
            f"{COMPANY_INFO_LABEL}:\n{item.get('company_info', '')}"
        )

    if item.get("kind") == "retry":
        return (
            f"{RETRY_TITLE}\n"
            f"{DATE_LABEL}: {item.get('attempted_at', '')}\n"
            f"{COMPANY_LABEL}: {item['company']}\n"
            f"{JOB_LABEL}: {item['title']}\n"
            f"{SCORE_LABEL}: {item.get('score', '')}/100\n"
            f"{LINK_LABEL}: {item['link']}\n\n"
            f"{MATCHED_LABEL}:\n{matched_text}\n\n"
            f"{COMPANY_INFO_LABEL}:\n{item.get('company_info', '')}\n\n"
            f"{RETRY_RESULT_LABEL}:\n{item.get('retry_result', '')}\n\n"
            f"{RECOMMENDATION_LABEL}:\n{item.get('recommendation', '')}"
        )

    return (
        f"{MANUAL_TITLE}\n"
        f"{COMPANY_LABEL}: {item['company']}\n"
        f"{JOB_LABEL}: {item['title']}\n"
        f"{SCORE_LABEL}: {item.get('score', '')}/100\n"
        f"{LINK_LABEL}: {item['link']}\n\n"
        f"{MATCHED_LABEL}:\n{matched_text}\n\n"
        f"{COMPANY_INFO_LABEL}:\n{item.get('company_info', '')}\n\n"
        f"{BLOCKER_LABEL}:\n{item.get('blocker', '')}\n\n"
        f"{RECOMMENDATION_LABEL}:\n{item.get('recommendation', '')}"
    )


def _post_message(token: str, chat_id: str, text: str) -> dict:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _migrated_chat_id(exc: HTTPError) -> str | None:
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
    except (OSError, json.JSONDecodeError):
        return None

    migrated = payload.get("parameters", {}).get("migrate_to_chat_id")
    return str(migrated) if migrated else None


def send(token: str, chat_id: str, text: str) -> dict:
    try:
        return _post_message(token, chat_id, text)
    except HTTPError as exc:
        migrated_chat_id = _migrated_chat_id(exc)
        if not migrated_chat_id or migrated_chat_id == str(chat_id):
            raise

    result = _post_message(token, migrated_chat_id, text)
    result["_migrated_from_chat_id"] = str(chat_id)
    result["_migrated_to_chat_id"] = migrated_chat_id
    return result


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send submitted/manual job alerts to Telegram.")
    parser.add_argument("alerts_json", type=Path)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise SystemExit("Missing TELEGRAM_CHAT_ID")

    alerts = json.loads(args.alerts_json.read_text(encoding="utf-8-sig"))
    results = []
    for item in alerts:
        try:
            result = send(token, chat_id, build_message(item))
            results.append(
                {
                    "kind": item.get("kind"),
                    "title": item.get("title"),
                    "ok": result.get("ok", False),
                    "message_id": result.get("result", {}).get("message_id"),
                    "migrated_to_chat_id": result.get("_migrated_to_chat_id"),
                }
            )
        except HTTPError as exc:
            results.append({"kind": item.get("kind"), "title": item.get("title"), "ok": False, "error": f"telegram_http_{exc.code}"})
        except URLError:
            results.append({"kind": item.get("kind"), "title": item.get("title"), "ok": False, "error": "telegram_network_error"})

    log_path = args.log or args.alerts_json.with_name(args.alerts_json.stem + "_sent_log.json")
    log_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    print_json({"sent": len(results), "ok": all(item["ok"] for item in results), "log": str(log_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
