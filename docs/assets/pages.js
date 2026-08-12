const els = {
  candidateName: document.querySelector("#candidateName"),
  generatedAt: document.querySelector("#generatedAt"),
  syncStatus: document.querySelector("#syncStatus"),
  metrics: document.querySelector("#metrics"),
  insights: document.querySelector("#insights"),
  locationPolicy: document.querySelector("#locationPolicy"),
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
  ["נדרשת הגשה ידנית", "status-manual-required"],
  ["נדרש אישור", "status-pending"],
  ["נפסל", "status-rejected"],
]);

const MANUAL_STATUS = "הוגש ידנית";
const MANUAL_REQUIRED_STATUS = "נדרשת הגשה ידנית";
const PENDING_STATUS = "נדרש אישור";
const MANUAL_REJECTED_STATUS = "נפסל";
const MANUAL_REJECTION_REASON = "נפסל בבחירה ידנית";
const MANUAL_STORAGE_KEY = "job-searcher-manual-submissions-v1";
const MANUAL_REJECTIONS_STORAGE_KEY = "job-searcher-manual-rejections-v1";
const LOCATION_PREFS_STORAGE_KEY = "job-searcher-location-preferences-v1";
const SYNC_CONFIG_PATH = "assets/dashboard-config.json";
const SYNC_TIMEOUT_MS = 12000;
const SYNC_UNAVAILABLE_MESSAGE = "הסנכרון לא זמין. אנא רענן או בדוק מצב סנכרון.";
const SYNC_LOADING_MESSAGE = "הסנכרון עדיין נטען. אנא המתן רגע לפני ביצוע פעולה.";
const SYNC_SAVING_MESSAGE = "הסנכרון בפעולה. אנא המתן לסיום העדכון.";
const SYNC_ALERTS_ONLY_MESSAGE = "אחסון מרכזי לא זמין כרגע. הסימון יישמר בדפדפן ותישלח התראת Telegram.";

const state = {
  data: null,
  selectedKey: null,
  status: "all",
  manualSubmissions: {},
  manualRejections: {},
  locationPreferences: {
    approvedLocations: {},
    radiusKm: 0,
  },
  sync: {
    config: {},
    enabled: false,
    loaded: false,
    saving: false,
    lastError: "",
    lastSyncedAt: "",
    storageStatus: "",
    storageWarning: "",
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
    source: String(value.source || "remote").trim(),
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
    source: String(value.source || "remote").trim(),
  };
}

function normalizeLocationPreferenceEntry(value = {}) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const key = String(value.key || value.city_key || "").trim();
  const label = String(value.label || value.city || value.city_label || "").trim();
  if (!key || !label) {
    return null;
  }

  const terms = Array.isArray(value.terms)
    ? value.terms.map((term) => String(term || "").trim()).filter(Boolean)
    : [label, key];

  return {
    key,
    label,
    terms: [...new Set(terms)],
    approved: value.approved === undefined ? true : value.approved === true || String(value.approved || "").toLowerCase() === "true",
    updatedAt: String(value.updatedAt || value.updated_at || "").trim(),
    source: String(value.source || "remote").trim(),
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

function normalizeLocationPreferences(value) {
  const approvedLocations = {};
  const preferences = value && typeof value === "object" ? value : {};
  const approved = preferences.approved_locations || preferences.approvedLocations || {};
  const entries = Array.isArray(approved) ? approved : Object.values(approved || {});
  const radiusKm = Math.max(0, Math.min(Number.parseInt(String(preferences.radius_km || preferences.radiusKm || "0"), 10) || 0, 250));

  entries.forEach((entry) => {
    const normalizedEntry = normalizeLocationPreferenceEntry(entry);
    if (normalizedEntry) {
      approvedLocations[normalizedEntry.key] = normalizedEntry;
    }
  });

  return { approvedLocations, radiusKm };
}

function remoteLocationPreferences(value) {
  const normalized = normalizeLocationPreferences(value);
  return { approved_locations: normalized.approvedLocations, radius_km: normalized.radiusKm };
}

function saveManualSubmissions() {
  localStorage.setItem(MANUAL_STORAGE_KEY, JSON.stringify(state.manualSubmissions));
  localStorage.setItem(MANUAL_REJECTIONS_STORAGE_KEY, JSON.stringify(state.manualRejections));
  localStorage.setItem(LOCATION_PREFS_STORAGE_KEY, JSON.stringify(state.locationPreferences));
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

function updateSyncStorageStatus(payload = {}) {
  state.sync.storageStatus = String(payload?.storage_status || "").trim();
  state.sync.storageWarning = String(payload?.storage_warning || "").trim();
}

function syncAlertsOnly() {
  return state.sync.storageStatus === "alerts_only";
}

async function loadSyncConfig() {
  try {
    const response = await fetch(SYNC_CONFIG_PATH, { cache: "no-store" });
    if (!response.ok) {
      state.sync.config = {};
      state.sync.enabled = false;
      state.sync.lastError = "sync_config_unavailable";
      return;
    }

    const config = await response.json();
    state.sync.config = config && typeof config === "object" ? config : {};
    state.sync.enabled = !isPlaceholderEndpoint(syncEndpoint());
    state.sync.lastError = state.sync.enabled ? "" : "sync_not_configured";
    state.sync.storageStatus = "";
    state.sync.storageWarning = "";
  } catch {
    state.sync.config = {};
    state.sync.enabled = false;
    state.sync.lastError = "sync_config_unavailable";
    state.sync.storageStatus = "";
    state.sync.storageWarning = "";
  }
}

function syncWriteBlockMessage() {
  if (state.sync.saving) {
    return SYNC_SAVING_MESSAGE;
  }
  if (!state.sync.enabled || state.sync.lastError) {
    return SYNC_UNAVAILABLE_MESSAGE;
  }
  if (!state.sync.loaded) {
    return SYNC_LOADING_MESSAGE;
  }
  return "";
}

function guardManualWrite() {
  const message = syncWriteBlockMessage();
  if (!message) {
    return true;
  }
  showToast(message);
  render();
  refreshOpenModal();
  return false;
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
      location_preferences: remoteLocationPreferences(currentState.location_preferences),
      events: currentState.events || [],
    };
  }

  const nextState = {
    ok: true,
    generated_at: new Date().toISOString(),
    manual_submissions: currentState.manual_submissions || {},
    manual_rejections: currentState.manual_rejections || {},
    location_preferences: remoteLocationPreferences(currentState.location_preferences),
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

  if (!duplicate && params.action === "setLocationPreference") {
    const approved = String(params.approved || "").toLowerCase() === "true";
    if (approved) {
      nextState.location_preferences.approved_locations[params.city_key] = {
        key: String(params.city_key || ""),
        label: String(params.city_label || ""),
        terms: String(params.city_terms || "")
          .split("|")
          .map((term) => term.trim())
          .filter(Boolean),
        approved,
        updatedAt: timestampNow(),
        source: "remote",
      };
    } else {
      delete nextState.location_preferences.approved_locations[params.city_key];
    }
  }

  if (!duplicate && params.action === "setLocationRadius") {
    nextState.location_preferences.radius_km = Math.max(0, Math.min(Number.parseInt(String(params.radius_km || "0"), 10) || 0, 250));
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
      city_key: String(params.city_key || ""),
      city_label: String(params.city_label || ""),
      approved: String(params.approved || ""),
      radius_km: String(params.radius_km || ""),
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
    location_preferences: nextState.location_preferences,
    telegram: { sent: false, reason: "jsonblob_transport_no_server_secret" },
  };
}

function mergeRemoteState(remoteSubmissions, remoteRejections, remoteLocationPreferences) {
  const remoteSubmitted = normalizeManualSubmissions(remoteSubmissions);
  const remoteRejected = normalizeManualRejections(remoteRejections);
  const remoteLocations = normalizeLocationPreferences(remoteLocationPreferences);
  state.manualSubmissions = remoteSubmitted;
  state.manualRejections = remoteRejected;
  state.locationPreferences = remoteLocations;
  saveManualSubmissions();
}

function applyAlertsOnlyLocationPreference(option, approved) {
  const cityKey = String(option.key || slugifyCity(option.label)).trim();
  if (!cityKey) {
    return;
  }
  if (approved) {
    state.locationPreferences.approvedLocations[cityKey] = normalizeLocationPreferenceEntry({
      key: cityKey,
      label: String(option.label || cityKey).trim(),
      terms: optionTerms({ ...option, key: cityKey, label: option.label || cityKey }),
      approved: true,
      updatedAt: timestampNow(),
      source: "alerts_only",
    });
  } else {
    delete state.locationPreferences.approvedLocations[cityKey];
  }
  saveManualSubmissions();
}

function applyAlertsOnlyManualAction(action, key, submittedAt = "", note = "") {
  if (!key) {
    return;
  }
  if (action === "markManualSubmitted") {
    state.manualSubmissions[key] = {
      submittedAt: submittedAt || timestampNow(),
      updatedAt: timestampNow(),
      note: String(note || "").trim(),
      source: "alerts_only",
    };
    delete state.manualRejections[key];
  }
  if (action === "clearManualSubmitted") {
    delete state.manualSubmissions[key];
  }
  if (action === "markManualRejected") {
    state.manualRejections[key] = {
      rejectedAt: submittedAt || timestampNow(),
      updatedAt: timestampNow(),
      note: String(note || MANUAL_REJECTION_REASON).trim(),
      source: "alerts_only",
    };
    delete state.manualSubmissions[key];
  }
  if (action === "clearManualRejected") {
    delete state.manualRejections[key];
  }
  saveManualSubmissions();
}

async function loadRemoteManualSubmissions() {
  if (!state.sync.enabled) {
    state.sync.lastError = state.sync.lastError || "sync_not_configured";
    showToast(SYNC_UNAVAILABLE_MESSAGE);
    return;
  }

  try {
    state.sync.lastError = "";
    const payload = await syncRequest({ action: "listUpdates" });
    if (!payload || payload.ok === false) {
      throw new Error(payload?.error || "sync_error");
    }
    updateSyncStorageStatus(payload);
    if (!syncAlertsOnly()) {
      mergeRemoteState(payload.manual_submissions || {}, payload.manual_rejections || {}, payload.location_preferences || {});
    }
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    showToast(SYNC_UNAVAILABLE_MESSAGE);
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
  const options = [
    ...(policy.default_approved || []),
    ...(policy.user_approvable || []),
    ...(policy.nearby_options || []),
    ...(policy.region_options || []),
    ...(policy.map_points || []),
  ];
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

function isDefaultLocation(key) {
  const policy = state.data?.location_policy || {};
  return (policy.default_approved || []).some((option) => option.key === key);
}

function selectedRadiusKm() {
  return Math.max(0, Math.min(Number.parseInt(String(state.locationPreferences.radiusKm || "0"), 10) || 0, 250));
}

function homeLocation(policy = state.data?.location_policy || {}) {
  return policy.home || {};
}

function distanceKm(lat1, lng1, lat2, lng2) {
  const earthRadiusKm = 6371;
  const toRadians = (value) => (Number(value) * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLng = toRadians(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function isPointWithinRadius(point = {}, policy = state.data?.location_policy || {}) {
  const radius = selectedRadiusKm();
  const home = homeLocation(policy);
  if (!radius || point.key === home.key) {
    return false;
  }
  const lat = Number(point.lat);
  const lng = Number(point.lng);
  const homeLat = Number(home.lat);
  const homeLng = Number(home.lng);
  if (![lat, lng, homeLat, homeLng].every(Number.isFinite)) {
    return false;
  }
  return distanceKm(homeLat, homeLng, lat, lng) <= radius + 0.001;
}

function isScannedLocation(key, point = null) {
  return isDefaultLocation(key) || isLocationApproved(key) || (point ? isPointWithinRadius(point) : false);
}

function mapPointClass(point = {}) {
  if (point.key === state.data?.location_policy?.home?.key) {
    return "home";
  }
  if (isDefaultLocation(point.key) || isLocationApproved(point.key)) {
    return "scanned";
  }
  return isPointWithinRadius(point) ? "radius" : "not-scanned";
}

async function pushLocationPreference(option, approved) {
  const blockedMessage = syncWriteBlockMessage();
  if (blockedMessage) {
    showToast(blockedMessage);
    return;
  }

  const cityKey = String(option.key || slugifyCity(option.label)).trim();
  const cityLabel = String(option.label || cityKey).trim();
  const terms = optionTerms({ ...option, key: cityKey, label: cityLabel });
  const eventId = `setLocationPreference:${cityKey}:${approved}:${timestampNow()}:${Math.random().toString(36).slice(2)}`;
  state.sync.saving = true;
  state.sync.lastError = "";
  renderChrome();

  try {
    const payload = await syncRequest(
      {
        action: "setLocationPreference",
        event_id: eventId,
        city_key: cityKey,
        city_label: cityLabel,
        city_terms: terms.join("|"),
        approved: approved ? "true" : "false",
        user_agent: navigator.userAgent,
      },
      "POST"
    );

    if (!payload || payload.ok === false) {
      throw new Error(payload?.error || "sync_error");
    }

    updateSyncStorageStatus(payload);
    if (syncAlertsOnly()) {
      applyAlertsOnlyLocationPreference({ ...option, key: cityKey, label: cityLabel }, approved);
    } else {
      mergeRemoteState(payload.manual_submissions || {}, payload.manual_rejections || {}, payload.location_preferences || {});
    }
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
    showToast(
      syncAlertsOnly()
        ? approved
          ? "העיר נוספה בדפדפן. אחסון מרכזי לא זמין כרגע."
          : "העיר הוסרה בדפדפן. אחסון מרכזי לא זמין כרגע."
        : approved
        ? "העיר נוספה למדיניות החיפוש"
        : "העיר הוסרה ממדיניות החיפוש"
    );
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    showToast(SYNC_UNAVAILABLE_MESSAGE);
  } finally {
    state.sync.saving = false;
    render();
    refreshOpenModal();
  }
}

async function pushLocationRadius(radiusKm) {
  const blockedMessage = syncWriteBlockMessage();
  if (blockedMessage) {
    showToast(blockedMessage);
    return;
  }

  const radius = Math.max(0, Math.min(Number.parseInt(String(radiusKm || "0"), 10) || 0, 250));
  const eventId = `setLocationRadius:${radius}:${timestampNow()}:${Math.random().toString(36).slice(2)}`;
  state.sync.saving = true;
  state.sync.lastError = "";
  renderChrome();

  try {
    const payload = await syncRequest(
      {
        action: "setLocationRadius",
        event_id: eventId,
        radius_km: String(radius),
        user_agent: navigator.userAgent,
      },
      "POST"
    );

    if (!payload || payload.ok === false) {
      throw new Error(payload?.error || "sync_error");
    }

    updateSyncStorageStatus(payload);
    if (syncAlertsOnly()) {
      state.locationPreferences.radiusKm = radius;
      saveManualSubmissions();
    } else {
      mergeRemoteState(payload.manual_submissions || {}, payload.manual_rejections || {}, payload.location_preferences || {});
    }
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
    showToast(
      syncAlertsOnly()
        ? radius
          ? `רדיוס החיפוש נשמר בדפדפן ל-${radius} ק״מ`
          : "רדיוס החיפוש בוטל בדפדפן"
        : radius
        ? `רדיוס החיפוש עודכן ל-${radius} ק״מ`
        : "רדיוס החיפוש בוטל"
    );
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    showToast(SYNC_UNAVAILABLE_MESSAGE);
  } finally {
    state.sync.saving = false;
    render();
    refreshOpenModal();
  }
}

async function pushManualAction(action, key, submittedAt = "", note = "") {
  const blockedMessage = syncWriteBlockMessage();
  if (blockedMessage) {
    showToast(blockedMessage);
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

    updateSyncStorageStatus(payload);
    if (syncAlertsOnly()) {
      applyAlertsOnlyManualAction(action, key, submittedAt, note);
    } else {
      mergeRemoteState(payload.manual_submissions || {}, payload.manual_rejections || {}, payload.location_preferences || {});
    }
    state.sync.loaded = true;
    state.sync.lastSyncedAt = timestampNow();
    const successMessages = syncAlertsOnly()
      ? {
          markManualSubmitted: "הסימון נשמר בדפדפן ונשלחה התראת Telegram",
          clearManualSubmitted: "הסימון הידני הוסר מהדפדפן",
          markManualRejected: "הפסילה הידנית נשמרה בדפדפן",
          clearManualRejected: "הפסילה הידנית הוסרה מהדפדפן",
        }
      : {
          markManualSubmitted: "ההגשה הידנית נשמרה במעקב המרכזי",
          clearManualSubmitted: "הסימון הידני הוסר מהמעקב המרכזי",
          markManualRejected: "הפסילה הידנית נשמרה במעקב המרכזי",
          clearManualRejected: "הפסילה הידנית הוסרה מהמעקב המרכזי",
        };
    showToast(successMessages[action] || "העדכון נשמר במעקב המרכזי");
  } catch (error) {
    state.sync.lastError = error.message || "sync_error";
    showToast(SYNC_UNAVAILABLE_MESSAGE);
  } finally {
    state.sync.saving = false;
    render();
    refreshOpenModal();
  }
}

async function markManualSubmitted(key) {
  if (!guardManualWrite()) {
    return;
  }
  const submittedAt = timestampNow();
  const note = state.manualSubmissions[key]?.note || "";
  showToast(syncAlertsOnly() ? `שומר סימון הגשה ידנית בדפדפן: ${submittedAt}` : `שולח סימון הגשה ידנית לסנכרון: ${submittedAt}`);
  await pushManualAction("markManualSubmitted", key, submittedAt, note);
}

async function clearManualSubmitted(key) {
  if (!guardManualWrite()) {
    return;
  }

  showToast(syncAlertsOnly() ? "מסיר את הסימון מהדפדפן" : "מסיר את הסימון מהמעקב המרכזי");
  await pushManualAction("clearManualSubmitted", key);
}

async function markManualRejected(key) {
  if (!guardManualWrite()) {
    return;
  }
  const rejectedAt = timestampNow();
  const note = MANUAL_REJECTION_REASON;
  showToast(syncAlertsOnly() ? `שומר פסילה ידנית בדפדפן: ${rejectedAt}` : `שולח פסילה ידנית לסנכרון: ${rejectedAt}`);
  await pushManualAction("markManualRejected", key, rejectedAt, note);
}

async function clearManualRejected(key) {
  if (!guardManualWrite()) {
    return;
  }

  showToast(syncAlertsOnly() ? "מסיר את הפסילה הידנית מהדפדפן" : "מסיר את הפסילה הידנית מהמעקב המרכזי");
  await pushManualAction("clearManualRejected", key);
}

async function loadState() {
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
    ["הגשה ידנית", statusCount(MANUAL_REQUIRED_STATUS)],
    ["ממתינות", statusCount(PENDING_STATUS)],
    ["נפסלו", statusCount("נפסל")],
  ];

  els.metrics.innerHTML = items
    .map(
      ([label, value]) =>
        `<article class="metric"><span class="metric-value">${escapeHtml(value)}</span><span class="metric-label">${escapeHtml(label)}</span></article>`
    )
    .join("");
}

function renderInsightJobs(jobs = []) {
  if (!jobs.length) {
    return "";
  }
  return `
    <div class="insight-jobs">
      ${jobs
        .map(
          (job) => `
            <button type="button" class="insight-job" data-insight-key="${escapeHtml(job.key)}">
              <span class="insight-score">${escapeHtml(job.score)}</span>
              <span>
                <strong>${escapeHtml(job.title)}</strong>
                <small>${escapeHtml(job.company)} · ${escapeHtml(job.location || "ללא מיקום")}</small>
              </span>
            </button>
          `
        )
        .join("")}
    </div>
  `;
}

function renderConversionSummary(conversion = {}) {
  const counts = conversion.counts || {};
  const plan = conversion.submission_plan || {};
  const sources = Array.isArray(conversion.source_quality) ? conversion.source_quality : [];
  const recommendations = Array.isArray(conversion.recommendations) ? conversion.recommendations : [];
  const hasConversion = Object.keys(counts).length > 0 || Object.keys(plan).length > 0;

  if (!hasConversion) {
    return "";
  }

  const metricItems = [
    ["הגשות מתוך מתאימות", `${counts.submitted_rate_from_suitable ?? 0}%`],
    ["הגשות מתוך מתועדות", `${counts.submitted_rate_from_documented ?? 0}%`],
    ["מוכנות עכשיו", plan.runnable ?? 0],
    ["תוכניות מנוע", plan.plans ?? 0],
  ];

  return `
    <div class="conversion-panel">
      <div class="conversion-metrics" aria-label="מדדי המרה">
        ${metricItems
          .map(
            ([label, value]) => `
              <span class="conversion-metric">
                <strong>${escapeHtml(value)}</strong>
                <span>${escapeHtml(label)}</span>
              </span>
            `
          )
          .join("")}
      </div>
      <div class="source-quality" aria-label="איכות מקורות">
        ${sources
          .slice(0, 5)
          .map(
            (source) => `
              <span class="source-pill" title="${escapeHtml(`הוגשו ${source.submitted || 0}, ממתינות ${source.pending || 0}, ידניות ${source.manual_required || 0}`)}">
                ${escapeHtml(source.source || "מקור")} · ${escapeHtml(source.submission_rate ?? 0)}%
              </span>
            `
          )
          .join("")}
      </div>
      ${
        recommendations.length
          ? `<ul class="conversion-recommendations">
              ${recommendations
                .slice(0, 3)
                .map((recommendation) => `<li>${escapeHtml(recommendation)}</li>`)
                .join("")}
            </ul>`
          : ""
      }
    </div>
  `;
}

let locationMapInitHandle = 0;
let activeLocationMap = null;

function locationMapPoints(policy = {}) {
  return (Array.isArray(policy.map_points) ? policy.map_points : []).filter(
    (point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lng))
  );
}

function locationStatusText(point = {}) {
  const pointClass = mapPointClass(point);
  if (pointClass === "not-scanned") {
    return "לא בסריקה";
  }
  if (pointClass === "radius") {
    return `בתוך רדיוס ${selectedRadiusKm()} ק״מ`;
  }
  return "בסריקה";
}

function locationMapBounds(bounds = {}) {
  return [
    [Number(bounds.min_lat ?? 29.45), Number(bounds.min_lng ?? 34.25)],
    [Number(bounds.max_lat ?? 33.35), Number(bounds.max_lng ?? 35.95)],
  ];
}

function locationMapFocusBounds(bounds = {}) {
  return [
    [Number(bounds.min_lat ?? 31.25), Number(bounds.min_lng ?? 34.42)],
    [Number(bounds.max_lat ?? 31.95), Number(bounds.max_lng ?? 34.9)],
  ];
}

function regionPolygonLatLngs(region = {}) {
  const polygon = Array.isArray(region.map_area?.polygon) ? region.map_area.polygon : [];
  return polygon
    .map((point) => [Number(point.lat), Number(point.lng)])
    .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng));
}

function activeRegionOptions(policy = state.data?.location_policy || {}) {
  return (Array.isArray(policy.region_options) ? policy.region_options : []).filter(
    (option) => isLocationApproved(option.key) && regionPolygonLatLngs(option).length >= 3
  );
}

function extendBoundsWithLatLngs(bounds, latLngs = []) {
  latLngs.forEach(([lat, lng]) => bounds.extend([lat, lng]));
  return bounds;
}

function addLocationAreaOverlays(map, policy = {}) {
  const bounds = window.L.latLngBounds(locationMapFocusBounds(policy.map?.focus_bounds || {}));
  activeRegionOptions(policy).forEach((region) => {
    const polygon = regionPolygonLatLngs(region);
    extendBoundsWithLatLngs(bounds, polygon);
    window.L.polygon(polygon, {
      className: "location-region-overlay",
      color: "#0f766e",
      fillColor: "#0f766e",
      fillOpacity: 0.14,
      opacity: 0.82,
      weight: 2,
      dashArray: "7 6",
    })
      .addTo(map)
      .bindTooltip(`אזור ${region.label}`, {
        className: "location-map-tooltip",
        direction: "center",
        opacity: 0.92,
        sticky: true,
      });
  });

  const radius = selectedRadiusKm();
  const home = homeLocation(policy);
  const homeLat = Number(home.lat);
  const homeLng = Number(home.lng);
  if (radius > 0 && Number.isFinite(homeLat) && Number.isFinite(homeLng)) {
    const circle = window.L.circle([homeLat, homeLng], {
      className: "location-radius-overlay",
      color: "#1b5d92",
      fillColor: "#1b5d92",
      fillOpacity: 0.08,
      opacity: 0.88,
      radius: radius * 1000,
      weight: 2,
      dashArray: "8 6",
    })
      .addTo(map)
      .bindTooltip(`רדיוס ${radius} ק״מ משדרות`, {
        className: "location-map-tooltip",
        direction: "center",
        opacity: 0.92,
        sticky: true,
      });
    bounds.extend(circle.getBounds().getSouthWest());
    bounds.extend(circle.getBounds().getNorthEast());
  }

  return bounds;
}

function markerIconForPoint(point = {}) {
  const pointClass = mapPointClass(point);
  const size = pointClass === "home" ? 26 : 18;
  const radiusClass = isPointWithinRadius(point) ? " in-radius" : "";
  return window.L.divIcon({
    className: `location-map-pin ${pointClass}${radiusClass}`,
    html: `<span>${pointClass === "home" ? "קורן" : ""}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function markerTooltip(point = {}) {
  return `
    <strong>${escapeHtml(point.label || "")}</strong>
    <span>${escapeHtml(locationStatusText(point))}</span>
  `;
}

function markerPopup(point = {}, interactionsDisabled = false) {
  const pointClass = mapPointClass(point);
  const toggleable = pointClass !== "home" && !point.locked && !interactionsDisabled;
  const approved = isLocationApproved(point.key);
  return `
    <div class="location-map-popup" dir="rtl">
      <strong>${escapeHtml(point.label || "")}</strong>
      <span>${escapeHtml(locationStatusText(point))}</span>
      ${
        toggleable
          ? `<button type="button" class="map-popup-button" data-location-action="toggle" data-location-key="${escapeHtml(point.key)}">${
              approved ? "הסר מהסריקה" : "הוסף לסריקה"
            }</button>`
          : ""
      }
    </div>
  `;
}

function bindMapViewButtons(panel, map, policy = {}) {
  const israelBounds = locationMapBounds(policy.map?.bounds || {});
  const focusBounds = locationMapFocusBounds(policy.map?.focus_bounds || {});
  panel.querySelectorAll("[data-map-view]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.mapView;
      panel.querySelectorAll("[data-map-view]").forEach((item) => item.classList.toggle("active", item === button));
      map.fitBounds(view === "israel" ? israelBounds : focusBounds, {
        padding: [28, 28],
        maxZoom: view === "israel" ? 8 : 11,
      });
    });
  });
}

function initializeLocationMap(interactionsDisabled = false) {
  const panel = els.locationPolicy?.querySelector(".location-map-panel");
  const canvas = panel?.querySelector("[data-location-map-canvas]");
  if (!panel || !canvas || !state.data?.location_policy) {
    return;
  }

  const policy = state.data.location_policy;
  const points = locationMapPoints(policy);
  if (!window.L || points.length === 0) {
    panel.classList.add("map-unavailable");
    return;
  }

  if (activeLocationMap) {
    activeLocationMap.remove();
    activeLocationMap = null;
  }

  canvas.replaceChildren();
  const map = window.L.map(canvas, {
    attributionControl: true,
    scrollWheelZoom: false,
    zoomControl: true,
  });
  map.setView([31.52, 34.63], 9);

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const overlayBounds = addLocationAreaOverlays(map, policy);
  const hasActiveRegionOverlay = activeRegionOptions(policy).length > 0;
  const hasRadiusOverlay = selectedRadiusKm() > 0;
  const markerLayer = window.L.markerClusterGroup
    ? window.L.markerClusterGroup({
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        disableClusteringAtZoom: hasRadiusOverlay ? 9 : 12,
        maxClusterRadius: hasRadiusOverlay ? 22 : 34,
        iconCreateFunction(cluster) {
          const childMarkers = cluster.getAllChildMarkers();
          const states = childMarkers.map((marker) => marker.options.scanState);
          const activeStates = new Set(["scanned", "radius"]);
          const clusterState = states.every((stateName) => stateName === "scanned")
            ? "scanned"
            : states.every((stateName) => stateName === "radius")
              ? "radius"
              : states.every((stateName) => activeStates.has(stateName))
                ? "scanned"
            : states.every((stateName) => stateName === "not-scanned")
              ? "not-scanned"
              : "mixed";
          const radiusClass = childMarkers.some((marker) => marker.options.withinRadius) ? " in-radius" : "";
          return window.L.divIcon({
            html: `<span>${cluster.getChildCount()}</span>`,
            className: `location-marker-cluster ${clusterState}${radiusClass}`,
            iconSize: window.L.point(38, 38),
          });
        },
      })
    : window.L.layerGroup();

  points.forEach((point) => {
    const pointClass = mapPointClass(point);
    const marker = window.L.marker([Number(point.lat), Number(point.lng)], {
      icon: markerIconForPoint(point),
      keyboard: false,
      scanState: pointClass,
      withinRadius: isPointWithinRadius(point, policy),
      title: `${point.label} - ${locationStatusText(point)}`,
    })
      .bindTooltip(markerTooltip(point), {
        className: "location-map-tooltip",
        direction: "top",
        offset: [0, -12],
        opacity: 0.96,
      })
      .bindPopup(markerPopup(point, interactionsDisabled), {
        className: "location-map-popup-shell",
        closeButton: true,
        minWidth: 170,
      });
    markerLayer.addLayer(marker);
  });

  markerLayer.addTo(map);
  map.fitBounds(overlayBounds, { padding: [28, 28], maxZoom: hasActiveRegionOverlay ? 8 : hasRadiusOverlay ? 10 : 11 });
  bindMapViewButtons(panel, map, policy);
  activeLocationMap = map;
  requestAnimationFrame(() => map.invalidateSize());
}

function scheduleLocationMapInit(interactionsDisabled = false) {
  if (locationMapInitHandle) {
    cancelAnimationFrame(locationMapInitHandle);
  }
  locationMapInitHandle = requestAnimationFrame(() => {
    initializeLocationMap(interactionsDisabled);
  });
}

function renderLocationMap(policy = {}, interactionsDisabled = false) {
  const points = locationMapPoints(policy);
  const scannedCount = points.filter((point) => isScannedLocation(point.key, point)).length;
  const radius = selectedRadiusKm();
  const radiusCount = radius ? points.filter((point) => isPointWithinRadius(point, policy)).length : 0;
  const nearbyCount = (policy.nearby_options || []).length;
  const localityCount = Number(policy.israel_localities_count || (policy.israel_localities || []).length || 0);
  const regionOptions = Array.isArray(policy.region_options) ? policy.region_options : [];
  const radiusOptions = Array.isArray(policy.radius_options_km) ? policy.radius_options_km : [25, 40, 60, 80, 100, 150];
  const disabled = interactionsDisabled ? " disabled" : "";
  const regionChips = regionOptions
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button type="button" class="region-chip${approved ? " approved" : ""}" data-location-action="toggle" data-location-key="${escapeHtml(
          option.key
        )}" aria-pressed="${approved ? "true" : "false"}"${disabled}>${escapeHtml(option.label)}</button>
      `;
    })
    .join("");
  const radiusOptionsHtml = [
    `<option value="0"${radius === 0 ? " selected" : ""}>ללא רדיוס</option>`,
    ...radiusOptions.map((value) => `<option value="${escapeHtml(value)}"${radius === Number(value) ? " selected" : ""}>${escapeHtml(value)} ק״מ</option>`),
  ].join("");

  return `
    <section class="location-map-panel" aria-label="מפת מיקומים">
      <div class="location-map-stage">
        <div class="map-canvas leaflet-map" data-location-map-canvas></div>
        <div class="map-fallback">
          <strong>המפה לא נטענה</strong>
          <span>רשימת המיקומים זמינה למטה.</span>
        </div>
      </div>
      <aside class="map-side" aria-label="מקרא מפה">
        <div class="map-toolbar" aria-label="תצוגת מפה">
          <button type="button" class="map-view-button active" data-map-view="sderot"${interactionsDisabled ? " disabled" : ""}>אזור שדרות</button>
          <button type="button" class="map-view-button" data-map-view="israel"${interactionsDisabled ? " disabled" : ""}>ישראל</button>
        </div>
        <div class="map-legend">
          <span><i class="legend-dot home"></i>קורן · שדרות</span>
          <span><i class="legend-dot scanned"></i>בסריקה</span>
          <span><i class="legend-dot radius"></i>בתוך רדיוס</span>
          <span><i class="legend-dot not-scanned"></i>לא בסריקה</span>
        </div>
        <div class="map-region-panel" aria-label="אזורי סריקה">
          ${regionChips}
        </div>
        <label class="map-radius-control">
          <span>רדיוס משדרות</span>
          <select data-location-action="radius"${disabled}>
            ${radiusOptionsHtml}
          </select>
        </label>
        <div class="map-summary-grid" aria-label="סיכום מיקומים במפה">
          <span><strong>${escapeHtml(scannedCount)}</strong><small>במדיניות הסריקה</small></span>
          <span><strong>${escapeHtml(points.length - scannedCount)}</strong><small>לא מסומנים</small></span>
          ${
            radius
              ? `<span><strong>${escapeHtml(radiusCount)}</strong><small>בתוך ${escapeHtml(radius)} ק״מ משדרות</small></span>`
              : ""
          }
          <span><strong>${escapeHtml(nearbyCount)}</strong><small>יישובים סביב שדרות</small></span>
          <span><strong>${escapeHtml(localityCount)}</strong><small>יישובים במאגר</small></span>
        </div>
      </aside>
    </section>
  `;
}

function renderLocationPolicy() {
  if (!els.locationPolicy || !state.data) {
    return;
  }

  const policy = state.data.location_policy || {};
  const defaultApproved = Array.isArray(policy.default_approved) ? policy.default_approved : [];
  const userApprovable = Array.isArray(policy.user_approvable) ? policy.user_approvable : [];
  const nearbyOptions = Array.isArray(policy.nearby_options) ? policy.nearby_options : [];
  const regionOptions = Array.isArray(policy.region_options) ? policy.region_options : [];
  const knownKeys = new Set([...defaultApproved, ...userApprovable, ...nearbyOptions, ...regionOptions].map((option) => option.key));
  const customApproved = approvedLocationEntries().filter((entry) => !knownKeys.has(entry.key));
  const syncBlockedMessage = syncWriteBlockMessage();
  const disabled = syncBlockedMessage ? " disabled" : "";

  const defaultChips = defaultApproved
    .map(
      (option) => `
        <span class="city-chip locked" title="מאושר כברירת מחדל">
          ${escapeHtml(option.label)}
        </span>
      `
    )
    .join("");

  const optionalChips = userApprovable
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button
          type="button"
          class="city-chip toggle${approved ? " approved" : ""}"
          data-location-action="toggle"
          data-location-key="${escapeHtml(option.key)}"
          aria-pressed="${approved ? "true" : "false"}"
          ${disabled}
        >
          ${escapeHtml(option.label)}
        </button>
      `;
    })
    .join("");

  const nearbyChips = nearbyOptions
    .map((option) => {
      const approved = isLocationApproved(option.key);
      return `
        <button
          type="button"
          class="city-chip toggle nearby${approved ? " approved" : ""}"
          data-location-action="toggle"
          data-location-key="${escapeHtml(option.key)}"
          aria-pressed="${approved ? "true" : "false"}"
          ${disabled}
        >
          ${escapeHtml(option.label)}
        </button>
      `;
    })
    .join("");

  const customChips = customApproved
    .map(
      (entry) => `
        <button
          type="button"
          class="city-chip toggle approved custom"
          data-location-action="toggle"
          data-location-key="${escapeHtml(entry.key)}"
          aria-pressed="true"
          ${disabled}
        >
          ${escapeHtml(entry.label)}
        </button>
      `
    )
    .join("");

  els.locationPolicy.innerHTML = `
    <div class="location-head">
      <div>
        <p class="eyebrow">מדיניות מיקום</p>
        <h2>ערי חיפוש מאושרות</h2>
      </div>
      <span class="state-pill local">${escapeHtml(defaultApproved.length + approvedLocationEntries().length)} מיקומים מאושרים</span>
    </div>
    ${renderLocationMap(policy, Boolean(syncBlockedMessage))}
    <div class="location-groups">
      <section class="location-group">
        <h3>ברירת מחדל</h3>
        <div class="city-grid">${defaultChips}</div>
      </section>
      <section class="location-group">
        <h3>בחירה</h3>
        <div class="city-grid">${optionalChips}</div>
      </section>
      <section class="location-group wide">
        <h3>יישובים וקיבוצים סביב שדרות</h3>
        <div class="city-grid">${nearbyChips}${customChips}</div>
      </section>
      <form class="custom-city-form" data-location-action="custom">
        <label class="search-box" for="customCityInput">
          <span>עיר נוספת</span>
          <input id="customCityInput" name="city" type="text" autocomplete="off" maxlength="80" />
        </label>
        <button type="submit" class="manual-button"${disabled}>הוסף</button>
      </form>
    </div>
    ${syncBlockedMessage ? `<section class="sync-warning" role="alert">${escapeHtml(syncBlockedMessage)}</section>` : ""}
  `;
  scheduleLocationMapInit(Boolean(syncBlockedMessage));
}

function renderInsights() {
  if (!els.insights) {
    return;
  }

  const insights = state.data.insights || {};
  const actions = Array.isArray(insights.next_actions) ? insights.next_actions : [];
  const blockers = Array.isArray(insights.blocker_counts) ? insights.blocker_counts : [];
  const snapshot = insights.snapshot || {};
  const safeAuto = Number(snapshot.safe_auto_submit_now || 0);
  const conversionSummary = renderConversionSummary(state.data.conversion || {});

  if (!actions.length && !blockers.length && !conversionSummary) {
    els.insights.innerHTML = "";
    return;
  }

  const statusLine =
    safeAuto > 0
      ? `${safeAuto} משרות זמינות להגשה אוטומטית`
      : "אין כרגע משרה בטוחה להגשה אוטומטית";

  els.insights.innerHTML = `
    <div class="insights-head">
      <div>
        <p class="eyebrow">השלב הבא</p>
        <h2>${escapeHtml(statusLine)}</h2>
      </div>
      <span class="state-pill local">${escapeHtml(snapshot.high_score_actionable || 0)} משרות דורשות פעולה</span>
    </div>
    ${conversionSummary}
    <div class="insight-grid">
      ${actions
        .map(
          (action) => `
            <article class="insight-card">
              <h3>${escapeHtml(action.title)}</h3>
              <p>${escapeHtml(action.impact)}</p>
              <p class="insight-recommendation">${escapeHtml(action.recommendation)}</p>
              ${renderInsightJobs(action.jobs || [])}
            </article>
          `
        )
        .join("")}
    </div>
    <div class="blocker-strip" aria-label="חסמים מרכזיים">
      ${blockers
        .slice(0, 8)
        .map(
          (blocker) => `
            <span class="blocker-pill" title="${escapeHtml(blocker.recommendation || "")}">
              ${escapeHtml(blocker.label)} · ${escapeHtml(blocker.count)}
            </span>
          `
        )
        .join("")}
    </div>
  `;
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
  if (source === "alerts_only") {
    return "נשמר בדפדפן ונשלחה התראת Telegram; אחסון מרכזי לא זמין כרגע.";
  }
  if (source === "local") {
    return "נשמר בדפדפן המקומי.";
  }
  if (state.sync.enabled) {
    return "ממתין לאישור סנכרון.";
  }
  return SYNC_UNAVAILABLE_MESSAGE;
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
  const syncBlockedMessage = syncWriteBlockMessage();
  const manualDisabled = syncBlockedMessage ? ` disabled aria-disabled="true" title="${escapeHtml(syncBlockedMessage)}"` : "";
  const syncWarning = syncBlockedMessage ? `<section class="sync-warning" role="alert">${escapeHtml(syncBlockedMessage)}</section>` : "";
  const manualFact = manualTimestamp
    ? `<span class="fact manual-fact">הוגש ידנית: <span class="timestamp" dir="ltr">${escapeHtml(manualTimestamp)}</span></span>`
    : "";
  const manualRejectFact = manualRejectedAt
    ? `<span class="fact manual-fact">נפסל ידנית: <span class="timestamp" dir="ltr">${escapeHtml(manualRejectedAt)}</span></span>`
    : "";
  const manualAction = manualRejectedAt
    ? ""
    : job.manual_submitted_at
    ? `<button type="button" class="manual-button secondary" data-manual-action="clear" data-key="${escapeHtml(job.key)}"${manualDisabled}>בטל סימון ידני</button>`
    : `<button type="button" class="manual-button" data-manual-action="mark" data-key="${escapeHtml(job.key)}"${manualDisabled}>סמן כהוגש ידנית</button>`;
  const manualRejectAction = manualRejectedAt
    ? `<button type="button" class="manual-button danger-secondary" data-manual-action="clear-reject" data-key="${escapeHtml(job.key)}"${manualDisabled}>בטל פסילה ידנית</button>`
    : [PENDING_STATUS, MANUAL_REQUIRED_STATUS].includes(originalStatus) && !manualTimestamp
    ? `<button type="button" class="manual-button danger" data-manual-action="reject" data-key="${escapeHtml(job.key)}"${manualDisabled}>סמן כנפסל</button>`
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

      ${syncWarning}
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

  let label = "סנכרון לא זמין";
  let variant = "sync-error";
  if (state.sync.enabled && !state.sync.lastError) {
    if (state.sync.saving || !state.sync.loaded) {
      label = state.sync.saving ? "מסנכרן" : "בודק סנכרון";
      variant = "syncing";
    } else if (syncAlertsOnly()) {
      label = "התראות בלבד";
      variant = "sync-alerts";
    } else {
      label = "מסונכרן לענן";
      variant = "synced";
    }
  }
  els.syncStatus.textContent = label;
  els.syncStatus.className = `state-pill ${variant}`;
  els.syncStatus.title = syncAlertsOnly() ? SYNC_ALERTS_ONLY_MESSAGE : syncWriteBlockMessage() || "הסנכרון זמין.";
}

function render() {
  if (!state.data) {
    return;
  }
  renderChrome();
  renderMetrics();
  renderInsights();
  renderLocationPolicy();
  renderJobs();
  renderDetails();
}

els.insights?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-insight-key]");
  if (!button) {
    return;
  }
  state.selectedKey = button.dataset.insightKey;
  const job = selectedJob();
  if (job) {
    openJobModal(job);
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

  void pushLocationPreference(option, !isLocationApproved(key));
});

els.locationPolicy?.addEventListener("keydown", (event) => {
  if (!["Enter", " "].includes(event.key)) {
    return;
  }
  const button = event.target.closest("[data-location-action='toggle']");
  if (!button) {
    return;
  }
  event.preventDefault();
  const key = button.dataset.locationKey;
  const option = locationOptionByKey(key);
  if (!option) {
    showToast("לא נמצאו פרטי עיר לעדכון");
    return;
  }
  void pushLocationPreference(option, !isLocationApproved(key));
});

els.locationPolicy?.addEventListener("change", (event) => {
  const select = event.target.closest("[data-location-action='radius']");
  if (!select) {
    return;
  }
  void pushLocationRadius(select.value);
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
  void pushLocationPreference({ key, label, terms: [label] }, true);
});

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
