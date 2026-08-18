from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.discovery_scanner import (
    DiscoveredJob,
    Source,
    bgu_apply_url,
    clean_text,
    discover,
    extract_drushim_body_detail,
    extract_drushim_filters,
    merge_detail,
    parse_bgu,
    parse_drushim,
    parse_jobmaster,
    parse_jobnet,
    score_job,
)
from src.job_records import COMPANY, DATE, FIT, LINK, LOCATION, PENDING, REJECTED, REQUIREMENTS, SCORE, STATUS, STOP_REASON, TITLE, job_key, load_rows, write_rows


JOBMASTER_HTML = """
<article class="CardStyle JobItem font14" id="misra9830657">
  <div class="JobItemRight">
    <a class="CardHeader View_Job_Details" href="/jobs/checknum.asp?key=9830657">לחברה מובילה דרוש/ה קניין/ית רכש</a>
    <div><span class="Gray">פורסם לפני 4 שעות</span> ע"י <a class="CompanyNameLink"><span>אופק לעובד</span></a></div>
    <li class="jobLocation"><span>אשדוד, קריית גת</span></li>
    <div class="jobShortDescription">עבודה מול ספקים, הצעות מחיר, הזמנות, Excel ואנגלית.</div>
  </div>
</article>
"""


JOBNET_HTML = """
<div class="inerbox orange">
  <a href="/jobs?positionid=13300382"><h2 itemprop="title">איש/ת רכש</h2></a>
  <p itemprop="hiringOrganization"><a>חברה דסקרטית</a></p>
  <p class="boxDateCls" itemprop="datePosted">03/08/2026</p>
  <div itemprop="description">תיאור תפקיד: רכש, ספקים, משא ומתן והזמנות.</div>
  <div itemprop="skills">דרישות: תואר ראשון, Excel ואנגלית.</div>
  <span class="reg">- אשדוד, קריית גת</span>
</div>
"""


DRUSHIM_HTML = """
<div data-cy="job-item0" class="job-item">
  <h3><span class="job-url">קניין/ית רכש לחברת אלקטרוניקה</span></h3>
  <a href="/job/37979255/1959bdf9/">פתח משרה</a>
  <span class="bidi">רימון שירותי השמה</span>
  <div class="job-details-sub">קריית גת | 1-2 שנים | משרה מלאה | לפני 18 דקות</div>
  <div class="job-intro">איתור ספקים, ניהול משא ומתן והוצאת הזמנות.</div>
</div>
"""

BGU_HTML = """
<table>
  <tr>
    <td>2026 - 85</td>
    <td><a onclick="window.open('https://bguhr.my.salesforce.com/sfc/p/D0000000pKPc/a/Py000002BNjJ/file')">קניינ/ית התקשרויות וחשבונות-מדור התקשרויות וחשבונות-מחלקת רכש והספקה-אגף הכספים</a></td>
    <td><a onclick="if(typeof jsfcljs == 'function'){jsfcljs(document.getElementById('j_id0:formid'),'x,y,selectedItem,701Py00000XHZg0IAH','_blank');}return false">להגשת מועמדות לחצ/י כאן</a></td>
  </tr>
</table>
"""


DRUSHIM_DETAIL_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "קניין/ית רכש לחברת אלקטרוניקה",
        "description": "איתור יצרנים וספקים בתחומי המכאניקה והאלקטרוניקה.<br/>ביצוע מו&quot;מ ותמחור מול יצרנים וספקים.<br/>ביצוע רכש ומעקב הזמנות ואספקות.",
        "datePosted": "2026-08-03",
        "hiringOrganization": {"name": "רימון שירותי השמה"},
        "jobLocation": {"address": {"addressLocality": "קריית גת"}}
      }
    </script>
  </head>
  <body>
    <footer>דרושים מכירות דרושים שירות לקוחות דרושים הנהלת חשבונות</footer>
  </body>
</html>
"""


JOBMASTER_DETAIL_HTML = """
<article class="CardStyle articleJob JobItem font14">
  <div class="jobHead__text__titleAndCompName"><div class="CardHeader">כלכלן/ית מתחיל/ה</div></div>
  <a class="CompanyNameLink">CBC ISREAL</a>
  <li id="jobLocationData" class="jobLocation">באר שבע</li>
  <div id="jobDescriptionContent">
    ניתוח תהליכי דיווח ובקרה עסקית שוטפת, בניית תקציב שנתי וליווי כלכלי של פרויקטים.
  </div>
  <div id="jobRequirementsContent">
    תואר ראשון בכלכלה, שליטה מלאה ב-Office וב-Excel, יכולת אנליטית גבוהה.
  </div>
</article>
<footer>דרושים חשב שכר דרושים QA דרושים שירות לקוחות</footer>
"""


class DiscoveryScannerTests(unittest.TestCase):
    def test_clean_text_removes_broken_question_runs(self) -> None:
        self.assertEqual(clean_text("Buyer ???  Excel"), "Buyer Excel")

    def test_parse_jobmaster_card(self) -> None:
        jobs = parse_jobmaster(JOBMASTER_HTML, "https://www.jobmaster.co.il/jobs/?q=test")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "לחברה מובילה דרוש/ה קניין/ית רכש")
        self.assertEqual(jobs[0].company, "אופק לעובד")
        self.assertEqual(jobs[0].link, "https://www.jobmaster.co.il/jobs/checknum.asp?key=9830657")

    def test_parse_jobnet_card(self) -> None:
        jobs = parse_jobnet(JOBNET_HTML, "https://www.jobnet.co.il/jobs")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].link, "https://www.jobnet.co.il/jobs?positionid=13300382")
        self.assertIn("אשדוד", jobs[0].location)

    def test_parse_drushim_card(self) -> None:
        jobs = parse_drushim(DRUSHIM_HTML, "https://www.drushim.co.il/jobs/search/%D7%A8%D7%9B%D7%A9/")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "רימון שירותי השמה")
        self.assertEqual(jobs[0].location, "קריית גת")

    def test_parse_bgu_official_jobs(self) -> None:
        jobs = parse_bgu(BGU_HTML, "https://bguhr.my.salesforce-sites.com/Gius?mode=jobs")

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "BGU Careers")
        self.assertEqual(jobs[0].company, "אוניברסיטת בן-גוריון בנגב")
        self.assertEqual(jobs[0].location, "באר שבע")
        self.assertIn("קניינ/ית התקשרויות וחשבונות", jobs[0].title)
        self.assertEqual(
            jobs[0].link,
            "https://www.tfaforms.com/4851745?tfa_4776808320092=701Py00000XHZg0&tfa_4776808320093=001D000001095iN&tfa_4776808320094=%D7%93%D7%A8%D7%95%D7%A9%D7%99%D7%9D",
        )
        self.assertEqual(job_key({LINK: jobs[0].link}), "bgu:701Py00000XHZg0")

    def test_bgu_apply_url_trims_salesforce_checksum(self) -> None:
        self.assertIn("tfa_4776808320092=701Py00000XHZg0", bgu_apply_url("701Py00000XHZg0IAH"))

    def test_drushim_detail_uses_jobposting_jsonld_not_footer_text(self) -> None:
        merged = merge_detail(
            DiscoveredJob(
                source="Drushim",
                title="קניין/ית רכש לחברת אלקטרוניקה",
                company="רימון שירותי השמה",
                location="קריית גת",
                link="https://www.drushim.co.il/job/37979255/1959bdf9/",
                description="",
                requirements="",
            ),
            DRUSHIM_DETAIL_HTML,
        )
        scored = score_job(merged)

        self.assertIn("ספקים", merged.description)
        self.assertNotIn("שירות לקוחות", merged.description)
        self.assertEqual(scored.status, PENDING)

    def test_jobmaster_detail_uses_description_nodes_not_footer_text(self) -> None:
        merged = merge_detail(
            DiscoveredJob(
                source="JobMaster",
                title="כלכלן/ית מתחיל/ה",
                company="CBC ISREAL",
                location="באר שבע",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=9614515",
                description="",
                requirements="",
            ),
            JOBMASTER_DETAIL_HTML,
        )
        scored = score_job(merged)

        self.assertIn("בניית תקציב", merged.description)
        self.assertNotIn("שירות לקוחות", merged.description)
        self.assertEqual(scored.status, PENDING)

    def test_extract_drushim_screening_filters(self) -> None:
        html = r'''
        <script>
        window.__NUXT__={JobContent:{Filters:["\u05d4\u05d0\u05dd \u05d1\u05d9\u05e6\u05e2\u05ea \u05d1\u05e7\u05e8\u05d4 \u05ea\u05e7\u05e6\u05d9\u05d1\u05d9\u05ea \u05dc\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8\u05d9\u05dd?"],Salary:null}};
        </script>
        '''

        self.assertIn("שאלות סינון", extract_drushim_filters(html))
        self.assertIn("בקרה תקציבית", extract_drushim_filters(html))

    def test_extract_drushim_body_detail_stops_before_footer(self) -> None:
        text = (
            "ניווט תיאור משרה עבודה מול ספקים. דרישות התפקיד ניסיון במערכת ERP עם MRP. "
            "לפרופיל החברה ומשרות נוספות > קטגוריה דרושים שירות לקוחות"
        )

        detail = extract_drushim_body_detail(text)

        self.assertIn("ERP", detail)
        self.assertNotIn("שירות לקוחות", detail)

    def test_required_erp_rejects_otherwise_matching_job(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="קניין/ית רכש",
                company="חברה",
                location="אשדוד",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=1",
                description="עבודה מול ספקים והזמנות.",
                requirements="ERP חובה, Excel ואנגלית.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertLess(scored.score, 70)

    def test_accounting_title_is_rejected_even_when_financial_terms_match(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Jobnet",
                title="חשב/ת",
                company="חברה",
                location="באר שבע",
                link="https://www.jobnet.co.il/jobs?positionid=2",
                description="תפקיד כספים הכולל תקציב, Excel ודוחות.",
                requirements="תואר בכלכלה וניסיון פיננסי.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("הנהלת חשבונות", scored.stop_reason)

    def test_warehouse_core_title_is_rejected(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Jobnet",
                title="איש/ת רכש וניהול מחסן",
                company="חברה",
                location="אשדוד",
                link="https://www.jobnet.co.il/jobs?positionid=3",
                description="רכש, ספקים והזמנות.",
                requirements="Excel ואנגלית.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("מחסן", scored.stop_reason)

    def test_hr_recruiting_role_is_rejected_even_when_degree_terms_match(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="רכז/ת גיוס טכנולוגי/ת",
                company="חברת הדרכה",
                location="תל אביב",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=7",
                description="עבודה מול מועמדים, לינקדאין ודוחות גיוס.",
                requirements="תואר רלוונטי וניסיון קודם יתרון.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("גיוס/HR", scored.stop_reason)

    def test_student_position_requires_approval_before_submission(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="איש/ת בקרה תקציבית - משרת סטודנט",
                company="חברה",
                location="באר שבע",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=8",
                description="בקרה תקציבית, דוחות והזמנות.",
                requirements="סטודנט/ית לתואר פיננסי, Excel ברמה גבוהה.",
            )
        )

        self.assertEqual(scored.status, PENDING)
        self.assertIn("סטודנט/ית", scored.stop_reason)

    def test_technical_program_manager_is_rejected(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="Program Manager - Tactical Laser",
                company="חברה ביטחונית",
                location="רחובות",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=9",
                description="Leading complex projects, technical documents and business development and marketing activities.",
                requirements="Bachelor degree in engineering or Exact Sciences. Willingness to travel abroad.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("טכני/הנדסי", scored.stop_reason)

    def test_mandatory_engineer_or_practical_engineer_is_rejected(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="בקר/ית פרויקטים",
                company="חברה קבלנית",
                location="תל אביב",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=11",
                description="בקרה תקציבית, עבודה מול ממשקים ו-Priority.",
                requirements="מהנדס/ת או הנדסאי/ת – חובה. ניסיון בבנייה יתרון.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("מהנדס/ת או הנדסאי/ת", scored.stop_reason)

    def test_head_of_budget_domain_is_rejected_as_senior_management(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="אחראי/ת תחום תקציבים והתקשרויות",
                company="חברה",
                location="ראשון לציון",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=10",
                description="ניהול תקציבים גדולים, מכרזים, חוזים והתקשרויות.",
                requirements="תואר ראשון רלוונטי ושליטה מלאה ב-Excel.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("ניהול בכיר", scored.stop_reason)

    def test_procurement_job_is_not_rejected_for_warehouse_mention_only(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Drushim",
                title="קניין/ית רכש לחברת אלקטרוניקה",
                company="חברה",
                location="קריית גת",
                link="https://www.drushim.co.il/job/1/",
                description="עבודה מול ספקים, הצעות מחיר, הזמנות וממשק מול מחסן.",
                requirements="תואר ראשון, Excel ואנגלית.",
            )
        )

        self.assertEqual(scored.status, PENDING)
        self.assertGreaterEqual(scored.score, 70)

    def test_far_location_is_rejected_even_when_professionally_relevant(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="קניין/ית רכש",
                company="חברה",
                location="חיפה",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=4",
                description="עבודה מול ספקים, הצעות מחיר, הזמנות ומשא ומתן.",
                requirements="תואר ראשון, Excel ואנגלית.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("המיקום", scored.stop_reason)

    def test_hybrid_without_office_frequency_requires_approval(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="כלכלן/ית",
                company="חברה",
                location="תל אביב - היברידי",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=5",
                description="בקרה תקציבית, דוחות, Excel וניתוח נתונים.",
                requirements="תואר בכלכלה ואנגלית.",
            )
        )

        self.assertEqual(scored.status, PENDING)
        self.assertIn("נדרש אישור", scored.stop_reason)

    def test_procurement_department_manager_is_rejected(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Drushim",
                title="מנהל.ת מחלקת רכש",
                company="חברה",
                location="יבנה",
                link="https://www.drushim.co.il/job/1/",
                description="ניהול מחלקת רכש, ספקים, משא ומתן והזמנות.",
                requirements="ניסיון ברכש וניהול עובדים.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("מנהל/ת רכש", scored.stop_reason)

    def test_head_of_economics_domain_is_rejected_as_senior_management(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="JobMaster",
                title="ראש תחום כלכלה ותקציבים",
                company="חברה",
                location="באר שבע",
                link="https://www.jobmaster.co.il/jobs/checknum.asp?key=6",
                description="ניהול תחום כלכלה ותקציבים, עבודה מול הנהלה ודוחות.",
                requirements="תואר בכלכלה וניסיון של 3 שנים.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertLess(scored.score, 70)

    def test_inventory_and_procurement_manager_is_rejected_as_senior_management(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Drushim",
                title="מנהל/ת אפסנאות ורכש מקומי",
                company="חברה",
                location="באר שבע",
                link="https://www.drushim.co.il/job/2/",
                description="ניהול אפסנאות ורכש, ספקים והזמנות.",
                requirements="ניסיון ברכש וניהול.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertLess(scored.score, 70)

    def test_hybrid_up_to_two_days_is_in_scope(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="LinkedIn",
                title="Financial Analyst",
                company="Company",
                location="Tel Aviv hybrid",
                link="https://www.linkedin.com/jobs/view/1",
                description="Budget control, Excel, reports and financial analysis. Up to two office days per week.",
                requirements="BA in economics and high English.",
            )
        )

        self.assertEqual(scored.status, PENDING)
        self.assertNotIn("נדרש אישור", scored.stop_reason)

    def test_far_secondary_location_is_rejected_without_approval_queue(self) -> None:
        scored = score_job(
            DiscoveredJob(
                source="Drushim",
                title="קניין/ית רכש",
                company="חברה",
                location="רחובות",
                link="https://www.drushim.co.il/job/3/",
                description="רכש, ספקים, משא ומתן והזמנות.",
                requirements="תואר ראשון, Excel ואנגלית. היברידי עד פעמיים בשבוע.",
            )
        )

        self.assertEqual(scored.status, REJECTED)
        self.assertIn("רחוק משדרות", scored.stop_reason)

    def test_dashboard_approved_secondary_location_can_be_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preferences_path = Path(tmp) / "location_preferences.json"
            preferences_path.write_text(
                json.dumps(
                    {
                        "location_preferences": {
                            "approved_locations": [
                                {"key": "rehovot", "label": "רחובות", "terms": ["רחובות", "rehovot"], "approved": True}
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"JOB_SEARCH_LOCATION_PREFERENCES": str(preferences_path)}, clear=False):
                scored = score_job(
                    DiscoveredJob(
                        source="Drushim",
                        title="קניין/ית רכש",
                        company="חברה",
                        location="רחובות",
                        link="https://www.drushim.co.il/job/4/",
                        description="רכש, ספקים, משא ומתן והזמנות.",
                        requirements="תואר ראשון, Excel ואנגלית.",
                    )
                )

        self.assertEqual(scored.status, PENDING)
        self.assertIn("אושר בדשבורד", scored.fit)

    def test_discover_appends_new_rows_without_overwriting_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "jobs.csv"
            summary_path = root / "summary.md"
            csv_path.write_text(
                "\ufeffתאריך,חברה,שם המשרה,מיקום,קישור,ציון התאמה,דרישות מרכזיות,סיבות להתאמה,סטטוס,סיבת פסילה או עצירה,נוסח הפנייה שנשלח,שם קובץ קורות החיים שצורף\n",
                encoding="utf-8",
            )
            summary_path.write_text("- מספר המשרות שנסרקו: 0\n", encoding="utf-8")

            with patch("src.discovery_scanner.default_sources", return_value=[Source("JobMaster", "https://example.test", "jobmaster")]):
                with patch("src.discovery_scanner.scan_sources", return_value=(parse_jobmaster(JOBMASTER_HTML, "https://www.jobmaster.co.il"), 1, {})):
                    result = discover(csv_path, summary_path, root / "report.json", root / "report.md")

            rows = load_rows(csv_path)
            self.assertEqual(result.new_rows, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][STATUS], PENDING)
            self.assertIn("9830657", rows[0][LINK])

    def test_discover_rescores_scanner_managed_existing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "jobs.csv"
            summary_path = root / "summary.md"
            csv_path.write_text(
                "\ufeffתאריך,חברה,שם המשרה,מיקום,קישור,ציון התאמה,דרישות מרכזיות,סיבות להתאמה,סטטוס,סיבת פסילה או עצירה,נוסח הפנייה שנשלח,שם קובץ קורות החיים שצורף\n"
                "2026-08-03,חברה,חשב/ת,באר שבע,https://www.jobnet.co.il/jobs?positionid=2,75,תואר בכלכלה,תקציב,נדרש אישור,נמצא בסריקה חדשה; נדרש מעבר מנוע ההגשה לפני שליחה.,,\n",
                encoding="utf-8",
            )
            summary_path.write_text("- מספר המשרות שנסרקו: 0\n", encoding="utf-8")
            job = DiscoveredJob(
                source="Jobnet",
                title="חשב/ת",
                company="חברה",
                location="באר שבע",
                link="https://www.jobnet.co.il/jobs?positionid=2",
                description="תפקיד כספים הכולל תקציב, Excel ודוחות.",
                requirements="תואר בכלכלה וניסיון פיננסי.",
            )

            with patch("src.discovery_scanner.default_sources", return_value=[Source("Jobnet", "https://example.test", "jobnet")]):
                with patch("src.discovery_scanner.scan_sources", return_value=([job], 1, {})):
                    result = discover(csv_path, summary_path, root / "report.json", root / "report.md", rescore_existing=True)

            rows = load_rows(csv_path)
            self.assertEqual(result.rescored_existing, 1)
            self.assertEqual(rows[0][STATUS], REJECTED)
            self.assertLess(int(rows[0][SCORE]), 70)
            self.assertIn("הנהלת חשבונות", rows[0][STOP_REASON])

    def test_discover_preserves_reviewed_official_site_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "jobs.csv"
            summary_path = root / "summary.md"
            reviewed_reason = (
                "נדרש אישור לפני הגשה: באתר הרשמי מופיעה דרישת חובה לניסיון של 3-4 שנים; "
                "טופס ההגשה דורש הסכמה למדיניות פרטיות."
            )
            write_rows(
                csv_path,
                [
                    {
                        DATE: "2026-08-03",
                        COMPANY: "חברה",
                        TITLE: "כלכלן/ית",
                        LOCATION: "באר שבע",
                        LINK: "https://www.drushim.co.il/job/37979217/ce5efdcc/",
                        SCORE: "74",
                        REQUIREMENTS: "תואר בכלכלה",
                        FIT: "תקציב",
                        STATUS: PENDING,
                        STOP_REASON: reviewed_reason,
                    }
                ],
            )
            summary_path.write_text("- מספר המשרות שנסרקו: 0\n", encoding="utf-8")
            job = DiscoveredJob(
                source="Drushim",
                title="כלכלן/ית",
                company="חברה",
                location="באר שבע",
                link="https://www.drushim.co.il/job/37979217/ce5efdcc/",
                description="תקציב, Excel ודוחות.",
                requirements="תואר בכלכלה.",
            )

            with patch("src.discovery_scanner.default_sources", return_value=[Source("Drushim", "https://example.test", "drushim")]):
                with patch("src.discovery_scanner.scan_sources", return_value=([job], 1, {})):
                    result = discover(csv_path, summary_path, root / "report.json", root / "report.md", rescore_existing=True)

            rows = load_rows(csv_path)
            self.assertEqual(result.skipped_existing, 1)
            self.assertEqual(rows[0][STOP_REASON], reviewed_reason)

    def test_discover_keeps_existing_pending_approval_when_new_scan_is_generic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "jobs.csv"
            summary_path = root / "summary.md"
            approval_reason = "נדרש אישור לפני הגשה: יש דרישת ניסיון סביב 3 שנים, לכן נדרש אישור/בדיקה לפני הגשה."
            write_rows(
                csv_path,
                [
                    {
                        DATE: "2026-08-03",
                        COMPANY: "חברה",
                        TITLE: "בקר/ית תקציב",
                        LOCATION: "אשדוד",
                        LINK: "https://www.drushim.co.il/job/37735694/66ab8947/",
                        SCORE: "100",
                        REQUIREMENTS: "תואר בכלכלה",
                        FIT: "תקציב",
                        STATUS: PENDING,
                        STOP_REASON: approval_reason,
                    }
                ],
            )
            summary_path.write_text("- מספר המשרות שנסרקו: 0\n", encoding="utf-8")
            job = DiscoveredJob(
                source="Drushim",
                title="בקר/ית תקציב",
                company="חברה",
                location="אשדוד",
                link="https://www.drushim.co.il/job/37735694/66ab8947/",
                description="בקרה תקציבית, Excel ודוחות.",
                requirements="תואר בכלכלה.",
            )

            with patch("src.discovery_scanner.default_sources", return_value=[Source("Drushim", "https://example.test", "drushim")]):
                with patch("src.discovery_scanner.scan_sources", return_value=([job], 1, {})):
                    result = discover(csv_path, summary_path, root / "report.json", root / "report.md", rescore_existing=True)

            rows = load_rows(csv_path)
            self.assertEqual(result.rescored_existing, 1)
            self.assertEqual(rows[0][STATUS], PENDING)
            self.assertEqual(rows[0][STOP_REASON], approval_reason)


if __name__ == "__main__":
    unittest.main()
