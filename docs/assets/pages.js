const els = {
  candidateName: document.querySelector("#candidateName"),
  generatedAt: document.querySelector("#generatedAt"),
  metrics: document.querySelector("#metrics"),
  searchInput: document.querySelector("#searchInput"),
  scoreFilter: document.querySelector("#scoreFilter"),
  sortBy: document.querySelector("#sortBy"),
  segments: [...document.querySelectorAll(".segment")],
  visibleCount: document.querySelector("#visibleCount"),
  jobList: document.querySelector("#jobList"),
  jobDetails: document.querySelector("#jobDetails"),
  jobModal: document.querySelector("#jobModal"),
  modalClose: document.querySelector("#modalClose"),
  modalContent: document.querySelector("#modalContent"),
  toast: document.querySelector("#toast"),
};

const statusClass = new Map([
  ["הוגש", "status-submitted"],
  ["הוגש ידנית", "status-manual-submitted"],
  ["נדרש אישור", "status-pending"],
  ["נפסל", "status-rejected"],
]);

const MANUAL_STATUS = "הוגש ידנית";
const MANUAL_STORAGE_KEY = "job-searcher-manual-submissions-v1";

const state = {
  data: null,
  selectedKey: null,
  status: "all",
  manualSubmissions: {},
};

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 3500);
}

function loadManualSubmissions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(MANUAL_STORAGE_KEY) || "{}");
    state.manualSubmissions = parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    state.manualSubmissions = {};
  }
}

function saveManualSubmissions() {
  localStorage.setItem(MANUAL_STORAGE_KEY, JSON.stringify(state.manualSubmissions));
}

function timestampNow() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`;
}

function jobView(job) {
  const manual = state.manualSubmissions[job.key];
  if (!manual) {
    return job;
  }
  return {
    ...job,
    original_status: job.status,
    status: MANUAL_STATUS,
    manual_submitted_at: manual.submittedAt,
  };
}

function jobViews() {
  return state.data.jobs.map(jobView);
}

function markManualSubmitted(key) {
  const submittedAt = timestampNow();
  state.manualSubmissions[key] = { submittedAt };
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();
  showToast(`סומן כהוגש ידנית: ${submittedAt}`);
}

function clearManualSubmitted(key) {
  delete state.manualSubmissions[key];
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();
  showToast("סימון ההגשה הידנית בוטל");
}

function refreshAfterManualChange(key) {
  state.selectedKey = key;
  render();
  state.selectedKey = key;
  renderDetails();
}

async function loadState() {
  loadManualSubmissions();
  const response = await fetch("assets/job-data.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("לא נמצא קובץ נתונים לפרסום");
  }
  state.data = await response.json();
  if (!state.selectedKey && state.data.jobs.length > 0) {
    state.selectedKey = state.data.jobs[0].key;
  }
  render();
}

function renderMetrics() {
  const counts = state.data.counts;
  const manualCount = state.data.jobs.filter((job) => state.manualSubmissions[job.key]).length;
  const items = [
    ["נסרקו", counts.scanned],
    ["תועדו", counts.documented],
    ["מתאימות", counts.suitable],
    ["הוגשו", counts.submitted],
    ["הוגשו ידנית", manualCount],
    ["ממתינות", counts.pending],
    ["נפסלו", counts.rejected],
  ];

  els.metrics.innerHTML = items
    .map(
      ([label, value]) =>
        `<article class="metric"><span class="metric-value">${escapeHtml(value)}</span><span class="metric-label">${escapeHtml(label)}</span></article>`
    )
    .join("");
}

function currentJobs() {
  const query = els.searchInput.value.trim().toLowerCase();
  const minScore = Number(els.scoreFilter.value || 0);
  const selectedStatus = state.status;

  const filtered = jobViews().filter((job) => {
    const matchesStatus = selectedStatus === "all" || job.status === selectedStatus;
    const matchesScore = Number(job.score || 0) >= minScore;
    const haystack = [
      job.company,
      job.title,
      job.location,
      job.link,
      job.requirements,
      job.fit,
      job.stop_reason,
      job.manual_submitted_at,
    ]
      .join(" ")
      .toLowerCase();
    return matchesStatus && matchesScore && haystack.includes(query);
  });

  const sortBy = els.sortBy.value;
  filtered.sort((a, b) => {
    if (sortBy === "date") {
      return String(b.manual_submitted_at || b.date || "").localeCompare(String(a.manual_submitted_at || a.date || ""));
    }
    if (sortBy === "company") {
      return String(a.company || "").localeCompare(String(b.company || ""), "he");
    }
    return Number(b.score || 0) - Number(a.score || 0);
  });

  return filtered;
}

function renderJobs() {
  const jobs = currentJobs();
  els.visibleCount.textContent = `${jobs.length} מוצגות`;
  if (!jobs.some((job) => job.key === state.selectedKey)) {
    state.selectedKey = jobs[0]?.key || null;
  }

  if (jobs.length === 0) {
    els.jobList.innerHTML = `<div class="empty-state">אין משרות להצגה</div>`;
    return;
  }

  els.jobList.innerHTML = jobs
    .map((job) => {
      const selected = job.key === state.selectedKey ? " selected" : "";
      const pillClass = statusClass.get(job.status) || "";
      return `
        <article class="job-row${selected}" data-key="${escapeHtml(job.key)}" role="button" tabindex="0">
          <span class="score-badge">${escapeHtml(job.score)}</span>
          <span class="job-main">
            <span class="job-title">${escapeHtml(job.title)}</span>
            <span class="job-company">${escapeHtml(job.company)}</span>
            <span class="job-location">${escapeHtml(job.location || "ללא מיקום")}</span>
          </span>
          <span class="row-side">
            <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
            <a class="row-link" href="${escapeHtml(job.link)}" target="_blank" rel="noreferrer">פתח משרה</a>
          </span>
        </article>
      `;
    })
    .join("");
}

function textBlock(label, value) {
  const clean = String(value || "").trim();
  const body = clean ? `<p class="detail-text">${escapeHtml(clean)}</p>` : `<p class="detail-text empty">אין נתון</p>`;
  return `<section class="detail-section"><h3>${escapeHtml(label)}</h3>${body}</section>`;
}

function linkBlock(label, value) {
  const clean = String(value || "").trim();
  if (!clean) {
    return textBlock(label, "");
  }
  return `
    <section class="detail-section">
      <h3>${escapeHtml(label)}</h3>
      <a class="source-url" href="${escapeHtml(clean)}" target="_blank" rel="noreferrer">${escapeHtml(clean)}</a>
    </section>
  `;
}

function manualSubmittedBlock(timestamp) {
  if (!timestamp) {
    return "";
  }
  return `
    <section class="detail-section">
      <h3>הגשה ידנית</h3>
      <p class="detail-text">הוגש ידנית בתאריך ושעה: <span class="timestamp" dir="ltr">${escapeHtml(timestamp)}</span></p>
    </section>
  `;
}

function jobDetailsHtml(job, titleId = "") {
  const pillClass = statusClass.get(job.status) || "";
  const headingId = titleId ? ` id="${escapeHtml(titleId)}"` : "";
  const manualTimestamp = job.manual_submitted_at || "";
  const manualFact = manualTimestamp
    ? `<span class="fact manual-fact">הוגש ידנית: <span class="timestamp" dir="ltr">${escapeHtml(manualTimestamp)}</span></span>`
    : "";
  const manualAction = job.manual_submitted_at
    ? `<button type="button" class="manual-button secondary" data-manual-action="clear" data-key="${escapeHtml(job.key)}">בטל סימון ידני</button>`
    : `<button type="button" class="manual-button" data-manual-action="mark" data-key="${escapeHtml(job.key)}">סמן כהוגש ידנית</button>`;
  return `
    <div class="details-inner">
      <header class="details-head">
        <div class="details-title-line">
          <div>
            <h2${headingId} class="details-title">${escapeHtml(job.title)}</h2>
            <p class="details-company">${escapeHtml(job.company)}</p>
          </div>
          <span class="score-badge">${escapeHtml(job.score)}</span>
        </div>
        <div class="quick-facts">
          <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
          <span class="fact">${escapeHtml(job.location || "ללא מיקום")}</span>
          <span class="fact">${escapeHtml(job.date || "ללא תאריך")}</span>
          ${manualFact}
          <span class="fact">${escapeHtml(job.cv || "ללא CV")}</span>
        </div>
        <div class="actions">
          <a class="link-button" href="${escapeHtml(job.link)}" target="_blank" rel="noreferrer">פתח משרה מקורית</a>
          ${manualAction}
        </div>
      </header>

      ${manualSubmittedBlock(manualTimestamp)}
      ${textBlock("דרישות מרכזיות", job.requirements)}
      ${textBlock("סיבות התאמה", job.fit)}
      ${textBlock("סיבת עצירה או פסילה", job.stop_reason)}
      ${linkBlock("קישור ישיר", job.link)}
    </div>
  `;
}

function selectedJob() {
  return jobViews().find((item) => item.key === state.selectedKey);
}

function renderDetails() {
  const job = selectedJob();
  if (!job) {
    els.jobDetails.innerHTML = `<div class="empty-state">אין משרה נבחרת</div>`;
    return;
  }

  els.jobDetails.innerHTML = jobDetailsHtml(job);
}

function openJobModal(job) {
  state.selectedKey = job.key;
  render();
  els.modalContent.innerHTML = jobDetailsHtml(job, "modalTitle");
  els.jobModal.hidden = false;
  document.body.classList.add("modal-open");
  els.modalClose.focus();
}

function closeJobModal() {
  els.jobModal.hidden = true;
  document.body.classList.remove("modal-open");
}

function refreshOpenModal() {
  if (els.jobModal.hidden) {
    return;
  }
  const job = selectedJob();
  if (job) {
    els.modalContent.innerHTML = jobDetailsHtml(job, "modalTitle");
  }
}

function renderChrome() {
  els.candidateName.textContent = `${state.data.candidate.full_name} · מעקב מועמדויות`;
  els.generatedAt.textContent = `עודכן: ${state.data.generated_at}`;
}

function render() {
  if (!state.data) {
    return;
  }
  renderChrome();
  renderMetrics();
  renderJobs();
  renderDetails();
}

els.jobList.addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    return;
  }
  const row = event.target.closest(".job-row");
  if (!row) {
    return;
  }
  state.selectedKey = row.dataset.key;
  const job = selectedJob();
  if (job) {
    openJobModal(job);
  }
});

els.jobList.addEventListener("keydown", (event) => {
  if (!["Enter", " "].includes(event.key)) {
    return;
  }
  const row = event.target.closest(".job-row");
  if (!row) {
    return;
  }
  event.preventDefault();
  state.selectedKey = row.dataset.key;
  const job = selectedJob();
  if (job) {
    openJobModal(job);
  }
});

els.modalClose.addEventListener("click", closeJobModal);
els.jobModal.addEventListener("click", (event) => {
  if (event.target === els.jobModal) {
    closeJobModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.jobModal.hidden) {
    closeJobModal();
  }
});

function handleManualAction(event) {
  const button = event.target.closest("[data-manual-action]");
  if (!button) {
    return;
  }
  const key = button.dataset.key;
  if (!key) {
    return;
  }
  if (button.dataset.manualAction === "mark") {
    markManualSubmitted(key);
  } else {
    clearManualSubmitted(key);
  }
}

els.jobDetails.addEventListener("click", handleManualAction);
els.modalContent.addEventListener("click", handleManualAction);

els.searchInput.addEventListener("input", render);
els.scoreFilter.addEventListener("change", render);
els.sortBy.addEventListener("change", render);
els.segments.forEach((button) => {
  button.addEventListener("click", () => {
    state.status = button.dataset.status;
    els.segments.forEach((item) => item.classList.toggle("active", item === button));
    render();
  });
});

loadState().catch((error) => {
  showToast(error.message);
});
