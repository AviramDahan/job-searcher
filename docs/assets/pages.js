const els = {
  candidateName: document.querySelector("#candidateName"),
  generatedAt: document.querySelector("#generatedAt"),
  syncStatus: document.querySelector("#syncStatus"),
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
const MANUAL_REJECTED_STATUS = "נפסל";
const MANUAL_REJECTION_REASON = "נפסל בבחירה ידנית";
const MANUAL_STORAGE_KEY = "job-searcher-manual-submissions-v1";
const MANUAL_REJECTIONS_STORAGE_KEY = "job-searcher-manual-rejections-v1";
const SYNC_CONFIG_PATH = "assets/dashboard-config.json";
const SYNC_TIMEOUT_MS = 12000;

const state = {
  data: null,
  selectedKey: null,
  status: "all",
  manualSubmissions: {},
  manualRejections: {},
  sync: {
    config: {},
    enabled: false,
    loaded: false,
    saving: false,
    lastError: "",
    lastSyncedAt: "",
  },
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

function normalizeManualEntry(value = {}) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const submittedAt = String(value.submittedAt || value.submitted_at || value.manual_submitted_at || "").trim();
  if (!submittedAt) {
    return null;
  }

  return {
    submittedAt,
    updatedAt: String(value.updatedAt || value.updated_at || "").trim(),
    note: String(value.note || "").trim(),
    source: String(value.source || "local").trim(),
  };
}

function normalizeManualRejectionEntry(value = {}) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const rejectedAt = String(value.rejectedAt || value.rejected_at || value.manual_rejected_at || "").trim();
  if (!rejectedAt) {
    return null;
  }

  return {
    rejectedAt,
    updatedAt: String(value.updatedAt || value.updated_at || "").trim(),
    note: String(value.note || "").trim(),
    source: String(value.source || "local").trim(),
  };
}

function normalizeManualSubmissions(value) {
  const normalized = {};
  if (!value || typeof value !== "object") {
    return normalized;
  }

  Object.entries(value).forEach(([key, entry]) => {
    const normalizedEntry = normalizeManualEntry(entry);
    if (key && normalizedEntry) {
      normalized[key] = normalizedEntry;
    }
  });
  return normalized;
}

function normalizeManualRejections(value) {
  const normalized = {};
  if (!value || typeof value !== "object") {
    return normalized;
  }

  Object.entries(value).forEach(([key, entry]) => {
    const normalizedEntry = normalizeManualRejectionEntry(entry);
    if (key && normalizedEntry) {
      normalized[key] = normalizedEntry;
    }
  });
  return normalized;
}

function loadManualSubmissions() {
  try {
    const parsed = JSON.parse(localStorage.getItem(MANUAL_STORAGE_KEY) || "{}");
    state.manualSubmissions = normalizeManualSubmissions(parsed);
  } catch {
    state.manualSubmissions = {};
  }

  try {
    const parsed = JSON.parse(localStorage.getItem(MANUAL_REJECTIONS_STORAGE_KEY) || "{}");
    state.manualRejections = normalizeManualRejections(parsed);
  } catch {
    state.manualRejections = {};
  }
}

function saveManualSubmissions() {
  localStorage.setItem(MANUAL_STORAGE_KEY, JSON.stringify(state.manualSubmissions));
  localStorage.setItem(MANUAL_REJECTIONS_STORAGE_KEY, JSON.stringify(state.manualRejections));
}

function timestampNow() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`;
}

function syncEndpoint() {
  const endpoint = state.sync.config.updatesEndpoint || state.sync.config.endpoint || "";
  return String(endpoint).trim();
}

function isPlaceholderEndpoint(endpoint) {
  return !endpoint || endpoint.includes("REPLACE_ME") || endpoint.includes("YOUR_SCRIPT_URL");
}

function syncTransport() {
  return String(state.sync.config.transport || "jsonp").trim().toLowerCase();
}

async function loadSyncConfig() {
  try {
    const response = await fetch(SYNC_CONFIG_PATH, { cache: "no-store" });
    if (!response.ok) {
      state.sync.config = {};
      state.sync.enabled = false;
      return;
    }

    const config = await response.json();
    state.sync.config = config && typeof config === "object" ? config : {};
    state.sync.enabled = !isPlaceholderEndpoint(syncEndpoint());
  } catch {
    state.sync.config = {};
    state.sync.enabled = false;
  }
}

function jsonpRequest(endpoint, params = {}) {
  return new Promise((resolve, reject) => {
    const callbackName = `jobSearcherSync_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const requestUrl = new URL(endpoint, window.location.href);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        requestUrl.searchParams.set(key, String(value));
      }
    });
    requestUrl.searchParams.set("callback", callbackName);
    requestUrl.searchParams.set("_ts", String(Date.now()));

    const script = document.createElement("script");
    let settled = false;

    const cleanup = () => {
      window.clearTimeout(timer);
      script.remove();
      delete window[callbackName];
    };

    const timer = window.setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(new Error("sync_timeout"));
    }, SYNC_TIMEOUT_MS);

    window[callbackName] = (payload) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(payload);
    };

    script.onerror = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(new Error("sync_network_error"));
    };

    script.src = requestUrl.toString();
    document.head.append(script);
  });
}

async function corsRequest(endpoint, params = {}, method = "GET") {
  const requestUrl = new URL(endpoint, window.location.href);
  const requestInit = {
    method,
    headers: {},
  };

  if (method === "GET") {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        requestUrl.searchParams.set(key, String(value));
      }
    });
  } else {
    requestInit.headers["Content-Type"] = "application/json; charset=utf-8";
    requestInit.body = JSON.stringify(params);
  }

  const response = await fetch(requestUrl.toString(), requestInit);
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload) {
    throw new Error(payload?.error || `sync_http_${response.status}`);
  }
  return payload;
}

function syncRequest(params = {}, method = "GET") {
  const endpoint = syncEndpoint();
  if (syncTransport() === "jsonblob") {
    return jsonBlobRequest(endpoint, params);
  }
  if (syncTransport() === "cors") {
    return corsRequest(endpoint, params, method);
  }
  return jsonpRequest(endpoint, params);
}

async function jsonBlobRequest(endpoint, params = {}) {
  const response = await fetch(endpoint, {
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });
  const currentState = await response.json().catch(() => null);
  if (!response.ok || !currentState) {
    throw new Error(`sync_http_${response.status}`);
  }

  if ((params.action || "listUpdates") === "listUpdates") {
    return {
      ok: true,
      generated_at: currentState.generated_at || "",
      manual_submissions: currentState.manual_submissions || {},
      manual_rejections: currentState.manual_rejections || {},
      events: currentState.events || [],
    };
  }

  const nextState = {
    ok: true,
    generated_at: new Date().toISOString(),
    manual_submissions: currentState.manual_submissions || {},
    manual_rejections: currentState.manual_rejections || {},
    events: Array.isArray(currentState.events) ? currentState.events : [],
  };
  const eventId = String(params.event_id || `${params.action}:${params.job_key}:${timestampNow()}`);
  const duplicate = nextState.events.some((event) => event && event.event_id === eventId);

  if (!duplicate && params.action === "markManualSubmitted") {
    nextState.manual_submissions[params.job_key] = {
      submittedAt: String(params.manual_submitted_at || timestampNow()),
      updatedAt: timestampNow(),
      note: String(params.note || ""),
      source: "remote",
    };
    delete nextState.manual_rejections[params.job_key];
  }

  if (!duplicate && params.action === "clearManualSubmitted") {
    delete nextState.manual_submissions[params.job_key];
  }

  if (!duplicate && params.action === "markManualRejected") {
    nextState.manual_rejections[params.job_key] = {
      rejectedAt: String(params.manual_rejected_at || timestampNow()),
      updatedAt: timestampNow(),
      note: String(params.note || MANUAL_REJECTION_REASON),
      source: "remote",
    };
    delete nextState.manual_submissions[params.job_key];
  }

  if (!duplicate && params.action === "clearManualRejected") {
    delete nextState.manual_rejections[params.job_key];
  }

  if (!duplicate) {
    nextState.events.push({
      created_at: timestampNow(),
      event_id: eventId,
      action: String(params.action || ""),
      job_key: String(params.job_key || ""),
      company: String(params.company || ""),
      title: String(params.title || ""),
      location: String(params.location || ""),
      link: String(params.link || ""),
      score: String(params.score || ""),
    });
  }

  const putResponse = await fetch(endpoint, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      Accept: "application/json",
    },
    body: JSON.stringify(nextState),
  });
  if (!putResponse.ok) {
    throw new Error(`sync_http_${putResponse.status}`);
  }

  return {
    ok: true,
    duplicate,
    generated_at: nextState.generated_at,
    manual_submissions: nextState.manual_submissions,
    manual_rejections: nextState.manual_rejections,
    telegram: { sent: false, reason: "jsonblob_transport_no_server_secret" },
  };
}

function mergeRemoteManualState(remoteSubmissions, remoteRejections) {
  const remoteSubmitted = normalizeManualSubmissions(remoteSubmissions);
  const localSubmittedOnly = {};

  Object.entries(state.manualSubmissions).forEach(([key, entry]) => {
    if (!remoteSubmitted[key] && entry.source !== "remote") {
      localSubmittedOnly[key] = entry;
    }
  });

  const remoteRejected = normalizeManualRejections(remoteRejections);
  const localRejectedOnly = {};

  Object.entries(state.manualRejections).forEach(([key, entry]) => {
    if (!remoteRejected[key] && entry.source !== "remote") {
      localRejectedOnly[key] = entry;
    }
  });

  state.manualSubmissions = { ...remoteSubmitted, ...localSubmittedOnly };
  state.manualRejections = { ...remoteRejected, ...localRejectedOnly };
  saveManualSubmissions();
}

async function loadRemoteManualSubmissions() {
  if (!state.sync.enabled) {
    return;
  }

  try {
    state.sync.lastError = "";
    const payload = await syncRequest({ action: "listUpdates" });
    if (!payload || payload.ok === false) {
      throw new Error(payload?.error || "sync_error");
    }
    mergeRemoteManualState(payload.manual_submissions || {}, payload.manual_rejections || {});
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    showToast("הסנכרון המרכזי לא זמין כרגע; ממשיך עם סימון מקומי");
  }
}

function selectedRawJob(key) {
  return state.data?.jobs.find((job) => job.key === key) || null;
}

function jobView(job) {
  const rejection = state.manualRejections[job.key];
  if (rejection) {
    const rejectedAt = rejection.rejectedAt;
    const note = rejection.note || MANUAL_REJECTION_REASON;
    return {
      ...job,
      original_status: job.status,
      status: MANUAL_REJECTED_STATUS,
      stop_reason: `${MANUAL_REJECTION_REASON} בתאריך ושעה: ${rejectedAt}${note && note !== MANUAL_REJECTION_REASON ? `\n${note}` : ""}`,
      manual_rejected_at: rejectedAt,
      manual_rejection_note: note,
      manual_rejection_source: rejection.source || "",
    };
  }

  const manual = state.manualSubmissions[job.key];
  if (!manual) {
    return job;
  }
  return {
    ...job,
    original_status: job.status,
    status: MANUAL_STATUS,
    manual_submitted_at: manual.submittedAt,
    manual_note: manual.note || "",
    manual_source: manual.source || "",
  };
}

function jobViews() {
  return state.data.jobs.map(jobView);
}

function truncateForSync(value, maxLength = 900) {
  const clean = String(value || "").trim();
  if (clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, maxLength - 1)}…`;
}

async function pushManualAction(action, key, submittedAt = "", note = "") {
  if (!state.sync.enabled) {
    return;
  }

  const job = selectedRawJob(key) || {};
  const eventId = `${action}:${key}:${submittedAt || timestampNow()}:${Math.random().toString(36).slice(2)}`;
  state.sync.saving = true;
  state.sync.lastError = "";
  renderChrome();

  try {
    const payload = await syncRequest(
      {
      action,
      event_id: eventId,
      job_key: key,
      manual_submitted_at: submittedAt,
      manual_rejected_at: submittedAt,
      note,
      company: job.company || "",
      title: job.title || "",
      location: job.location || "",
      link: job.link || "",
      score: job.score || "",
      requirements: truncateForSync(job.requirements),
      fit: truncateForSync(job.fit),
      user_agent: navigator.userAgent,
      },
      "POST"
    );

    if (!payload || payload.ok === false) {
      throw new Error(payload?.error || "sync_error");
    }

    mergeRemoteManualState(payload.manual_submissions || {}, payload.manual_rejections || {});
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
    const successMessages = {
      markManualSubmitted: "ההגשה הידנית נשמרה במעקב המרכזי",
      clearManualSubmitted: "הסימון הידני הוסר מהמעקב המרכזי",
      markManualRejected: "הפסילה הידנית נשמרה במעקב המרכזי",
      clearManualRejected: "הפסילה הידנית הוסרה מהמעקב המרכזי",
    };
    showToast(successMessages[action] || "העדכון נשמר במעקב המרכזי");
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    const currentSubmission = state.manualSubmissions[key];
    const currentRejection = state.manualRejections[key];
    if (currentSubmission || currentRejection) {
      if (currentSubmission) {
        currentSubmission.source = "local";
      }
      if (currentRejection) {
        currentRejection.source = "local";
      }
      saveManualSubmissions();
    }
    showToast("נשמר מקומית, אבל הסנכרון המרכזי נכשל כרגע");
  } finally {
    state.sync.saving = false;
    render();
    refreshOpenModal();
  }
}

async function markManualSubmitted(key) {
  const submittedAt = timestampNow();
  const note = state.manualSubmissions[key]?.note || "";
  state.manualSubmissions[key] = {
    submittedAt,
    note,
    source: state.sync.enabled ? "syncing" : "local",
  };
  delete state.manualRejections[key];
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();

  if (!state.sync.enabled) {
    showToast(`סומן כהוגש ידנית: ${submittedAt}`);
    return;
  }

  showToast(`סומן כהוגש ידנית ונשלח לסנכרון: ${submittedAt}`);
  await pushManualAction("markManualSubmitted", key, submittedAt, note);
}

async function clearManualSubmitted(key) {
  delete state.manualSubmissions[key];
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();

  if (!state.sync.enabled) {
    showToast("סימון ההגשה הידנית בוטל");
    return;
  }

  showToast("מסיר את הסימון מהמעקב המרכזי");
  await pushManualAction("clearManualSubmitted", key);
}

async function markManualRejected(key) {
  const rejectedAt = timestampNow();
  const note = MANUAL_REJECTION_REASON;
  state.manualRejections[key] = {
    rejectedAt,
    note,
    source: state.sync.enabled ? "syncing" : "local",
  };
  delete state.manualSubmissions[key];
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();

  if (!state.sync.enabled) {
    showToast(`נפסל בבחירה ידנית: ${rejectedAt}`);
    return;
  }

  showToast(`נפסל בבחירה ידנית ונשלח לסנכרון: ${rejectedAt}`);
  await pushManualAction("markManualRejected", key, rejectedAt, note);
}

async function clearManualRejected(key) {
  delete state.manualRejections[key];
  saveManualSubmissions();
  refreshAfterManualChange(key);
  refreshOpenModal();

  if (!state.sync.enabled) {
    showToast("פסילה ידנית בוטלה");
    return;
  }

  showToast("מסיר את הפסילה הידנית מהמעקב המרכזי");
  await pushManualAction("clearManualRejected", key);
}

function refreshAfterManualChange(key) {
  state.selectedKey = key;
  render();
  state.selectedKey = key;
  renderDetails();
}

async function loadState() {
  loadManualSubmissions();
  await loadSyncConfig();

  const response = await fetch("assets/job-data.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("לא נמצא קובץ נתונים לפרסום");
  }
  state.data = await response.json();
  if (!state.selectedKey && state.data.jobs.length > 0) {
    state.selectedKey = state.data.jobs[0].key;
  }

  render();
  await loadRemoteManualSubmissions();
  render();
}

function renderMetrics() {
  const counts = state.data.counts;
  const views = jobViews();
  const manualCount = state.data.jobs.filter((job) => state.manualSubmissions[job.key]).length;
  const statusCount = (status) => views.filter((job) => job.status === status).length;
  const items = [
    ["נסרקו", counts.scanned],
    ["תועדו", counts.documented],
    ["מתאימות", counts.suitable],
    ["הוגשו", statusCount("הוגש")],
    ["הוגשו ידנית", manualCount],
    ["ממתינות", statusCount("נדרש אישור")],
    ["נפסלו", statusCount("נפסל")],
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
      job.manual_note,
      job.manual_rejected_at,
      job.manual_rejection_note,
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

function manualSourceText(source) {
  if (source === "remote") {
    return "נשמר במעקב המרכזי.";
  }
  if (state.sync.enabled) {
    return "ממתין לאישור סנכרון.";
  }
  return "נשמר בדפדפן הזה בלבד.";
}

function manualSubmittedBlock(timestamp, source) {
  if (!timestamp) {
    return "";
  }
  return `
    <section class="detail-section">
      <h3>הגשה ידנית</h3>
      <p class="detail-text">הוגש ידנית בתאריך ושעה: <span class="timestamp" dir="ltr">${escapeHtml(timestamp)}</span></p>
      <p class="detail-text">${escapeHtml(manualSourceText(source))}</p>
    </section>
  `;
}

function manualRejectedBlock(timestamp, source) {
  if (!timestamp) {
    return "";
  }
  return `
    <section class="detail-section">
      <h3>פסילה ידנית</h3>
      <p class="detail-text">${MANUAL_REJECTION_REASON} בתאריך ושעה: <span class="timestamp" dir="ltr">${escapeHtml(timestamp)}</span></p>
      <p class="detail-text">${escapeHtml(manualSourceText(source))}</p>
    </section>
  `;
}

function jobDetailsHtml(job, titleId = "") {
  const pillClass = statusClass.get(job.status) || "";
  const headingId = titleId ? ` id="${escapeHtml(titleId)}"` : "";
  const originalStatus = job.original_status || job.status || "";
  const manualTimestamp = job.manual_submitted_at || "";
  const manualSource = job.manual_source || "";
  const manualRejectedAt = job.manual_rejected_at || "";
  const manualRejectionSource = job.manual_rejection_source || "";
  const manualFact = manualTimestamp
    ? `<span class="fact manual-fact">הוגש ידנית: <span class="timestamp" dir="ltr">${escapeHtml(manualTimestamp)}</span></span>`
    : "";
  const manualRejectFact = manualRejectedAt
    ? `<span class="fact manual-fact">נפסל ידנית: <span class="timestamp" dir="ltr">${escapeHtml(manualRejectedAt)}</span></span>`
    : "";
  const manualAction = manualRejectedAt
    ? ""
    : job.manual_submitted_at
    ? `<button type="button" class="manual-button secondary" data-manual-action="clear" data-key="${escapeHtml(job.key)}">בטל סימון ידני</button>`
    : `<button type="button" class="manual-button" data-manual-action="mark" data-key="${escapeHtml(job.key)}">סמן כהוגש ידנית</button>`;
  const manualRejectAction = manualRejectedAt
    ? `<button type="button" class="manual-button danger-secondary" data-manual-action="clear-reject" data-key="${escapeHtml(job.key)}">בטל פסילה ידנית</button>`
    : originalStatus === "נדרש אישור" && !manualTimestamp
    ? `<button type="button" class="manual-button danger" data-manual-action="reject" data-key="${escapeHtml(job.key)}">סמן כנפסל</button>`
    : "";
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
          ${manualRejectFact}
          <span class="fact">${escapeHtml(job.cv || "ללא CV")}</span>
        </div>
        <div class="actions">
          <a class="link-button" href="${escapeHtml(job.link)}" target="_blank" rel="noreferrer">פתח משרה מקורית</a>
          ${manualAction}
          ${manualRejectAction}
        </div>
      </header>

      ${manualSubmittedBlock(manualTimestamp, manualSource)}
      ${manualRejectedBlock(manualRejectedAt, manualRejectionSource)}
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

  if (!els.syncStatus) {
    return;
  }

  let label = "סימון מקומי";
  let variant = "local";
  if (state.sync.enabled) {
    label = state.sync.saving ? "מסנכרן" : "מסונכרן לענן";
    variant = state.sync.saving ? "syncing" : "synced";
    if (state.sync.lastError) {
      label = "סנכרון לא זמין";
      variant = "sync-error";
    }
  }
  els.syncStatus.textContent = label;
  els.syncStatus.className = `state-pill ${variant}`;
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
    void markManualSubmitted(key);
  } else if (button.dataset.manualAction === "clear") {
    void clearManualSubmitted(key);
  } else if (button.dataset.manualAction === "reject") {
    void markManualRejected(key);
  } else if (button.dataset.manualAction === "clear-reject") {
    void clearManualRejected(key);
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
