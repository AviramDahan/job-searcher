from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin

try:
    import requests
    from bs4 import BeautifulSoup, Tag
except ImportError as exc:  # pragma: no cover - exercised only on missing optional deps
    raise RuntimeError("Install scanner dependencies: pip install -r requirements.txt") from exc

try:
    from .candidate_profile import KOREN_DAHAN_PROFILE, assess_candidate_facts
    from .job_records import (
        COMPANY,
        COVER,
        CV,
        DATE,
        FIT,
        LINK,
        LOCATION,
        PENDING,
        REJECTED,
        REQUIREMENTS,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        TITLE,
        deduplicate_rows,
        job_key,
        load_rows,
        write_rows,
    )
    from .location_policy import LocationAssessment, LocationDecision, assess_location
    from .rebuild_summary import render as render_summary
    from .submission_engine import cover_letter_for_application, parse_summary_scanned_count, row_to_job
except ImportError:
    from candidate_profile import KOREN_DAHAN_PROFILE, assess_candidate_facts
    from job_records import (
        COMPANY,
        COVER,
        CV,
        DATE,
        FIT,
        LINK,
        LOCATION,
        PENDING,
        REJECTED,
        REQUIREMENTS,
        SCORE,
        STATUS,
        STOP_REASON,
        SUBMITTED,
        TITLE,
        deduplicate_rows,
        job_key,
        load_rows,
        write_rows,
    )
    from location_policy import LocationAssessment, LocationDecision, assess_location
    from rebuild_summary import render as render_summary
    from submission_engine import cover_letter_for_application, parse_summary_scanned_count, row_to_job


DEFAULT_TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

ROLE_TERMS = {
    "procurement": ("רכש", "קניין", "קניינ", "buyer", "procurement", "sourcing", "ספק"),
    "finance": ("כלכל", "תקציב", "בקרה תקציבית", "financial analyst", "economist", "budget", "אנליסט"),
    "ops": ("שרשרת אספקה", "supply chain", "תכנון", "planner", "project controller", "pmo", "התקשרויות", "חוזים"),
}

TARGET_LOCATION_TERMS = (
    "שדרות",
    "נתיבות",
    "אשקלון",
    "קריית גת",
    "קרית גת",
    "באר שבע",
    'ב"ש',
    "אשדוד",
    "אופקים",
    "קריית מלאכי",
    "קרית מלאכי",
    "באר טוביה",
    "תימורים",
    "דרום",
)

SECONDARY_LOCATION_TERMS = (
    "יבנה",
    "רחובות",
    "לוד",
    "רמלה",
    "נס ציונה",
    "ראשון לציון",
)

TITLE_HARD_EXCLUDE_TERMS = (
    "מכירות",
    "שירות לקוחות",
    "מוקד",
    "טלמרקטינג",
    "הנהלת חשבונות",
    "מנהל/ת חשבונות",
    "מנהל חשבונות",
    "מנהלת חשבונות",
    "חשב/ת",
    "חשב שכר",
    "חשבות שכר",
    "רואה חשבון",
    'רו"ח',
    "audit",
    "מתכנת",
    "מפתח",
    "תוכנה",
    "software",
    "qa",
    "מחסנאי",
    "מלגזן",
    "מלקט",
    "ליקוט",
    "צוותי ניהול",
    "מעצב",
    "מעצבת",
    "אופנה",
)

BODY_HARD_EXCLUDE_TERMS = (
    "שירות לקוחות",
    "טלמרקטינג",
    "מוקד",
    "הנהלת חשבונות",
    "מנהל/ת חשבונות",
    "מנהל חשבונות",
    "מנהלת חשבונות",
    "חשב שכר",
    "רואה חשבון",
    'רו"ח',
    "software developer",
    "פיתוח תוכנה",
    "מחסנאי",
    "מלגזן",
    "מלקט",
    "ליקוט",
)

WAREHOUSE_CORE_TERMS = (
    "ניהול מחסן",
    "אחראי מחסן",
    "מחסן (טכני)",
    "תפעול מחסן",
)

SENIOR_EXCLUDE_TERMS = (
    "ראש תחום",
    "ראש/ת תחום",
    "מנהל/ת אפסנאות",
    "מנהל.ת אפסנאות",
    "מנהל אפסנאות",
    "מנהלת אפסנאות",
    "מנהל/ת אפסנאות ורכש",
    "מנהל.ת אפסנאות ורכש",
    "מנהל/ת רכש",
    "מנהל/ת מחלקת רכש",
    "מנהל.ת רכש",
    "מנהל.ת מחלקת רכש",
    "מנהל רכש",
    "מנהל מחלקת רכש",
    "מנהלת רכש",
    "מנהלת מחלקת רכש",
    "procurement manager",
    "סמנכ",
    "director",
    "ראש צוות",
)

SHORT_TEMP_TERMS = (
    "זמני",
    "זמנית",
    "4-6 חודשים",
    "שלושה חודשים",
    "temporary",
)

GOOD_REQUIREMENT_TERMS = (
    "תואר",
    "כלכלה",
    "ניהול",
    "excel",
    "אקסל",
    "office",
    "אנגלית",
    "ספקים",
    "הצעות מחיר",
    'מו"מ',
    "משא ומתן",
    "הזמנות",
    "חשבוניות",
    "תקציב",
    "ניתוח",
    "דוחות",
    "priority",
    "חשבשבת",
)

JUNIOR_TERMS = (
    "ללא ניסיון",
    "עד שנתיים",
    "עד 2",
    "1-2",
    "0-2",
    "0-3",
    "שנה ניסיון",
    "junior",
    "בוגר",
)

THREE_YEAR_TERMS = ("3 שנים", "שלוש שנים", "שלוש שנות", "3 שנות", "3+")
OVER_EXPERIENCE_TERMS = (
    "4 שנים",
    "ארבע שנים",
    "ארבע שנות",
    "4 שנות",
    "4+",
    "5 שנים",
    "חמש שנים",
    "חמש שנות",
    "5 שנות",
    "5+",
    "five years",
    "6 שנים",
    "7 שנים",
    "8 שנים",
    "10 שנים",
)


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    parser: str


@dataclass(frozen=True)
class DiscoveredJob:
    source: str
    title: str
    company: str
    location: str
    link: str
    description: str
    requirements: str
    posted: str = ""


@dataclass(frozen=True)
class ScoredJob:
    job: DiscoveredJob
    score: int
    status: str
    requirements: str
    fit: str
    stop_reason: str
    hard_reasons: tuple[str, ...]
    caution_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DiscoveryResult:
    scanned_cards: int
    parsed_jobs: int
    new_rows: int
    rescored_existing: int
    refreshed_existing: int
    skipped_existing: int
    rejected_new: int
    pending_new: int
    source_errors: dict[str, str]
    new_job_keys: list[str]


def default_sources() -> list[Source]:
    jobmaster_terms = ["רכש", "קניין", "כלכלן", "תקציב", "בקרה תקציבית", "PMO", "sourcing", "procurement", "buyer"]
    drushim_terms = ["רכש", "קניין", "כלכלן", "תקציב", "בקרה", "PMO", "sourcing", "procurement"]
    jobnet_urls = [
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=655&searchtype=byareas",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=655&searchtype=byareas&subarea=24",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=655&searchtype=byareas&subarea=25",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=655&searchtype=byareas&subarea=26",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=655&searchtype=byareas&subarea=32",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=654&searchtype=byareas&subprofid=881",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=654&searchtype=byareas&subprofid=749",
        "https://www.jobnet.co.il/jobs?checkarea=1&profid=650&searchtype=byareas",
    ]
    sources = [Source("JobMaster", f"https://www.jobmaster.co.il/jobs/?q={quote(term)}", "jobmaster") for term in jobmaster_terms]
    sources.extend(Source("Drushim", f"https://www.drushim.co.il/jobs/search/{quote(term)}/", "drushim") for term in drushim_terms)
    sources.extend(Source("Jobnet", url, "jobnet") for url in jobnet_urls)
    return sources


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def lower_text(value: str) -> str:
    return clean_text(value).lower()


def has_any(text: str, terms: Iterable[str]) -> bool:
    lowered = lower_text(text)
    return any(term.lower() in lowered for term in terms)


def fetch_html(session: requests.Session, url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "windows-1252"}:
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href or "")


def parse_jobmaster(html: str, source_url: str) -> list[DiscoveredJob]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[DiscoveredJob] = []
    for article in soup.select("article.JobItem"):
        title_link = article.select_one("a.CardHeader[href*='checknum.asp?key=']")
        if not title_link:
            continue
        company = clean_text(article.select_one(".CompanyNameLink").get_text(" ", strip=True) if article.select_one(".CompanyNameLink") else "")
        location = clean_text(article.select_one(".jobLocation").get_text(" ", strip=True) if article.select_one(".jobLocation") else "")
        description = clean_text(article.select_one(".jobShortDescription").get_text(" ", strip=True) if article.select_one(".jobShortDescription") else "")
        posted = clean_text(article.select_one(".Gray").get_text(" ", strip=True) if article.select_one(".Gray") else "")
        jobs.append(
            DiscoveredJob(
                source="JobMaster",
                title=clean_text(title_link.get_text(" ", strip=True)),
                company=company or "חסוי / JobMaster",
                location=location,
                link=absolute_url(source_url, title_link.get("href", "")),
                description=description,
                requirements=description,
                posted=posted,
            )
        )
    return jobs


def parse_jobnet(html: str, source_url: str) -> list[DiscoveredJob]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[DiscoveredJob] = []
    seen: set[str] = set()
    for box in soup.select("div.inerbox"):
        title_link = box.select_one("a[href*='positionid='] h2")
        if not title_link:
            continue
        anchor = title_link.find_parent("a")
        if not isinstance(anchor, Tag):
            continue
        link = absolute_url(source_url, anchor.get("href", ""))
        if link in seen:
            continue
        seen.add(link)
        description = clean_text(box.select_one("[itemprop='description']").get_text(" ", strip=True) if box.select_one("[itemprop='description']") else "")
        skills = clean_text(box.select_one("[itemprop='skills']").get_text(" ", strip=True) if box.select_one("[itemprop='skills']") else "")
        locations = [clean_text(item.get_text(" ", strip=True)) for item in box.select("span.reg")]
        company = clean_text(box.select_one("[itemprop='hiringOrganization']").get_text(" ", strip=True) if box.select_one("[itemprop='hiringOrganization']") else "")
        posted = clean_text(box.select_one(".boxDateCls").get_text(" ", strip=True) if box.select_one(".boxDateCls") else "")
        jobs.append(
            DiscoveredJob(
                source="Jobnet",
                title=clean_text(title_link.get_text(" ", strip=True)),
                company=company or "חסוי / Jobnet",
                location="; ".join(locations),
                link=link,
                description=description,
                requirements=skills,
                posted=posted,
            )
        )
    return jobs


def parse_drushim(html: str, source_url: str) -> list[DiscoveredJob]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[DiscoveredJob] = []
    seen: set[str] = set()
    for item in soup.select("[data-cy^='job-item']"):
        link_node = item.select_one("a[href^='/job/']")
        if not link_node:
            continue
        link = absolute_url(source_url, link_node.get("href", ""))
        if link in seen:
            continue
        seen.add(link)
        title = clean_text(item.select_one("h3").get_text(" ", strip=True) if item.select_one("h3") else "")
        company = clean_text(item.select_one(".bidi").get_text(" ", strip=True) if item.select_one(".bidi") else "")
        intro = clean_text(item.select_one(".job-intro").get_text(" ", strip=True) if item.select_one(".job-intro") else "")
        meta = clean_text(item.select_one(".job-details-sub").get_text(" ", strip=True) if item.select_one(".job-details-sub") else "")
        location = meta.split("|", 1)[0].strip() if meta else ""
        posted_match = re.search(r"(לפני [^|]+|\d{2}/\d{2}/\d{4})", meta)
        jobs.append(
            DiscoveredJob(
                source="Drushim",
                title=title,
                company=company or "חסוי / Drushim",
                location=location,
                link=link,
                description=intro,
                requirements=intro,
                posted=posted_match.group(1).strip() if posted_match else "",
            )
        )
    return jobs


PARSERS = {
    "jobmaster": parse_jobmaster,
    "jobnet": parse_jobnet,
    "drushim": parse_drushim,
}


def merge_detail(job: DiscoveredJob, html: str) -> DiscoveredJob:
    soup = BeautifulSoup(html, "lxml")
    text = clean_text(soup.get_text(" ", strip=True))
    if job.source == "JobMaster":
        description_node = soup.select_one("#jobDescriptionContent")
        requirements_node = soup.select_one("#jobRequirementsContent")
        if description_node or requirements_node:
            description = clean_text(description_node.get_text(" ", strip=True) if description_node else job.description)
            requirements = clean_text(requirements_node.get_text(" ", strip=True) if requirements_node else job.requirements)
            title_node = soup.select_one(".jobHead__text__titleAndCompName .CardHeader")
            company_node = soup.select_one(".CompanyNameLink")
            location_node = soup.select_one("#jobLocationData")
            return DiscoveredJob(
                source=job.source,
                title=clean_text(title_node.get_text(" ", strip=True) if title_node else job.title),
                company=clean_text(company_node.get_text(" ", strip=True) if company_node else job.company),
                location=clean_text(location_node.get_text(" ", strip=True) if location_node else job.location),
                link=job.link,
                description=clean_text(" ".join(part for part in [description, requirements] if part))[:2500] or job.description,
                requirements=requirements[:2500] or job.requirements,
                posted=job.posted,
            )
        marker = "תיאור המשרה:"
        details = text[text.find(marker) :] if marker in text else text
        return DiscoveredJob(
            source=job.source,
            title=job.title,
            company=job.company,
            location=job.location,
            link=job.link,
            description=details[:2500] or job.description,
            requirements=details[:2500] or job.requirements,
            posted=job.posted,
        )
    if job.source == "Drushim":
        posting = extract_jobposting_jsonld(soup)
        filters = extract_drushim_filters(html)
        body_detail = extract_drushim_body_detail(text)
        if posting:
            description = clean_html_text(str(posting.get("description", "")))
            requirements = clean_text(" ".join(part for part in [body_detail or description, filters] if part))
            organization = posting.get("hiringOrganization") if isinstance(posting.get("hiringOrganization"), dict) else {}
            location_payload = posting.get("jobLocation") if isinstance(posting.get("jobLocation"), dict) else {}
            address = location_payload.get("address") if isinstance(location_payload.get("address"), dict) else {}
            return DiscoveredJob(
                source=job.source,
                title=clean_text(str(posting.get("title") or job.title)),
                company=clean_text(str(organization.get("name") or job.company)),
                location=clean_text(str(address.get("addressLocality") or job.location)),
                link=job.link,
                description=(body_detail or description)[:2500] or job.description,
                requirements=requirements[:2500] or job.requirements,
                posted=clean_text(str(posting.get("datePosted") or job.posted)),
            )
        h1 = clean_text(soup.select_one("h1").get_text(" ", strip=True) if soup.select_one("h1") else job.title)
        meta_description = soup.select_one("meta[name='description']")
        description = body_detail or clean_text(meta_description.get("content", "") if meta_description else "")
        requirements = clean_text(" ".join(part for part in [description, filters] if part))
        return DiscoveredJob(
            source=job.source,
            title=h1 or job.title,
            company=job.company,
            location=job.location,
            link=job.link,
            description=description[:2500] or job.description,
            requirements=requirements[:2500] or job.requirements,
            posted=job.posted,
        )
    return job


def extract_drushim_filters(html: str) -> str:
    match = re.search(r"Filters:\[(?P<filters>.*?)\],Salary", html or "", flags=re.DOTALL)
    if not match:
        return ""
    values: list[str] = []
    for quoted in re.finditer(r'"((?:\\.|[^"])*)"', match.group("filters")):
        raw = quoted.group(1)
        try:
            values.append(json.loads(f'"{raw}"'))
        except json.JSONDecodeError:
            values.append(raw)
    clean_values = [clean_text(value) for value in values if clean_text(value)]
    return "שאלות סינון: " + " | ".join(clean_values) if clean_values else ""


def extract_drushim_body_detail(text: str) -> str:
    start_markers = ("תיאור משרה", "דרישות התפקיד")
    end_markers = ("לפרופיל החברה", "קטגוריה", "קבל התראות", "דרושים IL אתר הדרושים")
    start_positions = [clean_text(text).find(marker) for marker in start_markers if marker in clean_text(text)]
    if not start_positions:
        return ""
    start = min(pos for pos in start_positions if pos >= 0)
    end_candidates = [clean_text(text).find(marker, start + 1) for marker in end_markers if clean_text(text).find(marker, start + 1) > start]
    end = min(end_candidates) if end_candidates else start + 2500
    return clean_text(text[start:end])[:2500]


def clean_html_text(value: str) -> str:
    return clean_text(BeautifulSoup(value or "", "lxml").get_text(" ", strip=True))


def iter_jsonld_items(payload: object) -> Iterable[dict]:
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    yield item
        yield payload
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_jsonld_items(item)


def extract_jobposting_jsonld(soup: BeautifulSoup) -> dict | None:
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in iter_jsonld_items(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" in types:
                return item
    return None


def role_score(text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for label, terms in ROLE_TERMS.items():
        if has_any(text, terms):
            if label == "procurement":
                score += 43
                reasons.append("התאמה לליבת רכש/קניינות/ספקים")
            elif label == "finance":
                score += 36
                reasons.append("התאמה לכלכלה/תקציבים/בקרה/אנליזה")
            else:
                score += 26
                reasons.append("התאמה לשרשרת אספקה/PMO/התקשרויות")
    return min(score, 52), reasons


def location_score(job: DiscoveredJob) -> tuple[int, list[str], LocationAssessment]:
    context = " ".join([job.title, job.company, job.description, job.requirements, job.posted])
    assessment = assess_location(job.location, context)
    reasons = [assessment.reason] if assessment.decision != LocationDecision.OUT_OF_SCOPE else []
    return assessment.score_points, reasons, assessment


def requirement_score(text: str) -> tuple[int, list[str]]:
    matched = [term for term in GOOD_REQUIREMENT_TERMS if term.lower() in lower_text(text)]
    score = min(24, len(set(matched)) * 3)
    reasons = []
    if matched:
        reasons.append("דרישות תואמות: " + ", ".join(dict.fromkeys(matched[:7])))
    if has_any(text, JUNIOR_TERMS):
        score += 8
        reasons.append("ניסיון נדרש מתאים לפרופיל ג'וניור/עד 3 שנים")
    return min(score, 30), reasons


def exclusion_reasons(text: str, title: str = "") -> tuple[list[str], list[str]]:
    hard: list[str] = []
    caution: list[str] = []
    titleish = title or text[:250]
    if has_any(titleish, TITLE_HARD_EXCLUDE_TERMS) or has_any(text, BODY_HARD_EXCLUDE_TERMS):
        hard.append("נפסל: מופיעים רכיבי תפקיד מחוץ ליעד כמו מכירות/שירות/הנהלת חשבונות/תכנות/מחסן.")
    if has_any(titleish, WAREHOUSE_CORE_TERMS):
        hard.append("נפסל: ליבת התפקיד כוללת ניהול/תפעול מחסן ולא רכש/בקרה כתחום מרכזי.")
    if has_any(titleish, SENIOR_EXCLUDE_TERMS):
        hard.append("נפסל: התפקיד נראה כתפקיד ניהול בכיר או מנהל/ת רכש.")
    if has_any(text, SHORT_TEMP_TERMS):
        caution.append("המשרה נראית זמנית או קצרה ודורשת בדיקה לפני הגשה.")
    if has_any(text, OVER_EXPERIENCE_TERMS):
        hard.append("נפסל: דרישת הניסיון גבוהה משמעותית מהפרופיל שהוגדר.")
    elif has_any(text, THREE_YEAR_TERMS):
        caution.append("יש דרישת ניסיון סביב 3 שנים, לכן נדרש אישור/בדיקה לפני הגשה.")
    return hard, caution


def score_job(job: DiscoveredJob) -> ScoredJob:
    context = " ".join([job.title, job.company, job.location, job.description, job.requirements, job.posted])
    role_points, role_reasons = role_score(context)
    loc_points, loc_reasons, location_assessment = location_score(job)
    req_points, req_reasons = requirement_score(context)
    hard, caution = exclusion_reasons(context, job.title)
    fact_assessment = assess_candidate_facts(context, profile=KOREN_DAHAN_PROFILE)

    hard.extend(issue.reason for issue in fact_assessment.blockers if issue.severity.value == "do_not_apply")
    caution.extend(
        issue.reason
        for issue in fact_assessment.blockers
        if issue.severity.value != "do_not_apply" and getattr(issue, "code", "") != "work_model_unverified"
    )
    if not role_reasons:
        hard.append("נפסל: לא זוהתה התאמה מקצועית מספקת לתחומי היעד.")
    if location_assessment.decision == LocationDecision.OUT_OF_SCOPE:
        hard.append(location_assessment.reason)
    elif location_assessment.decision == LocationDecision.APPROVAL_REQUIRED:
        caution.append(location_assessment.reason)

    score = max(0, min(100, 18 + role_points + loc_points + req_points - len(hard) * 28 - len(caution) * 8))
    fit_reasons = role_reasons + loc_reasons + req_reasons
    requirements = clean_text(job.requirements or job.description)[:900]
    fit = "; ".join(fit_reasons)[:900] or "התאמה לא מספקת לפי הסריקה הראשונית."

    if score < 70 or hard:
        status = REJECTED
        stop_reason = " ".join(hard or [f"נפסל בסריקה אוטומטית: ציון התאמה {score}/100 מתחת לסף 70."])
    else:
        status = PENDING
        stop_reason = "נמצא בסריקה חדשה; נדרש מעבר מנוע ההגשה לפני שליחה."
        if caution:
            stop_reason = "נדרש אישור לפני הגשה: " + " ".join(caution)

    return ScoredJob(
        job=job,
        score=score,
        status=status,
        requirements=requirements,
        fit=fit,
        stop_reason=clean_text(stop_reason)[:900],
        hard_reasons=tuple(hard),
        caution_reasons=tuple(caution),
    )


def row_from_scored(scored: ScoredJob, today: str) -> dict[str, str]:
    row = {
        DATE: today,
        COMPANY: scored.job.company,
        TITLE: scored.job.title,
        LOCATION: scored.job.location,
        LINK: scored.job.link,
        SCORE: str(scored.score),
        REQUIREMENTS: scored.requirements,
        FIT: scored.fit,
        STATUS: scored.status,
        STOP_REASON: scored.stop_reason,
        COVER: "",
        CV: "",
    }
    if scored.status == PENDING:
        row[COVER] = cover_letter_for_application(row_to_job(row), KOREN_DAHAN_PROFILE)
    return row


SCANNER_STOP_MARKERS = (
    "נמצא בסריקה חדשה",
    "נדרש אישור לפני הגשה",
    "נפסל בסריקה אוטומטית",
    "נפסל: מופיעים רכיבי תפקיד",
    "נפסל: ליבת התפקיד",
    "נפסל: התפקיד נראה",
    "נפסל: דרישת הניסיון",
    "נפסל: המיקום",
    "נפסל: לא זוהתה התאמה מקצועית",
    "appears to be a required skill",
)

MANUAL_DECISION_MARKERS = (
    "בחירה ידנית",
    "dashboard",
    "הוגש ידנית",
    "הוגש בהצלחה",
)

REVIEW_DECISION_MARKERS = MANUAL_DECISION_MARKERS + (
    "באתר הרשמי",
    "טופס ההגשה",
    "לאחר בדיקה",
    "אין לחתום",
    "לפני כל הגשה",
    "Manual required:",
    "Rejected: duplicate",
    "נעצר:",
    "נעצר בטופס",
)


def is_scanner_managed_row(row: dict[str, str]) -> bool:
    if row.get(STATUS) == "הוגש":
        return False
    reason = row.get(STOP_REASON, "")
    if any(marker in reason for marker in REVIEW_DECISION_MARKERS):
        return False
    return any(marker in reason for marker in SCANNER_STOP_MARKERS)


def update_scanner_row(existing: dict[str, str], scored: ScoredJob) -> bool:
    manual_decision = any(marker in existing.get(STOP_REASON, "") for marker in REVIEW_DECISION_MARKERS)
    if not is_scanner_managed_row(existing) and not (scored.status == REJECTED and existing.get(STATUS) != SUBMITTED and not manual_decision):
        return False
    updated = row_from_scored(scored, existing.get(DATE, "") or datetime.now().strftime("%Y-%m-%d"))
    updated[DATE] = existing.get(DATE, updated[DATE])
    preserve_pending_approval = (
        existing.get(STATUS) == PENDING
        and existing.get(STOP_REASON, "").startswith("נדרש אישור לפני הגשה")
        and updated.get(STATUS) == PENDING
        and updated.get(STOP_REASON, "").startswith("נמצא בסריקה חדשה")
    )
    changed = False
    for field in (COMPANY, TITLE, LOCATION, LINK, SCORE, REQUIREMENTS, FIT, STATUS, STOP_REASON, COVER, CV):
        if preserve_pending_approval and field in {STATUS, STOP_REASON}:
            continue
        if existing.get(field, "") != updated.get(field, ""):
            existing[field] = updated.get(field, "")
            changed = True
    return changed


def source_from_link(link: str) -> str:
    lowered = (link or "").lower()
    if "jobmaster.co.il" in lowered:
        return "JobMaster"
    if "drushim.co.il" in lowered:
        return "Drushim"
    if "jobnet.co.il" in lowered:
        return "Jobnet"
    return "Unsupported"


def job_from_row(row: dict[str, str]) -> DiscoveredJob:
    return DiscoveredJob(
        source=source_from_link(row.get(LINK, "")),
        title=row.get(TITLE, ""),
        company=row.get(COMPANY, ""),
        location=row.get(LOCATION, ""),
        link=row.get(LINK, ""),
        description=row.get(REQUIREMENTS, ""),
        requirements=row.get(REQUIREMENTS, ""),
    )


def scan_sources(sources: list[Source], detail_limit: int = 80, timeout: int = DEFAULT_TIMEOUT) -> tuple[list[DiscoveredJob], int, dict[str, str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"})
    jobs: list[DiscoveredJob] = []
    errors: dict[str, str] = {}
    scanned_cards = 0
    for source in sources:
        parser = PARSERS[source.parser]
        try:
            parsed = parser(fetch_html(session, source.url, timeout=timeout), source.url)
        except Exception as exc:
            errors[source.url] = f"{type(exc).__name__}: {exc}"
            continue
        scanned_cards += len(parsed)
        jobs.extend(parsed)

    unique: dict[str, DiscoveredJob] = {}
    for job in jobs:
        if job.link and job.link not in unique:
            unique[job.link] = job

    detailed: list[DiscoveredJob] = []
    for index, job in enumerate(unique.values()):
        if index >= detail_limit or job.source == "Jobnet":
            detailed.append(job)
            continue
        try:
            detailed.append(merge_detail(job, fetch_html(session, job.link, timeout=timeout)))
        except Exception:
            detailed.append(job)
    return detailed, scanned_cards, errors


def discover(
    csv_path: Path,
    summary_path: Path,
    json_path: Path,
    md_path: Path,
    max_sources: int | None = None,
    detail_limit: int = 80,
    timezone: str = "Asia/Jerusalem",
    rescore_existing: bool = False,
    refresh_existing_limit: int = 60,
    timeout: int = DEFAULT_TIMEOUT,
) -> DiscoveryResult:
    rows = load_rows(csv_path)
    existing_by_key: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        existing_by_key.setdefault(job_key(row), []).append(row)
    existing_keys = set(existing_by_key)
    sources = default_sources()[:max_sources] if max_sources else default_sources()
    jobs, scanned_cards, errors = scan_sources(sources, detail_limit=detail_limit, timeout=timeout)
    today = datetime.now().strftime("%Y-%m-%d")

    scored_jobs = [score_job(job) for job in jobs]
    scored_jobs.sort(key=lambda item: (-item.score, item.job.source, item.job.title))
    scanned_keys = {job_key(row_from_scored(scored, today)) for scored in scored_jobs}
    new_keys: list[str] = []
    skipped_existing = 0
    rescored_existing = 0
    pending_new = 0
    rejected_new = 0
    for scored in scored_jobs:
        row = row_from_scored(scored, today)
        key = job_key(row)
        if key in existing_keys:
            changed = False
            if rescore_existing:
                for existing in existing_by_key[key]:
                    changed = update_scanner_row(existing, scored) or changed
            if changed:
                rescored_existing += 1
            else:
                skipped_existing += 1
            continue
        existing_keys.add(key)
        existing_by_key[key] = [row]
        rows.append(row)
        new_keys.append(key)
        if row[STATUS] == PENDING:
            pending_new += 1
        elif row[STATUS] == REJECTED:
            rejected_new += 1

    refreshed_existing = 0
    if rescore_existing and refresh_existing_limit > 0:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"})
        for existing in rows:
            if refreshed_existing >= refresh_existing_limit:
                break
            key = job_key(existing)
            if key in scanned_keys or existing.get(STATUS) == SUBMITTED:
                continue
            if source_from_link(existing.get(LINK, "")) not in {"JobMaster", "Drushim"}:
                continue
            if existing.get(STATUS) == REJECTED and int(existing.get(SCORE, "0") or "0") < 70:
                continue
            try:
                refreshed_job = merge_detail(job_from_row(existing), fetch_html(session, existing.get(LINK, ""), timeout=timeout))
            except Exception:
                continue
            if update_scanner_row(existing, score_job(refreshed_job)):
                refreshed_existing += 1

    rows = deduplicate_rows(rows)
    write_rows(csv_path, rows)
    old_scanned = parse_summary_scanned_count(summary_path, default=len(rows))
    summary_path.write_text(render_summary(rows, old_scanned + scanned_cards, 0, timezone), encoding="utf-8-sig")

    result = DiscoveryResult(
        scanned_cards=scanned_cards,
        parsed_jobs=len(scored_jobs),
        new_rows=len(new_keys),
        rescored_existing=rescored_existing,
        refreshed_existing=refreshed_existing,
        skipped_existing=skipped_existing,
        rejected_new=rejected_new,
        pending_new=pending_new,
        source_errors=errors,
        new_job_keys=new_keys,
    )
    write_discovery_outputs(scored_jobs, result, json_path, md_path)
    return result


def write_discovery_outputs(scored_jobs: list[ScoredJob], result: DiscoveryResult, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"result": asdict(result), "jobs": [asdict(item) for item in scored_jobs]}, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    lines = [
        "# Discovery Scan Report",
        "",
        f"- scanned_cards: {result.scanned_cards}",
        f"- parsed_jobs: {result.parsed_jobs}",
        f"- new_rows: {result.new_rows}",
        f"- rescored_existing: {result.rescored_existing}",
        f"- refreshed_existing: {result.refreshed_existing}",
        f"- pending_new: {result.pending_new}",
        f"- rejected_new: {result.rejected_new}",
        f"- skipped_existing: {result.skipped_existing}",
        "",
        "## Top Scored Jobs",
    ]
    for item in scored_jobs[:30]:
        lines.append(
            f"- {item.score}/100 - {item.job.source} - {item.job.company} - "
            f"[{item.job.title}]({item.job.link}) - {item.job.location} - {item.status} - {item.stop_reason}"
        )
    if result.source_errors:
        lines.extend(["", "## Source Errors"])
        for url, error in result.source_errors.items():
            lines.append(f"- {url}: {error}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_json(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan public job sources and add newly discovered rows to the tracker.")
    parser.add_argument("--csv", type=Path, default=Path("outputs/job_applications.csv"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/job_search_summary.md"))
    parser.add_argument("--json", type=Path, default=Path("outputs/discovery_scan_report.json"))
    parser.add_argument("--md", type=Path, default=Path("outputs/discovery_scan_report.md"))
    parser.add_argument("--max-sources", type=int)
    parser.add_argument("--detail-limit", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--timezone", default="Asia/Jerusalem")
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Recalculate rows created by this scanner while preserving submitted/manual dashboard decisions.",
    )
    parser.add_argument("--refresh-existing-limit", type=int, default=60)
    args = parser.parse_args()

    result = discover(
        csv_path=args.csv,
        summary_path=args.summary,
        json_path=args.json,
        md_path=args.md,
        max_sources=args.max_sources,
        detail_limit=args.detail_limit,
        timezone=args.timezone,
        rescore_existing=args.rescore_existing,
        refresh_existing_limit=args.refresh_existing_limit,
        timeout=args.timeout,
    )
    print_json(asdict(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
