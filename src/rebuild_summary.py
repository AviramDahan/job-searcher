from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .job_records import COMPANY, LINK, LOCATION, MANUAL_REQUIRED, SCORE, STATUS, STOP_REASON, SUBMITTED, PENDING, REJECTED, SUITABLE_STATUSES, TITLE, load_rows, score_int
except ImportError:
    from job_records import COMPANY, LINK, LOCATION, MANUAL_REQUIRED, SCORE, STATUS, STOP_REASON, SUBMITTED, PENDING, REJECTED, SUITABLE_STATUSES, TITLE, load_rows, score_int


def render(rows: list[dict[str, str]], scanned_count: int, telegram_alerts: int, timezone: str) -> str:
    now = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    counts = Counter(row.get(STATUS, "") for row in rows)
    suitable = sum(counts[status] for status in SUITABLE_STATUSES)
    top = sorted(rows, key=score_int, reverse=True)[:5]

    lines = [
        "# סיכום חיפוש משרות",
        "",
        f"- זמן עדכון אחרון: {now}",
        f"- מספר המשרות שנסרקו: {scanned_count}",
        f"- מספר המשרות שתועדו: {len(rows)}",
        f"- מספר המשרות המתאימות: {suitable}",
        f"- מספר המועמדויות שהוגשו: {counts[SUBMITTED]}",
        f"- מספר המשרות שממתינות לאישור: {counts[PENDING]}",
        f"- מספר המשרות שנדרשת עבורן הגשה ידנית: {counts[MANUAL_REQUIRED]}",
        f"- מספר המשרות שנפסלו: {counts[REJECTED]}",
        f"- התראות Telegram חדשות בסבב: {telegram_alerts}",
        "",
        "## חמש המשרות בעלות ההתאמה הגבוהה ביותר",
    ]
    for row in top:
        lines.append(f"- {row[SCORE]}/100 - {row[COMPANY]} - [{row[TITLE]}]({row[LINK]}) - {row[LOCATION]} - {row[STATUS]}")

    for status in [SUBMITTED, MANUAL_REQUIRED, PENDING, REJECTED]:
        lines.extend(["", f"## משרות בסטטוס: {status}"])
        status_rows = [row for row in rows if row.get(STATUS) == status]
        status_rows.sort(key=score_int, reverse=True)
        for row in status_rows:
            lines.append(
                f"- {row[SCORE]}/100 - {row[COMPANY]} - [{row[TITLE]}]({row[LINK]}) - "
                f"{row[LOCATION]} - {row[STATUS]} - {row[STOP_REASON]}"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild Markdown summary from job_applications.csv.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--scanned-count", type=int, default=0)
    parser.add_argument("--telegram-alerts", type=int, default=0)
    parser.add_argument("--timezone", default="Asia/Jerusalem")
    args = parser.parse_args()

    rows = load_rows(args.csv)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(render(rows, args.scanned_count, args.telegram_alerts, args.timezone), encoding="utf-8-sig")
    print(f"Wrote {args.summary} from {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
