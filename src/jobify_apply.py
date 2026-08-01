from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

try:
    from .browser_session import build_session_config, save_evidence
    from .job_records import job_key
except ImportError:
    from browser_session import build_session_config, save_evidence
    from job_records import job_key


SALARY_TERMS = ("ציפיות שכר", "שכר", "salary")
VERIFY_TERMS = ("אימות", "קוד", "verification", "verify")
CAPTCHA_TERMS = ("captcha", "recaptcha", "hcaptcha", "radware")
ACCOUNT_GATE_TERMS = (
    "כתובת האימייל כבר קיימת",
    "כתובת המייל כבר קיימת",
    "האימייל כבר קיים",
    "email already exists",
    "email exists",
    "already exists",
)


def page_has_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = (text or "").lower()
    return any(term.lower() in normalized for term in terms)


def classify_jobify_state(page_url: str, visible_text: str, diagnostic_text: str = "") -> tuple[str, str]:
    state_text = "\n".join(part for part in (visible_text, diagnostic_text, page_url) if part)
    if page_has_any(state_text, CAPTCHA_TERMS):
        return "captcha_gate", "Jobify displayed a CAPTCHA/security challenge."
    if page_has_any(state_text, ACCOUNT_GATE_TERMS):
        return "account_gate", "Jobify recognized an existing email address and requires account login before continuing."
    if page_has_any(state_text, VERIFY_TERMS):
        return "verification_gate", "Jobify requires email/phone verification before continuing."
    if page_has_any(state_text, SALARY_TERMS) or "ob-salary" in page_url:
        return "salary_gate", "Jobify onboarding reached a salary screen; numeric salary was not approved."
    if "login" in page_url or "register" in page_url:
        return "account_gate", "Jobify requires account login/registration continuation."
    return "uploaded", "CV was uploaded and Jobify advanced without a detected human gate."


async def collect_diagnostic_text(page, selectors: tuple[str, ...]) -> str:
    fragments: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = min(await locator.count(), 5)
        except Exception:
            continue
        for index in range(count):
            try:
                text = await locator.nth(index).text_content(timeout=1000)
            except Exception:
                continue
            if text and text.strip():
                fragments.append(text.strip())
    return "\n".join(fragments)


async def click_first_visible(page, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() and await locator.is_visible(timeout=1000):
                await locator.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


async def safe_goto(page, url: str, timeout_ms: int) -> None:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except Exception as exc:
            last_error = exc
            await page.wait_for_timeout(1500)
    if last_error:
        raise last_error


async def run(args: argparse.Namespace) -> int:
    cv_path = args.cv.resolve()
    if not cv_path.exists():
        raise SystemExit(f"CV file not found: {cv_path}")

    config = build_session_config(
        args.job_url,
        root=args.root,
        site_name="Jobify",
        headless=args.headless,
        executable_path=args.chrome_executable,
    )

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is not installed. Run: python -m pip install -r requirements.txt") from exc

    result: dict[str, object] = {
        "site": "Jobify",
        "job_url": args.job_url,
        "submitted": False,
        "stage": "started",
        "reason": "",
        "current_url": "",
        "evidence": None,
    }

    async with async_playwright() as playwright:
        config.user_data_dir.mkdir(parents=True, exist_ok=True)
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
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await safe_goto(page, args.job_url, args.timeout_ms)
            await page.wait_for_timeout(1500)

            await click_first_visible(
                page,
                (
                    "button:has-text('הגשת מועמדות')",
                    "text=הגשת מועמדות",
                    "a:has-text('הגשת מועמדות')",
                ),
            )
            await page.wait_for_timeout(1500)

            if await page.locator("a:has-text('הגש קו\"ח')").count():
                await page.locator("a:has-text('הגש קו\"ח')").first.click()
                await page.wait_for_timeout(1000)

            if "ab-type" not in page.url:
                await safe_goto(page, "https://jobify360.co.il/ab-type", args.timeout_ms)
                await page.wait_for_timeout(1000)

            file_inputs = page.locator("input[type='file']")
            if not await file_inputs.count():
                result.update(stage="file_input_missing", reason="Jobify did not expose a file input.")
            else:
                await file_inputs.first.set_input_files(str(cv_path))
                await page.wait_for_timeout(1500)
                if await page.locator("#agreeTerms").count():
                    await page.locator("#agreeTerms").check()
                await page.locator("#continueUploadBtn").click(timeout=10000)
                try:
                    await page.wait_for_url("**/ob-salary", timeout=args.post_upload_timeout_ms)
                except Exception:
                    await page.wait_for_timeout(5000)

                body_text = await page.locator("body").inner_text(timeout=10000)
                diagnostic_text = await collect_diagnostic_text(
                    page,
                    (
                        "#error_upload",
                        "#errorCVLoader",
                        ".error",
                        ".invalid-feedback",
                        "[class*='error']",
                        "[id*='error']",
                    ),
                )
                result["current_url"] = page.url
                stage, reason = classify_jobify_state(page.url, body_text, diagnostic_text)
                result.update(stage=stage, reason=reason)

            html = await page.content()
            screenshot = await page.screenshot(full_page=True)
            evidence = save_evidence(
                config=config,
                job_key=args.job_key,
                url=args.job_url,
                stage=str(result["stage"]),
                reason=str(result["reason"]),
                html=html,
                screenshot_bytes=screenshot,
                metadata={
                    "title": await page.title(),
                    "current_url": page.url,
                    "cv_file": cv_path.name,
                },
            )
            result["evidence"] = evidence.metadata_path
        finally:
            if args.keep_open:
                print("Browser remains open. Press Enter to close.")
                input()
            await context.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Try a Jobify application flow until the next human gate.")
    parser.add_argument("--job-url", required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--cv", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--chrome-executable", type=Path)
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--post-upload-timeout-ms", type=int, default=90000)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
