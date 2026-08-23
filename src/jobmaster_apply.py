from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from .browser_session import build_session_config, launch_persistent_context, save_evidence
except ImportError:
    from browser_session import build_session_config, launch_persistent_context, save_evidence


LOGIN_TERMS = ("כניסת משתמש", "התחבר", "סיסמה", "email", "password")
VERIFICATION_TERMS = ("קוד אימות", "אימות", "verify", "verification code")
SUCCESS_TERMS = ("קורות החיים נשלחו בהצלחה", "CV Sent successfully")
CAPTCHA_TERMS = ("captcha", "recaptcha", "radware", "cloudflare")
CLOSED_TERMS = (
    "המשרה אינה פעילה",
    "המשרה כבר לא פעילה",
    "לא נמצאה משרה",
    "אינה מקבלת מועמדויות",
    "המשרה הוסרה מהאתר",
    "הוסרה מהאתר ע\"י החברה",
)


class JobMasterStage(str, Enum):
    STARTED = "started"
    LOGIN_REQUIRED = "login_required"
    VERIFICATION_REQUIRED = "verification_required"
    CLOSED_JOB = "closed_job"
    CAPTCHA_GATE = "captcha_gate"
    APPLY_BUTTON_MISSING = "apply_button_missing"
    FORM_LOAD_TIMEOUT = "form_load_timeout"
    APPLY_FORM_OPENED = "apply_form_opened"
    CV_VERIFIED = "cv_verified"
    CV_UPLOADED = "cv_uploaded"
    CV_UNVERIFIED = "cv_unverified"
    PROFILE_INCOMPLETE = "profile_incomplete"
    FORM_PREPARED = "form_prepared"
    SUBMITTED = "submitted"
    SUBMIT_FAILED = "submit_failed"
    ERROR = "error"


@dataclass(frozen=True)
class JobMasterOptions:
    job_url: str
    job_key: str
    cover_letter: str = ""
    cv_path: Path | None = None
    expected_cv_filename: str = ""
    email: str = ""
    password: str = ""
    submit: bool = False
    root: Path = Path(".")
    headless: bool = False
    keep_open: bool = False
    timeout_ms: int = 45000
    settle_ms: int = 1500


@dataclass(frozen=True)
class JobMasterResult:
    site: str
    job_key: str
    job_url: str
    stage: str
    submitted: bool
    reason: str
    next_step: str
    current_url: str
    evidence: str | None
    cv_filename: str
    send_response: dict | None = None


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def job_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("key"):
        return query["key"][0]
    match = re.search(r"(?:key=|/)(\d{5,})(?:\D|$)", url)
    return match.group(1) if match else None


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in terms)


def classify_page_state(url: str, visible_text: str) -> JobMasterStage | None:
    combined = f"{url}\n{visible_text}"
    if contains_any(combined, CLOSED_TERMS):
        return JobMasterStage.CLOSED_JOB
    if contains_any(combined, CAPTCHA_TERMS):
        return JobMasterStage.CAPTCHA_GATE
    if contains_any(combined, VERIFICATION_TERMS):
        return JobMasterStage.VERIFICATION_REQUIRED
    if "account.jobmaster.co.il" in urlparse(url).netloc.lower() or (
        contains_any(visible_text, LOGIN_TERMS) and "jobmaster.co.il/jobs/checknum" not in url.lower()
    ):
        return JobMasterStage.LOGIN_REQUIRED
    if contains_any(combined, SUCCESS_TERMS):
        return JobMasterStage.SUBMITTED
    return None


def default_cv_path() -> Path | None:
    env_path = os.environ.get("CV_PATH", "").strip()
    if env_path:
        return Path(env_path)
    local_path = Path("data/private/koren_dahan_cv.pdf")
    return local_path if local_path.exists() else None


def expected_cv_name(cv_path: Path | None, override: str = "") -> str:
    env_name = os.environ.get("JOBMASTER_EXPECTED_CV_FILENAME", "").strip()
    if env_name:
        return env_name
    clean_override = normalize_cv_hint(override)
    if clean_override:
        return clean_override
    return cv_path.name if cv_path else ""


def normalize_cv_hint(value: str) -> str:
    clean = " ".join((value or "").split())
    if not clean:
        return ""
    lowered = clean.lower()
    if "לא צורף" in clean or "נדרש" in clean or "manual" in lowered:
        return ""
    match = re.search(r"([^\\/|]+?\.(?:pdf|docx?|rtf))", clean, flags=re.IGNORECASE)
    return match.group(1).strip() if match else clean


async def visible_text(page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""


async def click_first_visible(page, selectors: tuple[str, ...], timeout_ms: int = 5000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if await item.is_visible(timeout=500):
                    await item.click(timeout=timeout_ms)
                    return True
            except Exception:
                continue
    return False


async def fill_first_visible(page, selectors: tuple[str, ...], value: str, timeout_ms: int = 5000) -> bool:
    if not value:
        return False
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if await item.is_visible(timeout=500):
                    await item.fill(value, timeout=timeout_ms)
                    return True
            except Exception:
                continue
    return False


async def login_if_needed(page, options: JobMasterOptions) -> JobMasterStage | None:
    state = classify_page_state(page.url, await visible_text(page))
    if state != JobMasterStage.LOGIN_REQUIRED:
        return state
    if not options.email or not options.password:
        return JobMasterStage.LOGIN_REQUIRED

    email_filled = await fill_first_visible(page, ("#email", "input[name='email']", "input[type='email']"), options.email)
    password_filled = await fill_first_visible(page, ("#password", "input[name='password']", "input[type='password']"), options.password)
    if not email_filled or not password_filled:
        return JobMasterStage.LOGIN_REQUIRED

    await click_first_visible(page, ("input[type='submit']", "button[type='submit']", "button:has-text('התחברות')"))
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=options.timeout_ms)
    except Exception:
        pass
    await page.wait_for_timeout(options.settle_ms)
    return classify_page_state(page.url, await visible_text(page))


async def open_application_form(page, options: JobMasterOptions) -> JobMasterStage | None:
    job_id = job_id_from_url(options.job_url)
    selectors = (
        f"#applyJob{job_id}" if job_id else "button[id^='applyJob']",
        "button[data-selector^='Begin_Cv_Send']",
        "button:has-text('הגש מועמדות')",
        "button:has-text('שלח קורות חיים')",
    )
    clicked = await click_first_visible(page, selectors)
    if not clicked:
        return JobMasterStage.APPLY_BUTTON_MISSING

    deadline = max(1, options.timeout_ms // 500)
    saw_modal = False
    for _ in range(deadline):
        state = classify_page_state(page.url, await visible_text(page))
        if state in {
            JobMasterStage.LOGIN_REQUIRED,
            JobMasterStage.VERIFICATION_REQUIRED,
            JobMasterStage.CAPTCHA_GATE,
            JobMasterStage.CLOSED_JOB,
            JobMasterStage.SUBMITTED,
        }:
            return state
        try:
            if await page.locator(".cv-form-details").count():
                return JobMasterStage.APPLY_FORM_OPENED
            if await page.locator("#modal_content").count():
                saw_modal = True
        except Exception:
            pass
        await page.wait_for_timeout(500)

    return JobMasterStage.FORM_LOAD_TIMEOUT if saw_modal else None


async def cv_list_text(page) -> str:
    selectors = (".userCVList", ".getCVListHTML", "#modal_content")
    fragments = []
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count():
                text = await locator.first.inner_text(timeout=2000)
                if text:
                    fragments.append(text)
        except Exception:
            continue
    return "\n".join(fragments)


async def select_expected_cv(page, expected_filename: str) -> bool:
    if not expected_filename:
        return False
    expected = expected_filename.lower()
    labels = page.locator(".userCVList label")
    try:
        count = await labels.count()
    except Exception:
        return False
    for index in range(count):
        label = labels.nth(index)
        try:
            text = (await label.inner_text(timeout=1000)).lower()
            if expected in text:
                for_attr = await label.get_attribute("for")
                if for_attr:
                    radio = page.locator(f"#{for_attr}")
                    if await radio.count():
                        await radio.check(timeout=3000)
                        return True
                await label.click(timeout=3000)
                return True
        except Exception:
            continue
    return False


async def upload_cv_if_possible(page, cv_path: Path | None) -> bool:
    if not cv_path or not cv_path.exists():
        return False
    inputs = page.locator("input[type='file']")
    try:
        count = await inputs.count()
    except Exception:
        return False
    for index in range(count):
        item = inputs.nth(index)
        try:
            await item.set_input_files(str(cv_path.resolve()), timeout=5000)
            await page.wait_for_timeout(4000)
            return True
        except Exception:
            continue
    return False


async def ensure_current_cv(page, options: JobMasterOptions) -> JobMasterStage:
    expected = expected_cv_name(options.cv_path, options.expected_cv_filename)
    text = await cv_list_text(page)
    if expected and expected.lower() in text.lower():
        selected = await select_expected_cv(page, expected)
        return JobMasterStage.CV_VERIFIED if selected or expected.lower() in (await cv_list_text(page)).lower() else JobMasterStage.CV_UNVERIFIED

    if await upload_cv_if_possible(page, options.cv_path):
        refreshed_text = await cv_list_text(page)
        if expected and expected.lower() in refreshed_text.lower():
            await select_expected_cv(page, expected)
        return JobMasterStage.CV_UPLOADED

    return JobMasterStage.CV_UNVERIFIED


async def fill_cover_letter(page, cover_letter: str) -> bool:
    return await fill_first_visible(page, ("textarea[name='letter']", "textarea#letter", ".getMessageHTML textarea", "textarea"), cover_letter)


async def form_has_profile_errors(page) -> bool:
    error_selectors = (".profileEditingError:not(.hide)", ".cn-filedWrap--outline-error", ".profileDiv.editing .emptyError")
    for selector in error_selectors:
        try:
            if await page.locator(selector).count():
                return True
        except Exception:
            continue
    return False


async def submit_form(page, options: JobMasterOptions) -> tuple[JobMasterStage, dict | None]:
    response_payload = None
    clicked = False
    try:
        async with page.expect_response(lambda response: "sendkorot.api.asp" in response.url, timeout=15000) as response_info:
            clicked = await click_first_visible(
                page, (".cv-form-details button.buttonSubmit", ".cv-form-details button[type='submit']", "button.buttonSubmit")
            )
        if not clicked:
            return JobMasterStage.SUBMIT_FAILED, {"message": "submit_button_missing"}
        response = await response_info.value
        try:
            response_payload = await response.json()
        except Exception:
            response_payload = {"status": response.status, "url": response.url}
    except Exception:
        pass
    if not clicked:
        return JobMasterStage.SUBMIT_FAILED, {"message": "submit_button_missing"}

    await page.wait_for_timeout(5000)
    text = await visible_text(page)
    if contains_any(text, SUCCESS_TERMS) or await page.locator(".cvSendSuccessfully, .SentSuccessfully").count():
        return JobMasterStage.SUBMITTED, response_payload or {"status": "OK", "detected": "success_dom"}
    if response_payload and str(response_payload.get("status", "")).upper() == "OK":
        return JobMasterStage.SUBMITTED, response_payload
    if await form_has_profile_errors(page):
        return JobMasterStage.PROFILE_INCOMPLETE, response_payload or {"message": "profile_incomplete"}
    return JobMasterStage.SUBMIT_FAILED, response_payload or {"message": "success_not_detected"}


def reason_for_stage(stage: JobMasterStage, submit: bool) -> tuple[str, str]:
    reasons = {
        JobMasterStage.LOGIN_REQUIRED: (
            "JobMaster requires login before this application can continue.",
            "Start a persistent JobMaster session or provide JOBMASTER_EMAIL/JOBMASTER_PASSWORD in the runtime environment.",
        ),
        JobMasterStage.VERIFICATION_REQUIRED: (
            "JobMaster requires an email or phone verification code.",
            "Complete the verification in the persistent browser session, then retry.",
        ),
        JobMasterStage.CLOSED_JOB: ("The JobMaster posting is no longer active.", "Do not apply; mark the row rejected if still pending."),
        JobMasterStage.CAPTCHA_GATE: (
            "JobMaster presented a CAPTCHA or security challenge.",
            "Pause for a human to pass the challenge, then resume from the persistent session.",
        ),
        JobMasterStage.APPLY_BUTTON_MISSING: (
            "The JobMaster apply button was not found.",
            "Capture evidence and inspect whether the posting is closed, already submitted, or changed markup.",
        ),
        JobMasterStage.FORM_LOAD_TIMEOUT: (
            "JobMaster opened the application popup but did not finish loading the application form.",
            "Retry from the persistent session; if the popup still spins, inspect the network response or pause for human completion.",
        ),
        JobMasterStage.CV_UNVERIFIED: (
            "The expected current CV was not found in the JobMaster application popup.",
            "Upload or select the current CV before submitting.",
        ),
        JobMasterStage.PROFILE_INCOMPLETE: (
            "JobMaster reports missing profile fields in the application popup.",
            "Complete only verified candidate fields, then retry.",
        ),
        JobMasterStage.FORM_PREPARED: (
            "The JobMaster application form was prepared but not submitted.",
            "Run with submit mode when ready to send the application.",
        ),
        JobMasterStage.SUBMITTED: (
            "JobMaster confirmed the CV/application was sent successfully.",
            "Update the tracker and send the Telegram submitted alert.",
        ),
        JobMasterStage.SUBMIT_FAILED: (
            "JobMaster did not confirm a successful submission.",
            "Inspect the saved evidence and retry only after the blocker is clear.",
        ),
    }
    if stage == JobMasterStage.CV_UPLOADED:
        return (
            "The current CV was uploaded into the JobMaster application popup.",
            "Continue to submission after verifying the selected file and cover letter.",
        )
    if stage == JobMasterStage.CV_VERIFIED:
        return (
            "The expected current CV is available in the JobMaster application popup.",
            "Continue to submission." if submit else "Run with submit mode when ready to send the application.",
        )
    return reasons.get(stage, ("JobMaster application reached an unknown state.", "Inspect saved evidence before continuing."))


async def run_jobmaster_application(options: JobMasterOptions) -> JobMasterResult:
    config = build_session_config(options.job_url, root=options.root, site_name="JobMaster", headless=options.headless)
    stage = JobMasterStage.STARTED
    send_response = None
    playwright = None
    context = None
    page = None
    try:
        playwright, context = await launch_persistent_context(config)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(options.job_url, wait_until="domcontentloaded", timeout=options.timeout_ms)
        await page.wait_for_timeout(options.settle_ms)

        stage = classify_page_state(page.url, await visible_text(page)) or JobMasterStage.STARTED
        if stage == JobMasterStage.LOGIN_REQUIRED:
            stage = await login_if_needed(page, options) or JobMasterStage.STARTED
            if stage == JobMasterStage.LOGIN_REQUIRED:
                return await finalize(page, config, options, stage, send_response)

        if stage in {JobMasterStage.CLOSED_JOB, JobMasterStage.CAPTCHA_GATE, JobMasterStage.VERIFICATION_REQUIRED}:
            return await finalize(page, config, options, stage, send_response)

        form_stage = await open_application_form(page, options)
        if form_stage == JobMasterStage.LOGIN_REQUIRED:
            stage = await login_if_needed(page, options) or JobMasterStage.STARTED
            if stage == JobMasterStage.LOGIN_REQUIRED:
                return await finalize(page, config, options, stage, send_response)
            await page.goto(options.job_url, wait_until="domcontentloaded", timeout=options.timeout_ms)
            await page.wait_for_timeout(options.settle_ms)
            form_stage = await open_application_form(page, options)

        if form_stage and form_stage != JobMasterStage.APPLY_FORM_OPENED:
            return await finalize(page, config, options, form_stage, send_response)
        if form_stage != JobMasterStage.APPLY_FORM_OPENED:
            return await finalize(page, config, options, JobMasterStage.APPLY_BUTTON_MISSING, send_response)

        cv_stage = await ensure_current_cv(page, options)
        if cv_stage == JobMasterStage.CV_UNVERIFIED:
            return await finalize(page, config, options, cv_stage, send_response)

        await fill_cover_letter(page, options.cover_letter)
        if await form_has_profile_errors(page):
            return await finalize(page, config, options, JobMasterStage.PROFILE_INCOMPLETE, send_response)

        if not options.submit:
            return await finalize(page, config, options, JobMasterStage.FORM_PREPARED, send_response)

        stage, send_response = await submit_form(page, options)
        return await finalize(page, config, options, stage, send_response)
    except Exception as exc:
        if page is not None:
            return await finalize(page, config, options, JobMasterStage.ERROR, {"error": type(exc).__name__, "message": str(exc)})
        reason, next_step = reason_for_stage(JobMasterStage.ERROR, options.submit)
        return JobMasterResult(
            site="JobMaster",
            job_key=options.job_key,
            job_url=options.job_url,
            stage=JobMasterStage.ERROR.value,
            submitted=False,
            reason=f"{reason} {type(exc).__name__}: {exc}",
            next_step=next_step,
            current_url=options.job_url,
            evidence=None,
            cv_filename=options.cv_path.name if options.cv_path else "",
            send_response={"error": type(exc).__name__, "message": str(exc)},
        )
    finally:
        if options.keep_open and page is not None:
            print("JobMaster browser remains open. Press Enter here to close.")
            input()
        if context is not None:
            await context.close()
        if playwright is not None:
            await playwright.stop()


async def finalize(page, config, options: JobMasterOptions, stage: JobMasterStage, send_response: dict | None) -> JobMasterResult:
    reason, next_step = reason_for_stage(stage, options.submit)
    html = await page.content()
    screenshot = await page.screenshot(full_page=True)
    evidence = save_evidence(
        config=config,
        job_key=options.job_key,
        url=options.job_url,
        stage=f"jobmaster-{stage.value}",
        reason=reason,
        html=html,
        screenshot_bytes=screenshot,
        metadata={
            "options": {
                "submit": options.submit,
                "expected_cv_filename": expected_cv_name(options.cv_path, options.expected_cv_filename),
                "cv_path_name": options.cv_path.name if options.cv_path else "",
            },
            "current_url": page.url,
            "page_title": await page.title(),
            "send_response": send_response,
        },
    )
    return JobMasterResult(
        site="JobMaster",
        job_key=options.job_key,
        job_url=options.job_url,
        stage=stage.value,
        submitted=stage == JobMasterStage.SUBMITTED,
        reason=reason,
        next_step=next_step,
        current_url=page.url,
        evidence=evidence.metadata_path,
        cv_filename=options.cv_path.name if options.cv_path else "",
        send_response=send_response,
    )


def options_from_args(args: argparse.Namespace) -> JobMasterOptions:
    cv_path = args.cv or default_cv_path()
    return JobMasterOptions(
        job_url=args.job_url,
        job_key=args.job_key,
        cover_letter=args.cover_letter or "",
        cv_path=cv_path,
        expected_cv_filename=expected_cv_name(cv_path, args.expected_cv_filename or ""),
        email=args.email or os.environ.get("JOBMASTER_EMAIL", ""),
        password=args.password or os.environ.get("JOBMASTER_PASSWORD", ""),
        submit=args.submit,
        root=args.root,
        headless=args.headless,
        keep_open=args.keep_open,
        timeout_ms=args.timeout_ms,
        settle_ms=args.settle_ms,
    )


async def run(args: argparse.Namespace) -> int:
    result = await run_jobmaster_application(options_from_args(args))
    print_json(asdict(result))
    return 0 if result.stage not in {JobMasterStage.ERROR.value, JobMasterStage.SUBMIT_FAILED.value} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or submit a JobMaster application in a persistent browser session.")
    parser.add_argument("--job-url", required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--cover-letter", default="")
    parser.add_argument("--cv", type=Path)
    parser.add_argument("--expected-cv-filename", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--settle-ms", type=int, default=1500)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Actually submit after preparing the form.")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
