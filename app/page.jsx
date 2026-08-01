export default function DashboardPage() {
  return (
    <>
      <div className="app-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">Job Searcher</p>
            <h1 id="candidateName">מעקב מועמדויות</h1>
          </div>
          <div className="topbar-meta">
            <span id="generatedAt"></span>
            <span id="syncStatus" className="state-pill local">
              סימון מקומי
            </span>
          </div>
        </header>

        <section id="metrics" className="metrics" aria-label="מדדי פעילות"></section>

        <section className="filters" aria-label="סינון משרות">
          <label className="search-box" htmlFor="searchInput">
            <span>חיפוש</span>
            <input id="searchInput" type="search" autoComplete="off" placeholder="חברה, משרה, מיקום או קישור" />
          </label>

          <div className="segmented" role="group" aria-label="סטטוס">
            <button type="button" className="segment active" data-status="all">
              הכל
            </button>
            <button type="button" className="segment" data-status="הוגש">
              הוגש
            </button>
            <button type="button" className="segment" data-status="הוגש ידנית">
              הוגש ידנית
            </button>
            <button type="button" className="segment" data-status="נדרש אישור">
              נדרש אישור
            </button>
            <button type="button" className="segment" data-status="נפסל">
              נפסל
            </button>
          </div>

          <label className="select-field" htmlFor="scoreFilter">
            <span>ציון</span>
            <select id="scoreFilter" defaultValue="0">
              <option value="0">כל הציונים</option>
              <option value="70">70+</option>
              <option value="80">80+</option>
              <option value="90">90+</option>
            </select>
          </label>

          <label className="select-field" htmlFor="sortBy">
            <span>מיון</span>
            <select id="sortBy" defaultValue="score">
              <option value="score">התאמה</option>
              <option value="date">תאריך</option>
              <option value="company">חברה</option>
            </select>
          </label>
        </section>

        <main className="workspace">
          <section className="jobs-panel" aria-label="רשימת משרות">
            <div className="panel-title">
              <h2>משרות</h2>
              <span id="visibleCount"></span>
            </div>
            <div id="jobList" className="job-list" role="list"></div>
          </section>

          <aside id="jobDetails" className="details-panel" aria-label="פרטי משרה"></aside>
        </main>
      </div>

      <div id="jobModal" className="modal-backdrop" hidden>
        <section className="job-modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
          <button type="button" id="modalClose" className="modal-close" aria-label="סגור">
            ×
          </button>
          <div id="modalContent"></div>
        </section>
      </div>

      <div id="toast" className="toast" role="status" aria-live="polite" hidden></div>
      <link rel="stylesheet" href="/assets/pages.css" />
      <script type="module" src="/assets/pages.js"></script>
    </>
  );
}
