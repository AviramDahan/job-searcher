# Job Searcher

Job Searcher is a small automation toolkit for managing job-search scans, application tracking, and Telegram notifications.

The current version is a cleaned Git-ready extraction from a Codex workspace. It intentionally excludes private runtime artifacts such as CV files, cookies, session exports, raw HTML responses, and real Telegram credentials.

## What This Repository Contains

- `src/job_records.py` - shared CSV schema, job-key generation, duplicate detection, and basic summary counts.
- `src/rebuild_summary.py` - rebuilds `outputs/job_search_summary.md` from `outputs/job_applications.csv`.
- `src/send_job_status_alerts.py` - sends structured submitted/manual job alerts to Telegram from a JSON file.
- `src/send_manual_alerts_from_csv.py` - sends Telegram alerts for jobs in CSV status `נדרש אישור`, while keeping a local send log to avoid repeat alerts.
- `src/submission_engine.py` - central submission planner/runner that routes jobs through site adapters and returns one consistent decision model.
- `src/dashboard_app.py` - runs a local browser dashboard for reviewing, filtering, updating, and re-alerting tracked jobs.
- `src/dashboard_static/` - dashboard HTML, CSS, and JavaScript.
- `templates/job_applications.template.csv` - required CSV columns.
- `templates/alerts.example.json` - example Telegram alert payload.
- `docs/security.md` - what must not be committed.

## What Was Not Copied

The original Codex workspace contained many useful runtime artifacts, but most are not suitable for Git:

- CV PDF/DOCX files.
- Job-site cookies and sessions.
- Telegram tokens and real chat IDs.
- Raw LinkedIn/JobMaster/Jobnet/CBC scrape JSON and HTML responses.
- One-off application scripts with hardcoded candidate phone/email.
- Downloaded vendor JavaScript bundles from job websites.

Those files are useful operationally, but they are not clean reusable source code.

## Directory Layout

```text
Job Searcher/
  src/
    dashboard_app.py
    dashboard_static/
      index.html
      dashboard.css
      dashboard.js
    submission_engine.py
    jobmaster_apply.py
    job_records.py
    rebuild_summary.py
    send_job_status_alerts.py
    send_manual_alerts_from_csv.py
  templates/
    alerts.example.json
    job_applications.template.csv
    job_search_summary.template.md
  docs/
    security.md
  outputs/
    .gitkeep
  data/
    .gitkeep
  .env.example
  .gitignore
  README.md
  requirements.txt
```

## Setup

Use Python 3.10 or newer.

```powershell
cd "C:\Users\User\Desktop\Github Repos\Job Searcher"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The included core scripts use the Python standard library. `requirements.txt` keeps optional dependencies available for future scanner/submission adapters.

## Environment Variables

Create a local `.env` or set variables in PowerShell. Do not commit `.env`.

```powershell
$env:TELEGRAM_BOT_TOKEN="123456:REPLACE_ME"
$env:TELEGRAM_CHAT_ID="-1001234567890"
$env:DEFAULT_TIMEZONE="Asia/Jerusalem"
```

Optional local paths:

```powershell
$env:CV_PATH="C:\Path\To\cv.pdf"
$env:JOB_APPLICATIONS_CSV="outputs\job_applications.csv"
$env:JOB_SEARCH_SUMMARY="outputs\job_search_summary.md"
$env:CANDIDATE_PROFILE_PATH="data\private\candidate_profile.local.json"
```

JobMaster submissions require a local browser profile and credentials in the same shell that runs the command:

```powershell
$env:JOBMASTER_EMAIL="candidate@example.com"
$env:JOBMASTER_PASSWORD="REPLACE_ME"
$env:JOBMASTER_HEADLESS="true"
$env:CV_PATH="C:\Path\To\current_cv.pdf"
```

Candidate facts that are safe to reuse during applications should live in the ignored local profile file:

```json
{
  "full_name": "Candidate Name",
  "national_id": "",
  "has_relatives_at_company": false,
  "has_driving_license": null,
  "has_car": null,
  "can_arrive_independently": null,
  "marketing_consent_approved": null,
  "approved_salary_expectation": null,
  "system_skills": {
    "SAP": false,
    "ERP": false,
    "MRP": false,
    "Priority": null,
    "Power BI": null,
    "MS Project": null,
    "Nibit": null,
    "חשבשבת": null,
    "Canva": null,
    "ChatGPT": null
  }
}
```

Use `false` only for facts the candidate explicitly denied, `true` only for verified skills/facts, and `null` when the answer is still unknown.

## CSV Format

The tracker expects this exact CSV schema:

```text
תאריך,חברה,שם המשרה,מיקום,קישור,ציון התאמה,דרישות מרכזיות,סיבות להתאמה,סטטוס,סיבת פסילה או עצירה,נוסח הפנייה שנשלח,שם קובץ קורות החיים שצורף
```

Allowed statuses:

- `הוגש` - application was submitted.
- `נדרש אישור` - application should stop until a human confirms missing information or completes a blocked step.
- `נפסל` - job was rejected by filtering rules.

## Common Commands

Validate and summarize the CSV:

```powershell
python .\src\job_records.py .\outputs\job_applications.csv
```

Rebuild the Markdown summary:

```powershell
python .\src\rebuild_summary.py --csv .\outputs\job_applications.csv --summary .\outputs\job_search_summary.md --scanned-count 960 --telegram-alerts 0
```

Send Telegram alerts from a JSON payload:

```powershell
python .\src\send_job_status_alerts.py .\templates\alerts.example.json
```

Mark existing manual jobs as already alerted without sending Telegram messages:

```powershell
python .\src\send_manual_alerts_from_csv.py --csv .\outputs\job_applications.csv --log .\outputs\manual_alert_log.json --mark-existing
```

Send Telegram alerts for new `נדרש אישור` rows:

```powershell
python .\src\send_manual_alerts_from_csv.py --csv .\outputs\job_applications.csv --log .\outputs\manual_alert_log.json
```

Run the local dashboard:

```powershell
python -m src.dashboard_app --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## GitHub Pages Dashboard

The repository includes a GitHub Pages dashboard under `docs/`. It is a static snapshot for sharing progress and does not include backend actions, Telegram sending, browser automation, credentials, cookies, or CV files. Manual submitted markers in the Pages dashboard are stored only in that browser's `localStorage`; they do not update the CSV tracker or send Telegram.

Refresh the Pages data from the private tracker:

```powershell
python -m src.export_pages_dashboard --csv .\outputs\job_applications.csv --summary .\outputs\job_search_summary.md --out .\docs\assets\job-data.json --candidate-name "Candidate Name"
```

Preview the static dashboard locally:

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory docs
```

Then open:

```text
http://127.0.0.1:8766
```

Important: `docs/assets/job-data.json` contains job-application history. Keep the GitHub repository private unless the candidate explicitly approves a public read-only snapshot.

Dashboard capabilities:

- Review the current tracker counts and Telegram/manual-alert totals.
- Filter jobs by status, score, free text, and sort order.
- Open the original job URL from the selected row.
- Run a submission-engine check for the selected job.
- Save follow-up notes back into `outputs/job_applications.csv`.
- Mark a job as manually submitted or rejected, then rebuild `outputs/job_search_summary.md`.
- Resend a submitted/manual alert to Telegram for a selected job.

Telegram resend buttons require these environment variables in the same shell that starts the dashboard:

```powershell
$env:TELEGRAM_BOT_TOKEN="123456:REPLACE_ME"
$env:TELEGRAM_CHAT_ID="-1001234567890"
python -m src.dashboard_app --host 127.0.0.1 --port 8765
```

Dashboard Telegram resend history is stored in ignored local runtime data:

```text
data/runtime/dashboard_alert_log.json
```

## Submission Engine

The submission engine is the new central layer for turning scanned jobs into consistent next actions.

It returns one of these decisions:

- `ready_for_auto` - safe to attempt through the site's persistent browser/session adapter.
- `ready_for_company_fallback` - use the source as discovery, then prefer the official company form.
- `human_gate` - the system can fill safe fields but must pause for CAPTCHA/security or similar.
- `policy_required` - missing candidate fact, salary policy, legal declaration, work model, or interpretation question.
- `do_not_apply` - hard blocker such as denied SAP/ERP/MRP requirement, closed job, low score, or senior/non-target role.
- `already_submitted` - tracker already records a successful submission.
- `not_supported` - no adapter exists yet for that site.

Build a fresh engine plan from the tracker:

```powershell
python -m src.submission_engine --csv .\outputs\job_applications.csv --json .\outputs\submission_engine_plan.json --md .\outputs\submission_engine_plan.md --min-score 70
```

Save evidence metadata for the next runnable item without opening a browser:

```powershell
python -m src.submission_engine --run-next evidence_only
```

Open the next runnable item in a persistent browser session:

```powershell
python -m src.submission_engine --run-next open_browser
```

Prepare the next runnable JobMaster application without sending it:

```powershell
python -m src.submission_engine --run-next prepare
```

Submit the next runnable JobMaster application, then update the tracker, rebuild the summary, and send Telegram when configured:

```powershell
python -m src.submission_engine --run-next submit --notify
```

The JobMaster adapter logs in through a persistent browser profile, waits for the application popup to finish loading, verifies/selects the current CV, fills a human cover note, appends an approved salary note when salary expectations are required, and records screenshot/HTML evidence for every terminal state. It will not alter the original CV file.

Current first-pass adapters:

- JobMaster: persistent session, verify current CV, prepare/submit modes, tracker update, Telegram notification, and success evidence.
- Jobnet: persistent/direct form path.
- LinkedIn: authenticated session, prefer official company fallback when external apply appears.
- Jobify: source discovery and company fallback.
- AllJobs/Drushim/IAI/Nestle/DSV: explicit route decisions for CAPTCHA, consent, system-skill, or policy blockers.

Engine outputs are ignored by Git because they are operational data:

```text
outputs/submission_engine_plan.json
outputs/submission_engine_plan.md
```

## Operating Rules

The automation logic follows these rules:

- Submit only jobs with fit score `70+` and no blocker.
- Stop and document jobs that require CAPTCHA, email/SMS verification, account creation, missing mandatory answers, numeric salary expectations, unknown legal declarations, relocation, heavy travel, or uncertain mandatory requirements.
- Do not claim skills, tools, education, certifications, licenses, or work history that are not in the candidate profile/CV.
- Prefer company career pages over intermediary job boards when a direct application path exists.
- Avoid duplicate applications by generating stable job keys from platform IDs and URLs.
- Send Telegram on every successful submission and every job that requires manual completion.

## Current Automation Schedule

The Codex heartbeat automation is configured outside this repository, under the local Codex settings directory. The current intended schedule is:

- Sunday through Thursday.
- `08:00`, `12:00`, `16:00`, `20:00`.
- Timezone: `Asia/Jerusalem`.

The local automation config path used in the original workspace was:

```text
C:\Users\User\.codex\automations\automation\automation.toml
```

## Preparing For GitHub

Before the first commit, run:

```powershell
rg -n "TELEGRAM|BOT_TOKEN|CHAT_ID|password|סיסמה|cookie|session|052|Koren|gmail|[0-9]{8,}:" .
```

Expected result: no real token, password, cookie, phone, email, or CV path should appear in tracked files.

Then initialize Git:

```powershell
git init
git status
git add .gitignore .env.example README.md requirements.txt src templates docs
git commit -m "Initial clean job search automation toolkit"
```

Real `outputs/` data is ignored by default. Commit it only to a private repository and only if you intentionally want application history in Git.

## Submission Reliability Layer

The repository now includes a reliability layer for the cases that previously became "manual submission required".

New modules:

- `src/submission_failures.py` classifies why an application did not complete.
- `src/candidate_profile.py` loads local verified candidate facts and separates resolved fields from real blockers.
- `src/site_adapters.py` maps known job sites to the right recovery strategy.
- `src/browser_session.py` defines persistent browser profiles and evidence capture.
- `src/open_submission_session.py` opens a job in a persistent browser profile and saves HTML/screenshot evidence.
- `src/manual_submission_report.py` generates a report that separates true site automation failures from missing candidate facts.
- `src/retry_failed_submissions.py` builds and operates a retry queue for system-related failures only, including optional Telegram notifications for retry attempts.
- `src/send_retry_queue_alerts.py` sends Telegram alerts for retry-queue items that still require approval or manual completion.

Generate a manual-submission failure analysis:

```powershell
python .\src\manual_submission_report.py --csv .\outputs\job_applications.csv --out .\outputs\manual_submission_failure_analysis.md
```

Generate a retry queue for system-related failures:

```powershell
python .\src\retry_failed_submissions.py --csv .\outputs\job_applications.csv --json .\outputs\retry_queue.json --md .\outputs\retry_queue.md
```

The retry queue checks both the original stop reason and the recorded job requirements. Verified fields such as ID number or relatives-at-company answers can be reused. Required skills that the candidate explicitly does not have, such as SAP/ERP/MRP for the current profile, are removed from retry instead of being sent as manual submissions. Unknown or unresolved facts, such as driving/car availability, MS Project, salary numbers, or legal/privacy gates, remain human gates.

Open the next retryable item in a persistent browser session and save evidence:

```powershell
python .\src\retry_failed_submissions.py --csv .\outputs\job_applications.csv --open-next
```

Open the next retryable item and send a Telegram update:

```powershell
python .\src\retry_failed_submissions.py --csv .\outputs\job_applications.csv --open-next --notify
```

Create retry evidence without launching the browser:

```powershell
python .\src\retry_failed_submissions.py --csv .\outputs\job_applications.csv --open-next --evidence-only
```

Preview Telegram messages for retry items that still need manual action:

```powershell
python .\src\send_retry_queue_alerts.py --queue .\outputs\retry_queue.json --dry-run
```

Send Telegram messages for retry items that still need manual action:

```powershell
python .\src\send_retry_queue_alerts.py --queue .\outputs\retry_queue.json
```

Run the reliability tests:

```powershell
python -m unittest discover -s tests
```

Open a blocked application in a persistent browser session and keep it open for human completion:

```powershell
python .\src\open_submission_session.py --url "https://jobs.iai.co.il/job/76048804/" --job-key "iai:76048804" --manual-gate --keep-open
```

The first Playwright setup on a new machine requires:

```powershell
playwright install chromium
```

The intended behavior is not to bypass CAPTCHA or legal gates. The system should fill safe fields, save evidence, pause for human action, and resume from the same persistent browser session.

Retry alerts are de-duplicated in `data/runtime/retry_telegram_log.json`, which is ignored by Git.
