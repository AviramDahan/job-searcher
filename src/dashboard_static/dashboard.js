const els = {
  candidateName: document.querySelector("#candidateName"),
  generatedAt: document.querySelector("#generatedAt"),
  telegramState: document.querySelector("#telegramState"),
  metrics: document.querySelector("#metrics"),
  locationPolicy: document.querySelector("#locationPolicy"),
  searchInput: document.querySelector("#searchInput"),
  scoreFilter: document.querySelector("#scoreFilter"),
  sortBy: document.querySelector("#sortBy"),
  segments: [...document.querySelectorAll(".segment")],
  visibleCount: document.querySelector("#visibleCount"),
  jobList: document.querySelector("#jobList"),
  jobDetails: document.querySelector("#jobDetails"),
  toast: document.querySelector("#toast"),
};

const MANUAL_REQUIRED_STATUS = "נדרשת הגשה ידנית";
const PENDING_STATUS = "נדרש אישור";

const statusClass = new Map([
  ["הוגש", "status-submitted"],
  [MANUAL_REQUIRED_STATUS, "status-manual-required"],
  [PENDING_STATUS, "status-pending"],
  ["נפסל", "status-rejected"],
]);

const state = {
  data: null,
  selectedKey: null,
  status: "all",
  busy: false,
  enginePlans: new Map(),
  locationPreferences: { approvedLocations: {} },
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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function loadState() {
  const payload = await api("/api/state");
  state.data = payload.state;
  state.locationPreferences = {
    approvedLocations: payload.state.location_preferences?.approved_locations || {},
  };
  if (!state.selectedKey && state.data.jobs.length > 0) {
    state.selectedKey = state.data.jobs[0].key;
  }
  render();
}

function slugifyCity(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\p{L}\p{N}_-]+/gu, "")
    .slice(0, 80);
}

function optionTerms(option = {}) {
  const terms = Array.isArray(option.terms) ? option.terms : [];
  return [...new Set([option.label, option.key, ...terms].map((term) => String(term || "").trim()).filter(Boolean))];
}

function locationOptionByKey(key) {
  const policy = state.data?.location_policy || {};
  const options = [...(policy.default_approved || []), ...(policy.user_approvable || [])];
  const remote = state.locationPreferences.approvedLocations[key];
  return (
    options.find((option) => option.key === key) ||
    (remote
      ? {
          key: remote.key,
          label: remote.label,
          terms: remote.terms || [remote.label],
        }
      : null)
  );
}

function approvedLocationEntries() {
  return Object.values(state.locationPreferences.approvedLocations).filter((entry) => entry && entry.approved);
}

function isLocationApproved(key) {
  return Boolean(state.locationPreferences.approvedLocations[key]?.approved);
}

async function saveLocationPreference(option, approved) {
  state.busy = true;
  render();
  try {
    const cityKey = String(option.key || slugifyCity(option.label)).trim();
    const cityLabel = String(option.label || cityKey).trim();
    const payload = await api("/api/location-preferences", {
      method: "POST",
      body: JSON.stringify({
        city_key: cityKey,
        city_label: cityLabel,
        city_terms: optionTerms({ ...option, key: cityKey, label: cityLabel }).join("|"),
        approved: approved ? "true" : "false",
      }),
    });
    state.data = payload.state;
    state.locationPreferences = {
      approvedLocations: payload.location_preferences?.approved_locations || {},
    };
    showToast(approved ? "העיר נוספה למדיניות החיפוש" : "העיר הוסרה ממדיניות החיפוש");
    render();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    render();
  }
}

function renderMetrics() {
  const counts = state.data.counts;
  const manualAlerts = state.data.telegram.manual_alerts;
  const retry = state.data.retry_queue;
  const items = [
    ["נסרקו", counts.scanned],
    ["תועדו", counts.documented],
    ["מתאימות", counts.suitable],
    ["הוגשו", counts.submitted],
    ["הגשה ידנית", counts.manual_required || 0],
    ["ממתינות", counts.pending],
    ["נפסלו", counts.rejected],
    ["Telegram", manualAlerts.sent || 0],
  ];

  els.metrics.innerHTML = items
    .map(([label, value]) => {
      const suffix = label === "Telegram" && retry.total ? ` · retry ${retry.total}` : "";
      return `<article class="metric"><span class="metric-value">${escapeHtml(value)}</span><span class="metric-label">${escapeHtml(label + suffix)}</span></article>`;
    })
    .join("");
}

function renderLocationPolicy() {
  if (!els.locationPolicy || !state.data) {
    return;
  }

  const policy = state.data.location_policy || {};
  const defaultApproved = Array.isArray(policy.default_approved) ? policy.default_approved : [];
  const userApprovable = Array.isArray(policy.user_approvable) ? policy.user_approvable : [];
  const knownKeys = new Set([...defaultApproved, ...userApprovable].map((option) => option.key));
  const customApproved = approvedLocationEntries().filter((entry) => !knownKeys.has(entry.key));
  const disabled = state.busy ? " disabled" : "";

  const defaultChips = defaultApproved
    .map((option) => `<span class="city-chip locked">${escapeHtml(option.label)}</span>`)
    .join("");
  const optionalChips = userApprovable
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button type="button" class="city-chip toggle${approved ? " approved" : ""}" data-location-action="toggle" data-location-key="${escapeHtml(
        option.key
      )}" aria-pressed="${approved ? "true" : "false"}"${disabled}>${escapeHtml(option.label)}</button>
      `;
    })
    .join("");
  const customChips = customApproved
    .map(
      (entry) =>
        `<button type="button" class="city-chip toggle approved custom" data-location-action="toggle" data-location-key="${escapeHtml(
          entry.key
        )}" aria-pressed="true"${disabled}>${escapeHtml(entry.label)}</button>`
    )
    .join("");

  els.locationPolicy.innerHTML = `
    <div class="location-head">
      <div>
        <p class="eyebrow">מדיניות מיקום</p>
        <h2>ערי חיפוש מאושרות</h2>
      </div>
      <span class="state-pill ready">${escapeHtml(defaultApproved.length + approvedLocationEntries().length)} ערים מאושרות</span>
    </div>
    <div class="location-groups">
      <section class="location-group">
        <h3>ברירת מחדל</h3>
        <div class="city-grid">${defaultChips}</div>
      </section>
      <section class="location-group">
        <h3>בחירה</h3>
        <div class="city-grid">${optionalChips}${customChips}</div>
      </section>
      <form class="custom-city-form" data-location-action="custom">
        <label class="search-box" for="customCityInput">
          <span>עיר נוספת</span>
          <input id="customCityInput" name="city" type="text" autocomplete="off" maxlength="80" />
        </label>
        <button type="submit" class="action-button primary"${disabled}>הוסף</button>
      </form>
    </div>
  `;
}

function currentJobs() {
  const query = els.searchInput.value.trim().toLowerCase();
  const minScore = Number(els.scoreFilter.value || 0);
  const selectedStatus = state.status;

  const filtered = state.data.jobs.filter((job) => {
    const matchesStatus = selectedStatus === "all" || job.status === selectedStatus;
    const matchesScore = Number(job.score || 0) >= minScore;
    const haystack = [job.company, job.title, job.location, job.link, job.requirements, job.fit, job.stop_reason]
      .join(" ")
      .toLowerCase();
    return matchesStatus && matchesScore && haystack.includes(query);
  });

  const sortBy = els.sortBy.value;
  filtered.sort((a, b) => {
    if (sortBy === "date") {
      return String(b.date || "").localeCompare(String(a.date || ""));
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
        <button type="button" class="job-row${selected}" data-key="${escapeHtml(job.key)}">
          <span class="score-badge">${escapeHtml(job.score)}</span>
          <span class="job-main">
            <span class="job-title">${escapeHtml(job.title)}</span>
            <span class="job-company">${escapeHtml(job.company)}</span>
            <span class="job-location">${escapeHtml(job.location || "ללא מיקום")}</span>
          </span>
          <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
        </button>
      `;
    })
    .join("");
}

function textBlock(label, value) {
  const clean = String(value || "").trim();
  const body = clean
    ? `<p class="detail-text">${escapeHtml(clean)}</p>`
    : `<p class="detail-text empty">אין נתון</p>`;
  return `<section class="detail-section"><h3>${escapeHtml(label)}</h3>${body}</section>`;
}

function renderDetails() {
  const job = state.data.jobs.find((item) => item.key === state.selectedKey);
  if (!job) {
    els.jobDetails.innerHTML = `<div class="empty-state">אין משרה נבחרת</div>`;
    return;
  }

  const pillClass = statusClass.get(job.status) || "";
  const telegramDisabled = !state.data.telegram.configured || state.busy ? "disabled" : "";
  const actionDisabled = state.busy ? "disabled" : "";
  const enginePlan = state.enginePlans.get(job.key);
  const engineSection = enginePlan
    ? `
      <section class="detail-section engine-result">
        <h3>בדיקת מנוע</h3>
        <div class="engine-grid">
          <span>אתר</span><strong>${escapeHtml(enginePlan.site)}</strong>
          <span>החלטה</span><strong>${escapeHtml(enginePlan.decision)}</strong>
          <span>פעולה</span><strong>${escapeHtml(enginePlan.action)}</strong>
          <span>ניתן לנסות</span><strong>${enginePlan.can_attempt ? "כן" : "לא"}</strong>
        </div>
        <p class="detail-text">${escapeHtml(enginePlan.reason)}</p>
        <p class="detail-text">${escapeHtml(enginePlan.next_step)}</p>
      </section>
    `
    : "";

  els.jobDetails.innerHTML = `
    <div class="details-inner">
      <header class="details-head">
        <div class="details-title-line">
          <div>
            <h2 class="details-title">${escapeHtml(job.title)}</h2>
            <p class="details-company">${escapeHtml(job.company)}</p>
          </div>
          <span class="score-badge">${escapeHtml(job.score)}</span>
        </div>
        <div class="quick-facts">
          <span class="status-pill ${pillClass}">${escapeHtml(job.status || "ללא סטטוס")}</span>
          <span class="fact">${escapeHtml(job.location || "ללא מיקום")}</span>
          <span class="fact">${escapeHtml(job.date || "ללא תאריך")}</span>
          <span class="fact">${escapeHtml(job.cv || "ללא CV")}</span>
        </div>
        <div class="actions">
          <a class="link-button" href="${escapeHtml(job.link)}" target="_blank" rel="noreferrer">פתח משרה</a>
          <button type="button" class="action-button primary" data-action="telegram" ${telegramDisabled}>שלח לטלגרם</button>
          <button type="button" class="action-button" data-action="engine_plan" ${actionDisabled}>בדיקת מנוע</button>
          <button type="button" class="action-button" data-action="mark_submitted" ${actionDisabled}>סמן כהוגש ידנית</button>
          <button type="button" class="action-button danger" data-action="mark_rejected" ${actionDisabled}>סמן כנפסל</button>
        </div>
      </header>

      ${engineSection}
      ${textBlock("דרישות מרכזיות", job.requirements)}
      ${textBlock("סיבות התאמה", job.fit)}
      ${textBlock("סיבת עצירה או פסילה", job.stop_reason)}
      ${textBlock("נוסח פנייה", job.cover)}
      ${textBlock("שלב הבא", job.next_step)}

      <section class="detail-section note-form">
        <h3>הערת מעקב</h3>
        <textarea id="noteInput" placeholder="הערה פנימית"></textarea>
        <div class="note-row">
          <input id="cvInput" type="text" value="${escapeHtml(job.cv || "")}" placeholder="שם קובץ CV" />
          <button type="button" class="action-button warning" data-action="add_note" ${actionDisabled}>שמור הערה</button>
        </div>
      </section>
    </div>
  `;
}

function renderChrome() {
  els.candidateName.textContent = `${state.data.candidate.full_name} · ניהול מועמדויות`;
  els.generatedAt.textContent = `עודכן: ${state.data.generated_at}`;
  els.telegramState.textContent = state.data.telegram.configured ? "Telegram מחובר" : "Telegram לא מוגדר";
  els.telegramState.classList.toggle("ready", state.data.telegram.configured);
  els.telegramState.classList.toggle("missing", !state.data.telegram.configured);
}

function render() {
  if (!state.data) {
    return;
  }
  renderChrome();
  renderMetrics();
  renderLocationPolicy();
  renderJobs();
  renderDetails();
}

async function updateJob(action) {
  const note = document.querySelector("#noteInput")?.value || "";
  const cvFilename = document.querySelector("#cvInput")?.value || "";
  state.busy = true;
  renderDetails();
  try {
    const payload = await api("/api/jobs/update", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey, action, note, cv_filename: cvFilename }),
    });
    state.data = payload.state;
    state.selectedKey = payload.job.key;
    showToast("עודכן");
    render();
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

async function sendTelegram() {
  state.busy = true;
  renderDetails();
  try {
    await api("/api/jobs/telegram", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey }),
    });
    showToast("נשלחה התראה לטלגרם");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

async function runEnginePlan() {
  state.busy = true;
  renderDetails();
  try {
    const payload = await api("/api/jobs/engine-plan", {
      method: "POST",
      body: JSON.stringify({ key: state.selectedKey }),
    });
    state.enginePlans.set(state.selectedKey, payload.engine.plan);
    showToast("בדיקת המנוע מוכנה");
  } catch (error) {
    showToast(error.message);
  } finally {
    state.busy = false;
    renderDetails();
  }
}

els.jobList.addEventListener("click", (event) => {
  const row = event.target.closest(".job-row");
  if (!row) {
    return;
  }
  state.selectedKey = row.dataset.key;
  render();
});

els.jobDetails.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.action;
  if (action === "telegram") {
    sendTelegram();
  } else if (action === "engine_plan") {
    runEnginePlan();
  } else {
    updateJob(action);
  }
});

els.locationPolicy?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-location-action='toggle']");
  if (!button) {
    return;
  }
  const key = button.dataset.locationKey;
  const option = locationOptionByKey(key);
  if (!option) {
    showToast("לא נמצאו פרטי עיר לעדכון");
    return;
  }
  void saveLocationPreference(option, !isLocationApproved(key));
});

els.locationPolicy?.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-location-action='custom']");
  if (!form) {
    return;
  }
  event.preventDefault();
  const input = form.querySelector("input[name='city']");
  const label = String(input?.value || "").trim();
  const key = `custom_${slugifyCity(label)}`;
  if (!label || key === "custom_") {
    showToast("יש להזין שם עיר");
    return;
  }
  if (input) {
    input.value = "";
  }
  void saveLocationPreference({ key, label, terms: [label] }, true);
});

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
