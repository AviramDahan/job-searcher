from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserSessionConfig:
    site_name: str
    user_data_dir: Path
    evidence_dir: Path
    headless: bool = False
    locale: str = "he-IL"
    timezone_id: str = "Asia/Jerusalem"
    executable_path: Path | None = None


@dataclass(frozen=True)
class SubmissionEvidence:
    attempt_id: str
    created_at: str
    job_key: str
    url: str
    site_name: str
    stage: str
    reason: str
    html_path: str | None = None
    screenshot_path: str | None = None
    metadata_path: str | None = None


def safe_slug(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value.strip().lower(), flags=re.UNICODE)
    return re.sub(r"-+", "-", value).strip("-") or "unknown"


def site_slug_from_url(url: str) -> str:
    domain = urlparse(url).netloc or "unknown-site"
    return safe_slug(domain)


def build_session_config(
    url: str,
    root: Path = Path("."),
    site_name: str | None = None,
    headless: bool = False,
    executable_path: Path | None = None,
) -> BrowserSessionConfig:
    slug = safe_slug(site_name or site_slug_from_url(url))
    executable = executable_path
    if executable is None and os.environ.get("CHROME_EXECUTABLE_PATH"):
        executable = Path(os.environ["CHROME_EXECUTABLE_PATH"])
    return BrowserSessionConfig(
        site_name=site_name or slug,
        user_data_dir=root / "data" / "browser-profiles" / slug,
        evidence_dir=root / "data" / "evidence" / slug,
        headless=headless,
        executable_path=executable,
    )


def attempt_id(job_key: str, stage: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{safe_slug(job_key)[:80]}-{safe_slug(stage)[:40]}"


def save_evidence(
    config: BrowserSessionConfig,
    job_key: str,
    url: str,
    stage: str,
    reason: str,
    html: str | None = None,
    screenshot_bytes: bytes | None = None,
    metadata: dict | None = None,
) -> SubmissionEvidence:
    config.evidence_dir.mkdir(parents=True, exist_ok=True)
    current_attempt_id = attempt_id(job_key, stage)
    base = config.evidence_dir / current_attempt_id

    html_path = None
    if html is not None:
        html_path = str(base.with_suffix(".html"))
        Path(html_path).write_text(html, encoding="utf-8", errors="replace")

    screenshot_path = None
    if screenshot_bytes is not None:
        screenshot_path = str(base.with_suffix(".png"))
        Path(screenshot_path).write_bytes(screenshot_bytes)

    metadata_path = str(base.with_suffix(".json"))
    evidence = SubmissionEvidence(
        attempt_id=current_attempt_id,
        created_at=datetime.now().isoformat(timespec="seconds"),
        job_key=job_key,
        url=url,
        site_name=config.site_name,
        stage=stage,
        reason=reason,
        html_path=html_path,
        screenshot_path=screenshot_path,
        metadata_path=metadata_path,
    )
    payload = {
        "evidence": asdict(evidence),
        "session": {
            "site_name": config.site_name,
            "user_data_dir": str(config.user_data_dir),
            "headless": config.headless,
            "locale": config.locale,
            "timezone_id": config.timezone_id,
        },
        "metadata": metadata or {},
    }
    Path(metadata_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    return evidence


async def launch_persistent_context(config: BrowserSessionConfig):
    """Launch a persistent Playwright Chromium context.

    The import stays inside the function so the rest of the project works even
    when Playwright is not installed on a machine that only sends alerts/reports.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium") from exc

    config.user_data_dir.mkdir(parents=True, exist_ok=True)
    playwright = await async_playwright().start()
    launch_options = {}
    if config.executable_path:
        launch_options["executable_path"] = str(config.executable_path)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(config.user_data_dir),
        headless=config.headless,
        locale=config.locale,
        timezone_id=config.timezone_id,
        viewport={"width": 1440, "height": 1000},
        **launch_options,
    )
    return playwright, context
