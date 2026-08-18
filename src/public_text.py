from __future__ import annotations

import re


MOJIBAKE_MARKERS = ("×", "Ã", "Â", "â")
MOJIBAKE_SPAN_RE = re.compile(r"[\u0080-\u00ff][\u0080-\u00ff \t.,:;!?/()\"'\\[\]{}+&|_-]*")


FIXED_REPLACEMENTS = (
    ("Approval required by submission engine:", "נדרש אישור לפני הגשה:"),
    ("Manual submission required by submission engine:", "נדרשת הגשה ידנית:"),
    ("Manual submission required:", "נדרשת הגשה ידנית:"),
    ("Rejected by submission engine:", "נפסל:"),
    ("Adapter gap by submission engine:", "חסר adapter בטוח לאתר:"),
    ("Manual gate:", "חסם ידני:"),
    ("Next:", "השלב הבא:"),
    (
        "The tracker already marks this job as rejected.",
        "המשרה כבר מסומנת כנפסלה במעקב.",
    ),
    (
        "Do not attempt this application unless the row is manually restored after a fresh review.",
        "אין לנסות להגיש אלא אם הרשומה שוחזרה ידנית אחרי בדיקה חדשה.",
    ),
    (
        "The tracker already marks this job as submitted.",
        "המשרה כבר מסומנת כהוגשה במעקב.",
    ),
    (
        "Do not submit again unless the operator explicitly resets the row.",
        "אין להגיש שוב אלא אם הרשומה אופסה במפורש.",
    ),
    (
        "The fit score is below the minimum submission threshold.",
        "ציון ההתאמה נמוך מסף ההגשה המינימלי.",
    ),
    (
        "Keep the job rejected or rescore it after reading a live updated posting.",
        "להשאיר כנפסל או לנקד מחדש רק אחרי קריאת מודעה עדכנית.",
    ),
    (
        "Ask the operator for approval or the missing policy-sensitive answer before attempting submission.",
        "יש לקבל אישור או תשובה חסרה לפני ניסיון הגשה.",
    ),
    (
        "Ask the operator for the missing or policy-sensitive answer before attempting submission.",
        "יש לקבל את התשובה החסרה או הרגישה לפני ניסיון הגשה.",
    ),
    (
        "Ask the operator to approve the distance or work model before attempting submission.",
        "יש לאשר את המרחק או מודל העבודה לפני ניסיון הגשה.",
    ),
    (
        "Do not apply unless the live posting proves the disqualifying requirement is not mandatory.",
        "אין להגיש אלא אם המודעה העדכנית מוכיחה שדרישת הפסילה אינה חובה.",
    ),
    (
        "No submission adapter exists for this site yet.",
        "עדיין אין adapter הגשה מאומת לאתר הזה.",
    ),
    (
        "Inspect the site once, then add an adapter profile and selectors.",
        "יש לבדוק את האתר פעם אחת ולהוסיף adapter/selectors מאומתים.",
    ),
    (
        "Open a persistent browser session, verify login/CV state, fill safe fields, and submit only after response confirmation.",
        "יש לפתוח דפדפן מתמשך, לוודא התחברות וקובץ CV, למלא רק שדות בטוחים, ולהגיש רק לאחר אישור תגובה ברור.",
    ),
    (
        "The requirement depends on how the candidate's experience is interpreted.",
        "הדרישה תלויה בפרשנות הניסיון של המועמדת.",
    ),
    (
        "Create reusable experience mappings, for example whether budget-control work counts as economist experience.",
        "יש למפות מראש אילו רכיבי ניסיון, למשל בקרה תקציבית, נחשבים לניסיון כלכלי.",
    ),
    (
        "Jobnet has a direct SendCv form, but the auto-submit adapter is not yet validated for mandatory questions, terms, email confirmation, and success evidence.",
        "ב-Jobnet יש טופס SendCv ישיר, אבל adapter ההגשה עדיין לא אומת לשאלות חובה, תנאים, אישור מייל והוכחת הצלחה.",
    ),
    (
        "Send as manual handoff or inspect the SendCv form in a persistent browser before adding a safe Jobnet submit adapter.",
        "להעביר להגשה ידנית או לבדוק את טופס SendCv בדפדפן מתמשך לפני הוספת adapter בטוח.",
    ),
    (
        "The site presented CAPTCHA or an anti-automation security layer.",
        "האתר הציג CAPTCHA או שכבת אבטחה נגד אוטומציה.",
    ),
    (
        "Use a persistent browser, fill all safe fields, capture evidence, then pause for a human to pass the challenge.",
        "יש להשתמש בדפדפן מתמשך, למלא שדות בטוחים, לשמור evidence, ולעצור לפתרון אנושי של האתגר.",
    ),
    (
        "The form requires an answer that is not verified in the candidate profile or source evidence.",
        "הטופס דורש תשובה שלא אומתה בפרופיל המועמדת או במקור המשרה.",
    ),
    (
        "The job requires a system/tool skill that has not been verified for the candidate.",
        "המשרה דורשת מערכת או כלי שלא אומתו עבור המועמדת.",
    ),
    (
        "Add candidate facts for each system; if verified, future forms can proceed without stopping.",
        "יש להוסיף עובדות מועמדת לכל מערכת; אם יאומתו, הגשות עתידיות יוכלו להמשיך בלי עצירה.",
    ),
    (
        "The form asks for a sensitive or unverified candidate fact.",
        "הטופס מבקש פרט רגיש או פרט שלא אומת על המועמדת.",
    ),
    (
        "Store the verified fact in the candidate profile, then allow future submissions to reuse it.",
        "יש לשמור את הפרט המאומת בפרופיל המועמדת ואז לאפשר שימוש חוזר בהגשות עתידיות.",
    ),
    (
        "National ID and relatives-at-company answer are available in the local profile.",
        "תעודת הזהות ותשובת קרובי המשפחה בחברה זמינות בפרופיל המקומי.",
    ),
    (
        "National ID and relatives-at-company answer are available in the local profile",
        "תעודת הזהות ותשובת קרובי המשפחה בחברה זמינות בפרופיל המקומי",
    ),
    (
        "Use the verified candidate profile answer.",
        "יש להשתמש בתשובה המאומתת מפרופיל המועמדת.",
    ),
    (
        "Driving license, car, and independent arrival are verified in the candidate profile.",
        "רישיון נהיגה, רכב והגעה עצמאית מאומתים בפרופיל המועמדת.",
    ),
    (
        "The official form asks whether the candidate previously applied, and this answer is not verified in the candidate profile.",
        "הטופס הרשמי שואל האם המועמדת הגישה מועמדות בעבר, והתשובה אינה מאומתת בפרופיל המועמדת.",
    ),
    (
        "The form asks for national ID, but the candidate profile does not include it.",
        "הטופס מבקש תעודת זהות, אך הפרט אינו קיים בפרופיל המועמדת.",
    ),
    (
        "The blocker does not match a known failure pattern.",
        "סיבת העצירה אינה תואמת עדיין תבנית כשל מוכרת.",
    ),
    (
        "Inspect the page and add a new classifier rule if this repeats.",
        "יש לבדוק את הדף ולהוסיף כלל סיווג חדש אם זה חוזר.",
    ),
    (
        "A numeric salary expectation was approved in the candidate profile.",
        "ציפיית שכר מספרית אושרה בפרופיל המועמדת.",
    ),
    (
        "Priority is verified in the candidate profile.",
        "ניסיון ב-Priority מאומת בפרופיל המועמדת.",
    ),
    (
        "Numeric salary expectations are not approved in the candidate profile.",
        "ציפיות שכר מספריות לא אושרו בפרופיל המועמדת.",
    ),
    (
        "The form requires marketing or third-party consent that is not approved in the candidate profile.",
        "הטופס דורש הסכמה לשיווק או לצד שלישי שאינה מאושרת בפרופיל המועמדת.",
    ),
    (
        "human security step required.",
        "נדרש שלב אבטחה אנושי.",
    ),
    (
        "Official fallback checked at",
        "נבדק מסלול רשמי ב-",
    ),
    (
        "Official fallback checked",
        "נבדק מסלול רשמי",
    ),
    (
        "נבדק fallback רשמי at",
        "נבדק מסלול רשמי ב-",
    ),
    (
        "נבדק fallback רשמי",
        "נבדק מסלול רשמי",
    ),
    (
        "Drushim exposed a relevant Rami Levy role, but there is no validated direct-submit adapter.",
        "Drushim הציג משרה רלוונטית של רמי לוי, אך אין עדיין adapter הגשה ישירה מאומת.",
    ),
    (
        "no direct posting/form for procurement clerk at Timorim was found",
        "לא נמצאה משרה ישירה או טופס ישיר לפקיד/ת רכש בתימורים",
    ),
    (
        "only WhatsApp/phone/recruiting email contact",
        "נמצא רק קשר דרך WhatsApp, טלפון או מייל גיוס",
    ),
    (
        "Recommendation: apply manually via Drushim or contact Rami Levy recruiting with the approved CV.",
        "המלצה: להגיש ידנית דרך Drushim או ליצור קשר עם גיוס רמי לוי ולצרף את ה-CV המאושר.",
    ),
    (
        "or contact Rami Levy recruiting with the approved CV.",
        "או ליצור קשר עם גיוס רמי לוי ולצרף את ה-CV המאושר.",
    ),
    (
        "Verify the flagged requirement or policy item before retrying the application.",
        "יש לבדוק את הדרישה או סעיף המדיניות שסומנו לפני ניסיון הגשה חוזר.",
    ),
    (
        "Use the verified candidate profile answers and retry the application flow instead of sending a manual handoff.",
        "יש להשתמש בתשובות המאומתות מפרופיל המועמדת ולנסות את מסלול ההגשה שוב במקום להעביר להגשה ידנית.",
    ),
    (
        "Marketing/third-party consent is approved in the local profile; retry the Drushim application flow.",
        "אישור תוכן שיווקי/צדדים שלישיים קיים בפרופיל המקומי; יש לנסות שוב את מסלול ההגשה ב-Drushim.",
    ),
    (
        "Send a manual handoff or inspect the SendCv form before adding a safe Jobnet adapter.",
        "יש להעביר להגשה ידנית או לבדוק את טופס SendCv לפני הוספת adapter בטוח ל-Jobnet.",
    ),
    (
        "Search for the same role on the official company career page; if no direct form exists, send manual handoff.",
        "יש לחפש את אותה משרה באתר הקריירה הרשמי של החברה; אם אין טופס ישיר, להעביר להגשה ידנית.",
    ),
    (
        "Drushim is approved as a discovery source, but no safe submit adapter exists yet for its application form.",
        "Drushim מאושר כמקור איתור, אבל עדיין אין adapter הגשה בטוח לטופס ההגשה שלו.",
    ),
    (
        "Use Drushim to identify the employer and prefer an official company career form; if no direct form exists, send a manual handoff.",
        "יש להשתמש ב-Drushim לזיהוי המעסיק ולהעדיף טופס קריירה רשמי של החברה; אם אין טופס ישיר, להעביר להגשה ידנית.",
    ),
    (
        "Use Jobify as source discovery, then search and submit through the official company career page when available.",
        "יש להשתמש ב-Jobify כמקור איתור, ואז לחפש ולהגיש דרך אתר הקריירה הרשמי של החברה כשקיים.",
    ),
    (
        "Use the authenticated LinkedIn session to identify Easy Apply or the external company URL; prefer the official company form.",
        "יש להשתמש בסשן LinkedIn מחובר כדי לזהות Easy Apply או קישור חיצוני לחברה; יש להעדיף טופס חברה רשמי.",
    ),
    (
        "Do not retry this Jobify posting unless the live page becomes open again.",
        "אין לנסות שוב את משרת Jobify הזו אלא אם הדף החי נפתח מחדש.",
    ),
    (
        "Open JobMaster with the persistent profile, verify the active CV is the current PDF, fill the tailored message if available, submit, and confirm the success banner.",
        "יש לפתוח את JobMaster עם הפרופיל המתמשך, לוודא שה-CV הפעיל הוא ה-PDF הנוכחי, למלא פנייה מותאמת אם קיימת, להגיש ולאמת הודעת הצלחה.",
    ),
    (
        "JobMaster requires login before this application can continue.",
        "JobMaster דורש התחברות לפני שניתן להמשיך בהגשה.",
    ),
    (
        "Start a persistent JobMaster session or provide JOBMASTER_EMAIL/JOBMASTER_PASSWORD in the runtime environment.",
        "יש לפתוח סשן JobMaster מתמשך או להגדיר פרטי התחברות בסביבת ההרצה המקומית.",
    ),
    (
        "JobMaster requires an email or phone verification code.",
        "JobMaster דורש קוד אימות במייל או בטלפון.",
    ),
    (
        "The JobMaster posting is no longer active.",
        "משרת JobMaster כבר אינה פעילה.",
    ),
    (
        "JobMaster presented a CAPTCHA or security challenge.",
        "JobMaster הציג CAPTCHA או אתגר אבטחה.",
    ),
    (
        "The JobMaster apply button was not found.",
        "כפתור ההגשה ב-JobMaster לא נמצא.",
    ),
    (
        "JobMaster opened the application popup but did not finish loading the application form.",
        "JobMaster פתח את חלון ההגשה אך טופס ההגשה לא נטען עד הסוף.",
    ),
    (
        "The expected current CV was not found in the JobMaster application popup.",
        "ה-CV הנוכחי הצפוי לא נמצא בחלון ההגשה של JobMaster.",
    ),
    (
        "JobMaster reports missing profile fields in the application popup.",
        "JobMaster מדווח שחסרים שדות בפרופיל בתוך חלון ההגשה.",
    ),
    (
        "The JobMaster application form was prepared but not submitted.",
        "טופס ההגשה ב-JobMaster הוכן אך לא נשלח.",
    ),
    (
        "JobMaster confirmed the CV/application was sent successfully.",
        "JobMaster אישר שה-CV/המועמדות נשלחו בהצלחה.",
    ),
    (
        "JobMaster did not confirm a successful submission.",
        "JobMaster לא אישר שההגשה הצליחה.",
    ),
    (
        "The current CV was uploaded into the JobMaster application popup.",
        "ה-CV הנוכחי הועלה לחלון ההגשה של JobMaster.",
    ),
    (
        "The expected current CV is available in the JobMaster application popup.",
        "ה-CV הנוכחי הצפוי זמין בחלון ההגשה של JobMaster.",
    ),
    (
        "JobMaster application reached an unknown state.",
        "ההגשה ב-JobMaster הגיעה למצב לא מזוהה.",
    ),
    (
        "Inspect saved evidence before continuing.",
        "יש לבדוק את ה-evidence שנשמר לפני המשך טיפול.",
    ),
    (
        "Jobify displayed a CAPTCHA/security challenge.",
        "Jobify הציג CAPTCHA או אתגר אבטחה.",
    ),
    (
        "Jobify recognized an existing email address and requires account login before continuing.",
        "Jobify זיהה מייל קיים ודורש התחברות לחשבון לפני המשך.",
    ),
    (
        "Jobify requires email/phone verification before continuing.",
        "Jobify דורש אימות במייל או בטלפון לפני המשך.",
    ),
    (
        "Jobify onboarding reached a salary screen; numeric salary was not approved.",
        "תהליך Jobify הגיע למסך שכר; סכום מספרי לא אושר מראש.",
    ),
    (
        "Jobify requires account login/registration continuation.",
        "Jobify דורש המשך התחברות או הרשמה.",
    ),
    (
        "CV was uploaded and Jobify advanced without a detected human gate.",
        "ה-CV הועלה ו-Jobify התקדם בלי שנמצא חסם אנושי.",
    ),
    (
        "Jobify did not expose a file input.",
        "Jobify לא הציג שדה העלאת קובץ.",
    ),
    (
        "SuccessFactors requires account creation",
        "SuccessFactors דורש יצירת חשבון",
    ),
    (
        "The application path depends on login, account state, or a site session.",
        "מסלול ההגשה תלוי בהתחברות, מצב חשבון או סשן באתר.",
    ),
    (
        "Registration requires third-party marketing consent",
        "ההרשמה דורשת הסכמה לתוכן שיווקי מצד שלישי",
    ),
    (
        "The form is protected by reCAPTCHA",
        "הטופס מוגן באמצעות reCAPTCHA",
    ),
    (
        "The form is protected by reCAPTCHA.",
        "הטופס מוגן באמצעות reCAPTCHA.",
    ),
    (
        "The role requires independent arrival by car",
        "המשרה דורשת הגעה עצמאית ברכב",
    ),
    (
        "LinkedIn login required",
        "נדרשת התחברות ל-LinkedIn",
    ),
    (
        "Do not apply unless the live posting shows an approved target location or a confirmed hybrid model of up to two weekly office visits.",
        "אין להגיש אלא אם המודעה החיה מציגה מיקום יעד מאושר או מודל היברידי מאומת של עד שתי הגעות שבועיות.",
    ),
    ("Ashdod", "אשדוד"),
)


REGEX_REPLACEMENTS = (
    (
        re.compile(r"([A-Za-z0-9][A-Za-z0-9+ #./_-]*) appears to be a required skill, but it is not verified in the candidate profile\.?"),
        r"נדרש ניסיון ב-\1 כחובה, אך הוא לא אומת בפרופיל המועמדת.",
    ),
    (
        re.compile(r"([A-Za-z0-9][A-Za-z0-9+ #./_-]*) appears to be a required skill, and the candidate has confirmed she has no experience with it\.?"),
        r"נדרש ניסיון ב-\1 כחובה, והמועמדת אישרה שאין לה ניסיון בו.",
    ),
    (
        re.compile(r"([A-Za-z0-9][A-Za-z0-9+ #./_-]*) is verified in the candidate profile\.?"),
        r"ניסיון ב-\1 מאומת בפרופיל המועמדת.",
    ),
    (
        re.compile(r"([A-Za-z0-9][A-Za-z0-9+ #./_-]*) is listed as a mandatory degree, but the verified candidate profile has B\.A\. Economics and Management\.?"),
        r"\1 מופיע כתואר חובה, אך בפרופיל המאומת מופיע B.A בכלכלה וניהול.",
    ),
    (
        re.compile(r"official ([A-Za-z0-9+ #./_-]+) form requires CAPTCHA/reCAPTCHA", re.IGNORECASE),
        r"הטופס הרשמי של \1 דורש CAPTCHA/reCAPTCHA",
    ),
    (
        re.compile(r"([A-Za-z0-9+ #./_-]+) application requires CAPTCHA/reCAPTCHA", re.IGNORECASE),
        r"ההגשה דרך \1 דורשת CAPTCHA/reCAPTCHA",
    ),
    (
        re.compile(
            r"Rejected: duplicate of the Timorim economist posting already tracked as manual-required at (.+?)\. Do not submit twice\.?",
            re.IGNORECASE,
        ),
        r"נפסל: כפילות של משרת הכלכלן/ית בתימורים שכבר מתועדת כנדרשת להגשה ידנית בקישור \1. אין להגיש פעמיים.",
    ),
    (
        re.compile(
            r"Rejected: duplicate of the Afcon Beer Sheva procurement job already submitted through JobMaster at (.+?)\. Do not submit again\.?",
            re.IGNORECASE,
        ),
        r"נפסל: כפילות של משרת הרכש של אפקון בבאר שבע שכבר הוגשה דרך JobMaster בקישור \1. אין להגיש שוב.",
    ),
)


def _mojibake_score(text: str) -> int:
    marker_score = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    control_score = sum(2 for ch in text if 0x80 <= ord(ch) <= 0x9F)
    return marker_score + control_score


def _decode_latin1_utf8(value: str) -> str:
    try:
        decoded = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    return decoded if _mojibake_score(decoded) < _mojibake_score(value) else value


def repair_common_mojibake(value: object) -> str:
    text = str(value or "")
    if not text or _mojibake_score(text) == 0:
        return text
    whole = _decode_latin1_utf8(text)
    if whole != text:
        return whole
    return MOJIBAKE_SPAN_RE.sub(lambda match: _decode_latin1_utf8(match.group(0)), text)


def public_hebrew_text(value: object) -> str:
    text = repair_common_mojibake(value)
    if not text:
        return ""
    for source, target in FIXED_REPLACEMENTS:
        text = text.replace(source, target)
    for pattern, replacement in REGEX_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()
