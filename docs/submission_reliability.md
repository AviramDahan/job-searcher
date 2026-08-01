# Submission Reliability Layer

This layer addresses the main reason applications became "manual submission required": the old workflow treated every failed form as a one-off event. The new workflow classifies failures, chooses a repeatable route, and stores evidence so the operator can continue from the exact failure point.

## Failure Categories

- `login_or_account`: The site needs login, account creation, or stable session state. Fix with persistent browser profiles.
- `captcha_or_security`: The site presented CAPTCHA, reCAPTCHA, Radware, Cloudflare, or similar. Fill safe fields and pause for a human.
- `form_automation_unreliable`: Fields did not accept automation reliably. Fix with stable selectors and field-level verification.
- `no_direct_form`: The source does not expose a reliable application form. Search the company career site first.
- `marketing_consent`: The form requires marketing or third-party consent. Continue only when the local candidate profile explicitly approves this policy.
- `sensitive_field`: The form asks for ID, relatives disclosure, driving/license/car, or another sensitive candidate fact. Reuse verified candidate facts only; unresolved facts remain human gates.
- `legal_declaration`: The form asks for a declaration or terms acceptance. Pause for approval.
- `unverified_system_skill`: The job requires a tool or system not verified in the profile.
- `experience_ambiguity`: The requirement depends on interpretation of experience.
- `closed_job`: The job is no longer accepting applications.

## Site Strategies

- JobMaster: retry with persistent session and verify uploaded CV freshness.
- Jobnet: direct form/POST flow with response evidence.
- LinkedIn: persistent authenticated browser; prefer official company page for external apply.
- AllJobs: treat Radware as a human gate; search official company page first.
- Drushim: persistent login is possible, but marketing consent must be handled by policy.
- DSV/SuccessFactors: persistent browser profile and field-level verification after typing.
- IAI: fill safe fields, stop at ID/relatives/legal/reCAPTCHA gates.
- Nestle: fill safe fields, stop at security checks.
- Jobify: aggregator source; search official company application page first.

## Required Runtime Behavior

1. Open the job with a persistent browser profile for the site.
2. Verify login state before starting the application.
3. Re-read the live job requirements before retrying a failed submission.
4. If the live requirements include a candidate fact that is already verified, such as ID number or relatives-at-company disclosure, continue with that answer. If a required skill is explicitly denied in the profile, do not apply. If a fact is still unknown, such as driving/car, salary number, MS Project, relocation, or heavy travel, downgrade the retry to `policy_required`.
5. Verify every typed field after input, especially duplicated email fields.
6. Save evidence at every blocker: metadata, HTML, and screenshot where available.
7. Pause at CAPTCHA, legal declaration, sensitive facts, or marketing consent.
8. Resume from the existing browser context after the human clears the gate.

## Retry Audit Outcome

The first retry audit found that several historical "manual submission required" rows were not pure system failures. Some jobs were already closed, and others had hard blockers such as SAP/ERP/MRP, reCAPTCHA, marketing consent, or travel requirements. Identity number and relatives-at-company disclosure are now reusable when present in the local candidate profile.

## What This Fixes

This does not bypass security systems. It reduces manual submissions by avoiding one-off sessions, retrying brittle forms correctly, and routing each site through a known adapter. Cases requiring CAPTCHA or legal approval still require a human, but the system should reach that point with the form prepared instead of failing early.
