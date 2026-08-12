const STATE_KEY = "job_searcher_sync_state_v2";
const LEGACY_MANUAL_SUBMISSIONS_KEY = "manual_submissions";
const DEFAULT_STATE_NAME = "default";
const MAX_FIELD_LENGTH = 1200;
const MAX_NOTE_LENGTH = 500;
const MAX_LOCATION_TERMS = 12;
const DEFAULT_REJECTION_NOTE = "נפסל בבחירה ידנית";
const BROKEN_TEXT_PATTERN = /\?{3,}/;
const ENCODING_FALLBACK_TEXT = "טקסט לא זמין בגלל בעיית קידוד במקור";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function javascriptResponse(body, status = 200) {
  return new Response(body, {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function optionsResponse() {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

function safeCallbackName(callback) {
  return /^[A-Za-z_$][0-9A-Za-z_$]*(\.[A-Za-z_$][0-9A-Za-z_$]*)*$/.test(callback || "");
}

function respond(request, payload, status = 200) {
  const callback = new URL(request.url).searchParams.get("callback") || "";
  if (safeCallbackName(callback)) {
    return javascriptResponse(`${callback}(${JSON.stringify(payload)});`, status);
  }
  return jsonResponse(payload, status);
}

function nowString(date = new Date()) {
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Jerusalem",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return formatter.format(date).replace("T", " ");
}

function clean(value, maxLength = MAX_FIELD_LENGTH) {
  const text = String(value || "").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
}

function hasBrokenText(value) {
  return BROKEN_TEXT_PATTERN.test(String(value || ""));
}

function safeTelegramText(value, fallback = ENCODING_FALLBACK_TEXT, maxLength = MAX_FIELD_LENGTH) {
  const text = clean(value, maxLength);
  return hasBrokenText(text) ? fallback : text;
}

function parseBool(value) {
  if (typeof value === "boolean") {
    return value;
  }
  return ["1", "true", "yes", "y", "כן", "approved"].includes(String(value || "").trim().toLowerCase());
}

function parseRadiusKm(value) {
  const radius = Number.parseInt(String(value || "").trim(), 10);
  if (!Number.isFinite(radius)) {
    return 0;
  }
  return Math.max(0, Math.min(radius, 250));
}

function cleanTerms(value) {
  const rawTerms = Array.isArray(value) ? value : String(value || "").split("|");
  const terms = [];
  rawTerms.forEach((term) => {
    const cleanTerm = clean(term, 80);
    if (cleanTerm && !terms.some((item) => item.toLowerCase() === cleanTerm.toLowerCase())) {
      terms.push(cleanTerm);
    }
  });
  return terms.slice(0, MAX_LOCATION_TERMS);
}

function normalizeLocationPreferences(value) {
  const preferences = value && typeof value === "object" ? value : {};
  const rawApproved = preferences.approved_locations && typeof preferences.approved_locations === "object" ? preferences.approved_locations : {};
  const approved = {};
  const entries = Array.isArray(rawApproved) ? rawApproved.map((entry) => [entry?.key, entry]) : Object.entries(rawApproved);
  entries.forEach(([rawKey, entry]) => {
    if (entry && typeof entry === "object") {
      const key = clean(entry.key || rawKey, 120);
      const label = clean(entry.label || entry.city_label || key, 120);
      if (key && label) {
        approved[key] = {
          key,
          label,
          terms: cleanTerms(entry.terms || entry.city_terms || [label, key]),
          approved: entry.approved === undefined ? true : parseBool(entry.approved),
          updatedAt: clean(entry.updatedAt || entry.updated_at, 30),
          source: clean(entry.source || "remote", 40),
        };
      }
    }
  });
  return {
    approved_locations: approved,
    radius_km: parseRadiusKm(preferences.radius_km ?? preferences.radiusKm),
  };
}

function defaultState() {
  return {
    ok: true,
    generated_at: new Date().toISOString(),
    manual_submissions: {},
    manual_rejections: {},
    location_preferences: normalizeLocationPreferences({}),
    events: [],
  };
}

function normalizeState(state) {
  const base = defaultState();
  if (!state || typeof state !== "object") {
    return base;
  }
  return {
    ok: true,
    generated_at: state.generated_at || base.generated_at,
    manual_submissions: state.manual_submissions && typeof state.manual_submissions === "object" ? state.manual_submissions : {},
    manual_rejections: state.manual_rejections && typeof state.manual_rejections === "object" ? state.manual_rejections : {},
    location_preferences: normalizeLocationPreferences(state.location_preferences),
    events: Array.isArray(state.events) ? state.events : [],
  };
}

async function readState(storage) {
  const state = await storage.get(STATE_KEY);
  if (state) {
    return normalizeState(state);
  }
  const legacySubmissions = await storage.get(LEGACY_MANUAL_SUBMISSIONS_KEY);
  const nextState = defaultState();
  if (legacySubmissions && typeof legacySubmissions === "object") {
    nextState.manual_submissions = legacySubmissions;
  }
  return nextState;
}

async function writeState(storage, state) {
  const nextState = normalizeState({ ...state, generated_at: new Date().toISOString() });
  await storage.put(STATE_KEY, nextState);
  return nextState;
}

async function requestParams(request) {
  const url = new URL(request.url);
  const params = Object.fromEntries(url.searchParams.entries());
  if (request.method !== "POST") {
    return params;
  }

  const contentType = request.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await request.json().catch(() => ({}));
    return { ...params, ...body };
  }
  if (contentType.includes("application/x-www-form-urlencoded") || contentType.includes("multipart/form-data")) {
    const form = await request.formData();
    const formParams = {};
    form.forEach((value, key) => {
      formParams[key] = String(value);
    });
    return { ...params, ...formParams };
  }

  return params;
}

function publicEntry(params, submittedAt, updatedAt) {
  return {
    submittedAt,
    updatedAt,
    note: clean(params.note, MAX_NOTE_LENGTH),
    source: "remote",
  };
}

function publicRejectionEntry(params, rejectedAt, updatedAt) {
  return {
    rejectedAt,
    updatedAt,
    note: clean(params.note || DEFAULT_REJECTION_NOTE, MAX_NOTE_LENGTH),
    source: "remote",
  };
}

function publicLocationPreferenceEntry(params, updatedAt) {
  const key = clean(params.city_key, 120);
  const label = clean(params.city_label, 120);
  return {
    key,
    label,
    terms: cleanTerms(params.city_terms || [label, key]),
    approved: parseBool(params.approved),
    updatedAt,
    source: "remote",
  };
}

function eventEntry(params, duplicate) {
  return {
    created_at: nowString(),
    event_id: clean(params.event_id, 220),
    action: clean(params.action, 80),
    duplicate,
    job_key: clean(params.job_key, 2000),
    company: clean(params.company),
    title: clean(params.title),
    location: clean(params.location),
    link: clean(params.link, 2000),
    score: clean(params.score, 20),
    city_key: clean(params.city_key, 120),
    city_label: clean(params.city_label, 120),
    approved: clean(params.approved, 20),
    radius_km: clean(params.radius_km, 20),
    note: clean(params.note, MAX_NOTE_LENGTH),
    user_agent: clean(params.user_agent, 500),
  };
}

async function sendTelegram(env, params, submittedAt) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    return { sent: false, reason: "missing_telegram_config" };
  }

  const company = safeTelegramText(params.company, "חברה לא זמינה בגלל בעיית קידוד במקור");
  const title = safeTelegramText(params.title, "משרה לא זמינה בגלל בעיית קידוד במקור");
  const location = safeTelegramText(params.location, "מיקום לא זמין בגלל בעיית קידוד במקור");
  const link = safeTelegramText(params.link, "קישור לא זמין בגלל בעיית קידוד במקור", 2000);
  const score = safeTelegramText(params.score, "", 20);
  const requirements = safeTelegramText(params.requirements, "דרישות לא זמינות בגלל בעיית קידוד במקור");
  const fit = safeTelegramText(params.fit, "סיבות התאמה לא זמינות בגלל בעיית קידוד במקור");
  const text = [
    "הוגשה ידנית בדשבורד",
    `תאריך ושעה: ${submittedAt}`,
    `חברה: ${company}`,
    `משרה: ${title}`,
    `מיקום: ${location}`,
    `ציון התאמה: ${score}/100`,
    `קישור: ${link}`,
    "",
    "דרישות מרכזיות:",
    requirements || "לא נשלחו דרישות מהדשבורד",
    "",
    "סיבות התאמה:",
    fit || "לא נשלחו סיבות התאמה מהדשבורד",
    "",
    "מידע כללי על החברה:",
    `${company}${location ? " | " + location : ""}`,
  ].join("\n");

  if (hasBrokenText(text)) {
    return { sent: false, reason: "telegram_text_contains_replacement_question_marks" };
  }

  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text,
      disable_web_page_preview: false,
    }),
  });

  return {
    sent: response.ok,
    status: response.status,
  };
}

function statePayload(state, extra = {}) {
  return {
    ok: true,
    generated_at: state.generated_at,
    manual_submissions: state.manual_submissions,
    manual_rejections: state.manual_rejections,
    location_preferences: state.location_preferences,
    events: state.events,
    ...extra,
  };
}

export class JobState {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    if (request.method === "OPTIONS") {
      return optionsResponse();
    }

    const params = await requestParams(request);
    const action = clean(params.action || "listUpdates", 80);

    if (action === "health") {
      return respond(request, {
        ok: true,
        service: "job-searcher-live-api",
        storage: "durable_object",
        generated_at: nowString(),
      });
    }
    if (action === "listUpdates") {
      return respond(request, statePayload(await readState(this.ctx.storage)));
    }
    if (action === "markManualSubmitted") {
      return respond(request, await this.markManualSubmitted(params));
    }
    if (action === "clearManualSubmitted") {
      return respond(request, await this.clearManualSubmitted(params));
    }
    if (action === "markManualRejected") {
      return respond(request, await this.markManualRejected(params));
    }
    if (action === "clearManualRejected") {
      return respond(request, await this.clearManualRejected(params));
    }
    if (action === "setLocationPreference") {
      return respond(request, await this.setLocationPreference(params));
    }
    if (action === "setLocationRadius") {
      return respond(request, await this.setLocationRadius(params));
    }

    return respond(request, { ok: false, error: "unknown_action", action }, 400);
  }

  async mutate(params, mutateState) {
    const action = clean(params.action, 80);
    const eventId = clean(params.event_id, 220) || `${action}:${clean(params.job_key || params.city_key, 2000)}:${nowString()}`;
    let duplicate = false;
    let nextState = defaultState();
    let mutationResult = {};

    await this.ctx.storage.transaction(async (txn) => {
      const state = await readState(txn);
      duplicate = state.events.some((event) => event && event.event_id === eventId);
      if (!duplicate) {
        mutationResult = mutateState(state, eventId) || {};
        state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
        nextState = await writeState(txn, state);
      } else {
        nextState = state;
      }
    });

    return { state: nextState, duplicate, mutationResult };
  }

  async markManualSubmitted(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const submittedAt = clean(params.manual_submitted_at, 30) || nowString();
    const { state, duplicate } = await this.mutate({ ...params, action: "markManualSubmitted" }, (draft) => {
      draft.manual_submissions[jobKey] = publicEntry(params, submittedAt, nowString());
      delete draft.manual_rejections[jobKey];
    });

    let telegram = { sent: false, reason: duplicate ? "duplicate_event" : "not_attempted" };
    if (!duplicate) {
      telegram = await sendTelegram(this.env, params, submittedAt).catch((error) => ({
        sent: false,
        reason: "telegram_error",
        message: error.message,
      }));
    }

    return statePayload(state, { duplicate, telegram });
  }

  async clearManualSubmitted(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const { state, duplicate } = await this.mutate({ ...params, action: "clearManualSubmitted" }, (draft) => {
      delete draft.manual_submissions[jobKey];
    });
    return statePayload(state, { duplicate, telegram: { sent: false, reason: duplicate ? "duplicate_event" : "clear_action" } });
  }

  async markManualRejected(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const rejectedAt = clean(params.manual_rejected_at, 30) || nowString();
    const { state, duplicate } = await this.mutate({ ...params, action: "markManualRejected" }, (draft) => {
      draft.manual_rejections[jobKey] = publicRejectionEntry(params, rejectedAt, nowString());
      delete draft.manual_submissions[jobKey];
    });
    return statePayload(state, { duplicate, telegram: { sent: false, reason: duplicate ? "duplicate_event" : "manual_reject_action" } });
  }

  async clearManualRejected(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const { state, duplicate } = await this.mutate({ ...params, action: "clearManualRejected" }, (draft) => {
      delete draft.manual_rejections[jobKey];
    });
    return statePayload(state, { duplicate, telegram: { sent: false, reason: duplicate ? "duplicate_event" : "clear_reject_action" } });
  }

  async setLocationPreference(params) {
    const cityKey = clean(params.city_key, 120);
    if (!cityKey) {
      return { ok: false, error: "missing_city_key" };
    }

    const entry = publicLocationPreferenceEntry(params, nowString());
    if (!entry.label) {
      return { ok: false, error: "missing_city_label" };
    }

    const { state, duplicate } = await this.mutate({ ...params, action: "setLocationPreference" }, (draft) => {
      if (entry.approved) {
        draft.location_preferences.approved_locations[cityKey] = entry;
      } else {
        delete draft.location_preferences.approved_locations[cityKey];
      }
    });
    return statePayload(state, { duplicate, telegram: { sent: false, reason: duplicate ? "duplicate_event" : "location_preference_action" } });
  }

  async setLocationRadius(params) {
    const radiusKm = parseRadiusKm(params.radius_km);
    const { state, duplicate } = await this.mutate({ ...params, action: "setLocationRadius" }, (draft) => {
      draft.location_preferences.radius_km = radiusKm;
      draft.location_preferences.radius_updated_at = nowString();
    });
    return statePayload(state, { duplicate, telegram: { sent: false, reason: duplicate ? "duplicate_event" : "location_radius_action" } });
  }
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return optionsResponse();
    }

    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return respond(request, {
        ok: true,
        service: "job-searcher-live-api",
        storage: "durable_object",
        generated_at: nowString(),
      });
    }

    const stateName = env.STATE_NAME || DEFAULT_STATE_NAME;
    const id = env.JOB_STATE.idFromName(stateName);
    const stub = env.JOB_STATE.get(id);
    return stub.fetch(request);
  },
};
