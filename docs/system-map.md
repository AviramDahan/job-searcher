# מיפוי מערכת Job Searcher

מסמך זה מתאר את מצב המערכת בפועל: קבצי מקור, זרימת אוטומציה, מקורות חיפוש, מנוע החלטות, הגשות, Telegram, דשבורד וסנכרון ענן.

## מקור אמת

- תיקיית פרויקט: `C:\Users\User\Desktop\Github Repos\Job Searcher`
- CSV מעקב פרטי: `outputs/job_applications.csv`
- סיכום פרטי: `outputs/job_search_summary.md`
- נתוני דשבורד ציבוריים: `docs/assets/job-data.json`
- קונפיג דשבורד ציבורי: `docs/assets/dashboard-config.json`
- פרופיל מועמדת פרטי: `data/private/candidate_profile.local.json`
- קובץ CV מאושר לשימוש: `data/private/koren_dahan_cv.pdf`
- קבצים מקוריים ב-Downloads אינם לעריכה.

## זרימת ריצה

1. `src.sync_location_preferences`
   מושך העדפות מיקום מהדשבורד החי ושומר ל-`outputs/location_preferences.json`.

2. `src.discovery_scanner`
   סורק מקורות עבודה ציבוריים, קורא דפי פירוט כשאפשר, מנקד התאמה, מוסיף משרות חדשות ומרענן משרות קיימות.

3. `src.submission_engine`
   קורא את ה-CSV ומחליט עבור כל משרה מתאימה האם אפשר להגיש, צריך fallback, צריך אישור, צריך הגשה ידנית, או לפסול.

4. `src.submission_plan_sync`
   מסנכרן את החלטות מנוע ההגשה חזרה ל-CSV, בלי לדרוס שורות שכבר הוגשו או שורות עם חסם ידני מוגן.

5. `src.retry_failed_submissions`
   בונה תור טיפול חוזר רק למקרים שבהם הכשל הוא טכני או ניתן לשיפור, ומפריד בין retry, fallback, human gate ו-policy gate.

6. `src.conversion_audit`
   מנתח למה סריקות לא הופכות להגשות ומייצר המלצות לשיפור.

7. `src.categorize_manual_required`
   מעביר שורות עם חסמי אתר אמיתיים לסטטוס `נדרשת הגשה ידנית`.

8. `src.export_pages_dashboard`
   מייצא snapshot נקי לדשבורד GitHub Pages.

## מקורות חיפוש פעילים

הסריקה החיה המובנית כרגע נמצאת ב-`src.discovery_scanner.default_sources`.

מקורות פעילים בפועל:

- JobMaster: מילות חיפוש `רכש`, `קניין`, `כלכלן`, `תקציב`, `בקרה תקציבית`, `PMO`, `sourcing`, `procurement`, `buyer`.
- Drushim: מילות חיפוש `רכש`, `קניין`, `כלכלן`, `תקציב`, `בקרה`, `PMO`, `sourcing`, `procurement`.
- Jobnet: קטגוריות URL קבועות בתחומי כספים/כלכלה/רכש/לוגיסטיקה לפי מזהי האתר.
- BGU Careers: מקור רשמי לאוניברסיטת בן-גוריון.

מקורות שיש להם routing/adapters אך אינם נסרקים באופן רחב כברירת מחדל:

- LinkedIn.
- AllJobs.
- Jobify.
- IAI Careers.
- Nestle Careers.
- DSV SuccessFactors.
- אתרי חברה רשמיים נוספים כמו Elbit, ICL, Intel, Vishay, ADAMA, SodaStream, Coca-Cola/CBC.

משמעות: חלק גדול מהסריקות עדיין מגיע מאגרגטורים. כדי להעלות יחס הגשות, השיפור הבא צריך להיות הרחבת discovery ישירה באתרי חברות רשמיים ולא עוד סריקה חוזרת של אותם אגרגטורים.

## מדיניות מיקום

הקוד המרכזי: `src/location_policy.py`.

מיקום בסיס: שדרות.

מיקומים מאושרים כברירת מחדל:

- שדרות.
- נתיבות.
- אשקלון.
- קריית גת.
- באר שבע.
- אשדוד.
- אופקים.
- קריית מלאכי.
- באר טוביה.
- תימורים.
- להבים.

מיקומים שהמשתמש יכול לאשר מהדשבורד:

- ערים ויישובים מתוך רשימה ידנית.
- אזורים: דרום, שפלה, מרכז, צפון.
- יישובים מתוך מאגר CBS ציבורי.
- רדיוס קילומטרים סביב שדרות.

כל עיר מחוץ למדיניות הנוכחית נפסלת, אלא אם המשרה היא מרחוק מלא או שיש מודל היברידי ברור של עד שתי הגעות שבועיות.

## החלטות מנוע ההגשה

הקוד המרכזי: `src/submission_engine.py`.

החלטות אפשריות:

- `ready_for_auto`: אפשר לנסות דרך adapter בטוח.
- `ready_for_company_fallback`: להשתמש באתר כמקור, למצוא טופס חברה רשמי ולנסות שם.
- `human_gate`: חסם אתר או אבטחה, למשל CAPTCHA או קוד אימות.
- `policy_required`: חסרה עובדה על המועמדת או נדרש אישור מדיניות.
- `do_not_apply`: פסילה קשיחה.
- `already_submitted`: כבר הוגש.
- `not_supported`: אין adapter בטוח לאתר.

הגשה אוטומטית מלאה קיימת בפועל בעיקר ל-JobMaster דרך `src/jobmaster_apply.py`.

## Adapters ואתרי יעד

הקוד המרכזי: `src/site_adapters.py`.

- JobMaster: נתמך עם session מתמשך, בדיקת CV, מילוי טקסט, שליחה ואימות הצלחה.
- Jobnet: מזוהה כמקור עם טופס SendCv, אך adapter שליחה עדיין לא מאומת עד הסוף.
- Drushim: טוב לאיתור, אך הגשה ישירה אינה בטוחה עדיין. עדיף fallback לאתר חברה.
- LinkedIn: דורש session מחובר; עדיף לזהות Easy Apply או קישור חברה רשמי.
- AllJobs: לרוב חסמי Radware/CAPTCHA; עדיף fallback לאתר חברה.
- IAI/Nestle: טפסים רשמיים אך יכולים לכלול CAPTCHA, שאלות משפטיות או פרטים רגישים.
- DSV/SuccessFactors: דורש session יציב ואימות שדות.
- Jobify: מקור/אגרגטור; עדיף fallback לאתר חברה.

## Telegram

קבצים מרכזיים:

- `src/send_job_status_alerts.py`
- `src/send_manual_alerts_from_csv.py`
- `src/send_retry_queue_alerts.py`

כל הודעה צריכה לצאת בעברית תקינה. שכבת `src/public_text.py` מנקה:

- טקסט mojibake היסטורי.
- רצפי `??`.
- משפטי מערכת באנגלית שמגיעים ממנוע ההגשה או מתורי retry.

סודות Telegram חייבים להישאר רק ב-`.env`, בסביבת הרצה מקומית, או ב-secrets של Cloudflare/Hosting. אין לשמור אותם בקבצים ציבוריים.

## דשבורד

דשבורד מקומי:

- `src/dashboard_app.py`
- `src/dashboard_static/index.html`
- `src/dashboard_static/dashboard.css`
- `src/dashboard_static/dashboard.js`

דשבורד GitHub Pages:

- `docs/index.html`
- `docs/assets/pages.js`
- `docs/assets/pages.css`
- `docs/assets/job-data.json`
- `docs/assets/dashboard-config.json`

יכולות קיימות:

- צפייה במשרות לפי סטטוס וציון.
- פתיחת משרה בפופאפ.
- קישור למשרה המקורית.
- סימון הוגש ידנית.
- סימון נפסל ידנית.
- בחירת מיקומים, אזורים ורדיוס.
- מפת ישראל עם נקודת שדרות, אזורים, רדיוס וסימון יישובים.
- סנכרון פעולות ידניות לענן דרך Worker.

## סנכרון ענן

המקור הפעיל:

- `https://job-searcher-live-api.aviramdahans.workers.dev/sync`

קוד Worker:

- `cloudflare-worker/src/index.js`
- `cloudflare-worker/wrangler.jsonc`

ה-Worker שומר:

- סימוני הוגש ידנית.
- סימוני נפסל ידנית.
- העדפות מיקום.
- רדיוס חיפוש.
- dedupe לאירועים.

`JSONBlob` הוגדר כמורשת בלבד ואינו מקור אמת עמיד.

## מצב אחרון שנמדד

בסבב ידני אחרון:

- נסרקו 442 כרטיסים.
- נותחו 346 משרות.
- נוספו 8 משרות חדשות.
- 1 משרה חדשה נכנסה לסטטוס `נדרש אישור`.
- 7 משרות חדשות נפסלו.
- היו 3 משרות runnable מסוג `ready_for_company_fallback`.
- לא הייתה משרת JobMaster במצב submit ישיר.

## צווארי בקבוק מרכזיים

- רוב המקורות הפעילים הם אגרגטורים, ולכן הרבה משרות מגיעות בלי טופס חברה רשמי.
- Drushim יוצר הרבה התאמות גבוהות, אבל אין adapter שליחה ישירה בטוח.
- Jobnet מייצר התאמות, אבל SendCv עדיין לא מאומת לשליחה אוטומטית מלאה.
- LinkedIn/AllJobs/IAI/Nestle דורשים יותר עבודה עם browser/fallback עקב login, CAPTCHA או שאלות טופס.
- מדיניות המיקום מצמצמת בצדק הרבה משרות רחוקות, ולכן כמות ההגשות תרד אם המקורות לא מתמקדים בדרום.
- משרות רבות נעצרות על דרישות מערכת לא מאומתות כמו Power BI או MS Project, או על פרשנות ניסיון.

## שיפורים מומלצים לפי עדיפות

1. להוסיף discovery רשמי לאתרי חברות בדרום: Elbit, IAI, ICL, Intel Kiryat Gat, Vishay, ADAMA, SodaStream, Coca-Cola/CBC, Afcon, Assuta Ashdod.
2. לבנות adapter מאומת ל-Jobnet SendCv עם evidence מלא: שדות חובה, תנאים, אימות מייל והוכחת הצלחה.
3. לבנות כלי fallback רשמי: מקבל חברה+תפקיד, מחפש אתר קריירה רשמי, מאמת טופס ישיר ומעדכן CSV.
4. להוסיף dashboard view ל-`ready_for_company_fallback`, כדי לטפל קודם במשרות עם ציון גבוה ולא רק בסטטוסים.
5. להוסיף רשימת מיומנויות מאומתות/לא מאומתות שניתן לערוך בדשבורד פרטי, כדי לצמצם `policy_required`.
6. להוסיף מדד conversion שבועי לפי מקור, כדי לדעת איפה להשקיע adapters.
7. להוסיף בדיקת health מחמירה לכל ריצה: sync, job-data, קידוד, מספר runnable, וסטטוס GitHub Pages.

