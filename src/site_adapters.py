from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

try:
    from .submission_failures import AutomationAction, FailureClassification, classify_failure
except ImportError:
    from submission_failures import AutomationAction, FailureClassification, classify_failure


class SiteCapability(str, Enum):
    DIRECT_FORM = "direct_form"
    PERSISTENT_LOGIN = "persistent_login"
    EXTERNAL_APPLY = "external_apply"
    CAPTCHA_GATE = "captcha_gate"
    MARKETING_CONSENT_RISK = "marketing_consent_risk"
    COMPANY_SITE_FALLBACK = "company_site_fallback"


@dataclass(frozen=True)
class SiteAdapterProfile:
    name: str
    domains: tuple[str, ...]
    capabilities: tuple[SiteCapability, ...]
    default_action: AutomationAction
    notes: str


ADAPTERS = (
    SiteAdapterProfile(
        name="JobMaster",
        domains=("jobmaster.co.il", "www.jobmaster.co.il", "account.jobmaster.co.il", "people.jobmaster.co.il"),
        capabilities=(SiteCapability.DIRECT_FORM, SiteCapability.PERSISTENT_LOGIN),
        default_action=AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
        notes="Generally workable after login. Verify CV profile freshness before every submission.",
    ),
    SiteAdapterProfile(
        name="Jobnet",
        domains=("jobnet.co.il", "www.jobnet.co.il"),
        capabilities=(SiteCapability.DIRECT_FORM,),
        default_action=AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
        notes="Worked reliably with direct POST flows; keep evidence for response confirmation.",
    ),
    SiteAdapterProfile(
        name="LinkedIn",
        domains=("linkedin.com", "www.linkedin.com", "il.linkedin.com"),
        capabilities=(SiteCapability.PERSISTENT_LOGIN, SiteCapability.EXTERNAL_APPLY, SiteCapability.COMPANY_SITE_FALLBACK),
        default_action=AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
        notes="Requires persistent authenticated browser state. Prefer company-site fallback for external apply jobs.",
    ),
    SiteAdapterProfile(
        name="AllJobs",
        domains=("alljobs.co.il", "www.alljobs.co.il"),
        capabilities=(SiteCapability.CAPTCHA_GATE, SiteCapability.COMPANY_SITE_FALLBACK),
        default_action=AutomationAction.FILL_UNTIL_HUMAN_GATE,
        notes="Often blocks automation with Radware. Search official company page before manual handoff.",
    ),
    SiteAdapterProfile(
        name="Drushim",
        domains=("drushim.co.il", "www.drushim.co.il"),
        capabilities=(SiteCapability.PERSISTENT_LOGIN, SiteCapability.MARKETING_CONSENT_RISK, SiteCapability.COMPANY_SITE_FALLBACK),
        default_action=AutomationAction.HUMAN_APPROVAL_REQUIRED,
        notes="Registration/login can include third-party marketing consent. Continue only when the local candidate profile explicitly approves it.",
    ),
    SiteAdapterProfile(
        name="DSV SuccessFactors",
        domains=("jobs.dsv.com",),
        capabilities=(SiteCapability.PERSISTENT_LOGIN, SiteCapability.DIRECT_FORM),
        default_action=AutomationAction.RETRY_WITH_PERSISTENT_SESSION,
        notes="Use persistent session and field-level verification; SuccessFactors fields can reject synthetic input.",
    ),
    SiteAdapterProfile(
        name="IAI Careers",
        domains=("jobs.iai.co.il",),
        capabilities=(SiteCapability.DIRECT_FORM, SiteCapability.CAPTCHA_GATE),
        default_action=AutomationAction.FILL_UNTIL_HUMAN_GATE,
        notes="Official forms may require ID, relatives disclosure, legal declaration, and reCAPTCHA.",
    ),
    SiteAdapterProfile(
        name="Nestle Careers",
        domains=("jobdetails.nestle.com",),
        capabilities=(SiteCapability.DIRECT_FORM, SiteCapability.CAPTCHA_GATE),
        default_action=AutomationAction.FILL_UNTIL_HUMAN_GATE,
        notes="Official career page can show security checks. Continue only after human passes gate.",
    ),
    SiteAdapterProfile(
        name="Jobify",
        domains=("jobify360.co.il",),
        capabilities=(SiteCapability.EXTERNAL_APPLY, SiteCapability.COMPANY_SITE_FALLBACK),
        default_action=AutomationAction.USE_COMPANY_SITE_FALLBACK,
        notes="Aggregator. Prefer finding the official company form.",
    ),
)


@dataclass(frozen=True)
class SubmissionRoute:
    adapter: SiteAdapterProfile | None
    failure: FailureClassification
    recommended_action: AutomationAction
    is_code_fixable: bool
    requires_human: bool
    route_notes: str


def _domain_matches(domain: str, candidate: str) -> bool:
    return domain == candidate or domain.endswith("." + candidate)


def adapter_for_url(url: str) -> SiteAdapterProfile | None:
    domain = urlparse(url).netloc.lower()
    for adapter in ADAPTERS:
        if any(_domain_matches(domain, candidate.lower()) for candidate in adapter.domains):
            return adapter
    return None


def route_submission_failure(reason: str, link: str, title: str = "", company: str = "") -> SubmissionRoute:
    adapter = adapter_for_url(link)
    failure = classify_failure(reason=reason, link=link, title=title, company=company)
    action = failure.action

    if adapter and failure.kind.value == "unknown":
        action = adapter.default_action

    route_notes = adapter.notes if adapter else "No site adapter exists yet; inspect manually and add a profile if repeated."
    return SubmissionRoute(
        adapter=adapter,
        failure=failure,
        recommended_action=action,
        is_code_fixable=failure.can_improve_with_code,
        requires_human=failure.requires_human,
        route_notes=route_notes,
    )


def known_sites() -> list[dict[str, object]]:
    return [
        {
            "name": adapter.name,
            "domains": list(adapter.domains),
            "capabilities": [capability.value for capability in adapter.capabilities],
            "default_action": adapter.default_action.value,
            "notes": adapter.notes,
        }
        for adapter in ADAPTERS
    ]
