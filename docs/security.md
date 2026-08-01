# Security Notes

This project automates job-search tracking and notification workflows. It can easily touch sensitive data, so keep the repository clean by default.

Do not commit:

- CV files or identity documents.
- Candidate profile files that contain ID numbers, phone numbers, email addresses, family-at-company answers, or other private facts.
- Telegram bot tokens or chat IDs.
- Job-site passwords, cookies, session files, or browser exports.
- Raw HTML responses from application forms.
- Filled application logs that include personal contact details.
- Telegram credentials inside `docs/assets/dashboard-config.json` or any public frontend file. Store them only in Apps Script properties or local environment variables.

Recommended workflow:

1. Store secrets in `.env` or in the shell environment.
2. Keep real outputs in `outputs/`, which is ignored by Git.
3. Keep private files under `data/private/`, which is ignored by Git.
4. Commit only reusable code, templates, and documentation.
5. Rotate any token that was ever pasted into a chat, commit, screenshot, or public issue.
6. Treat a no-PIN Apps Script web app URL as public-write. It is acceptable for the current MVP only if the Sheet is reviewed and can be repaired from the append-only history.
