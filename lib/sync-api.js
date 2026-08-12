const DEFAULT_JSONBLOB_ENDPOINT = "https://jsonblob.com/api/jsonBlob/019fef77-25db-7834-aa32-c48f4b824c74";
const MAX_FIELD_LENGTH = 1200;
const MAX_NOTE_LENGTH = 500;
const MAX_LOCATION_TERMS = 12;
const BROKEN_TEXT_PATTERN = /\?{3,}/;
const ENCODING_FALLBACK_TEXT = "טקסט לא זמין בגלל בעיית קידוד במקור";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

export function nowString(date = new Date()) {
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
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function hasBrokenText(value) {
  return BROKEN_TEXT_PATTERN.test(String(value || ""));
}

function safeTelegramText(value, fallback = ENCODING_FALLBACK_TEXT, maxLength = MAX_FIELD_LENGTH) {
  const text = clean(value, maxLength);
  return hasBrokenText(text) ? fallback : text;
}

function publicEntry(params, submittedAt, updatedAt, source = "remote") {
  return {
    submittedAt,
    updatedAt,
    note: clean(params.note, MAX_NOTE_LENGTH),
    source,
  };
}

function publicRejectionEntry(params, rejectedAt, updatedAt, source = "remote") {
  return {
    rejectedAt,
    updatedAt,
    note: clean(params.note || "נפסל בבחירה ידנית", MAX_NOTE_LENGTH),
    source,
  };
}

function parseBool(value) {
  if (typeof value === "boolean") {
    return value;
  }
  return ["1", "true", "yes", "y", "כן", "approved"].includes(String(value || "").trim().toLowerCase());
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

function publicLocationPreferenceEntry(params, updatedAt, source = "remote") {
  const key = clean(params.city_key, 120);
  const label = clean(params.city_label, 120);
  const terms = cleanTerms(params.city_terms || [label, key]);
  return {
    key,
    label,
    terms,
    approved: parseBool(params.approved),
    updatedAt,
    source,
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
  };
}

function parseRadiusKm(value) {
  const radius = Number.parseInt(String(value || "").trim(), 10);
  if (!Number.isFinite(radius)) {
    return 0;
  }
  return Math.max(0, Math.min(radius, 250));
}

function normalizeLocationPreferences(value) {
  const preferences = value && typeof value === "object" ? value : {};
  const rawApproved = preferences.approved_locations && typeof preferences.approved_locations === "object" ? preferences.approved_locations : {};
  const approved = {};
  const entries = Array.isArray(rawApproved) ? rawApproved.map((entry) => [entry?.key, entry]) : Object.entries(rawApproved);
  entries.forEach(([rawKey, entry]) => {
    if (entry && typeof entry === "object") {
      const key = entry.key || rawKey;
      if (key) {
        approved[key] = { ...entry, key };
      }
    }
  });
  return {
    approved_locations: approved,
    radius_km: parseRadiusKm(preferences.radius_km ?? preferences.radiusKm),
  };
}

function normalizeState(state) {
  return {
    ok: true,
    generated_at: state?.generated_at || new Date().toISOString(),
    manual_submissions: state?.manual_submissions && typeof state.manual_submissions === "object" ? state.manual_submissions : {},
    manual_rejections: state?.manual_rejections && typeof state.manual_rejections === "object" ? state.manual_rejections : {},
    location_preferences: normalizeLocationPreferences(state?.location_preferences),
    events: Array.isArray(state?.events) ? state.events : [],
  };
}

function unavailableState(error = "sync_storage_unavailable") {
  return {
    ok: false,
    error,
    generated_at: new Date().toISOString(),
    manual_submissions: {},
    manual_rejections: {},
    location_preferences: normalizeLocationPreferences({}),
    events: [],
  };
}

function transientState(reason = "remote_storage_unavailable") {
  return {
    ...normalizeState({}),
    storage_status: "alerts_only",
    storage_warning: reason,
  };
}

async function readRemoteState(endpoint) {
  const response = await fetch(endpoint, {
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`jsonblob_read_${response.status}`);
  }
  return normalizeState(await response.json());
}

async function writeRemoteState(endpoint, state) {
  const response = await fetch(endpoint, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      Accept: "application/json",
    },
    body: JSON.stringify(state),
  });
  if (!response.ok) {
    throw new Error(`jsonblob_write_${response.status}`);
  }
}

export async function sendTelegram(env, params, submittedAt) {
  const token = env.TELEGRAM_BOT_TOKEN || "";
  const chatId = env.TELEGRAM_CHAT_ID || "";
  if (!token || !chatId) {
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

  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: false,
    }),
  });

  return {
    sent: response.ok,
    status: response.status,
  };
}

export async function handleSyncAction(params, env = process.env) {
  const endpoint = env.JSONBLOB_ENDPOINT || DEFAULT_JSONBLOB_ENDPOINT;
  const action = clean(params.action || "listUpdates", 80);
  const storageDisabled = ["1", "true", "yes"].includes(String(env.SYNC_STORAGE_DISABLED || "").trim().toLowerCase());
  if (action === "health") {
    return {
      ok: true,
      service: "job-searcher-sites-sync",
      storage: storageDisabled ? "disabled" : "jsonblob",
      generated_at: new Date().toISOString(),
    };
  }
  if (storageDisabled) {
    return unavailableState("sync_storage_disabled");
  }
  let storageAvailable = true;
  let storageWarning = "";
  let state = normalizeState({});
  try {
    state = await readRemoteState(endpoint);
  } catch (error) {
    storageAvailable = false;
    storageWarning = error?.message || "remote_storage_unavailable";
    state = transientState(storageWarning);
  }

  if (action === "listUpdates") {
    return {
      ok: true,
      generated_at: state.generated_at,
      manual_submissions: state.manual_submissions,
      manual_rejections: state.manual_rejections,
      location_preferences: state.location_preferences,
      events: state.events,
      storage_status: storageAvailable ? "persistent" : "alerts_only",
      storage_warning: storageWarning,
    };
  }

  const cityKey = clean(params.city_key, 120);
  const jobKey = clean(params.job_key, 2000);
  if (action === "setLocationPreference") {
    if (!cityKey) {
      return { ok: false, error: "missing_city_key" };
    }
  } else if (action === "setLocationRadius") {
    // No job key is required for dashboard policy updates.
  } else if (!jobKey) {
    return { ok: false, error: "missing_job_key" };
  }

  const eventId = clean(params.event_id, 220) || `${action}:${jobKey || cityKey}:${nowString()}`;
  const duplicate = state.events.some((event) => event && event.event_id === eventId);
  let telegram = { sent: false, reason: "not_attempted" };

  if (!duplicate && action === "markManualSubmitted") {
    const submittedAt = clean(params.manual_submitted_at, 30) || nowString();
    state.manual_submissions[jobKey] = publicEntry(params, submittedAt, nowString(), storageAvailable ? "remote" : "alerts_only");
    delete state.manual_rejections[jobKey];
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = await sendTelegram(env, params, submittedAt).catch((error) => ({
      sent: false,
      reason: "telegram_error",
      message: error.message,
    }));
  } else if (!duplicate && action === "clearManualSubmitted") {
    delete state.manual_submissions[jobKey];
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = { sent: false, reason: "clear_action" };
  } else if (!duplicate && action === "markManualRejected") {
    const rejectedAt = clean(params.manual_rejected_at, 30) || nowString();
    state.manual_rejections[jobKey] = publicRejectionEntry(params, rejectedAt, nowString(), storageAvailable ? "remote" : "alerts_only");
    delete state.manual_submissions[jobKey];
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = { sent: false, reason: "manual_reject_action" };
  } else if (!duplicate && action === "clearManualRejected") {
    delete state.manual_rejections[jobKey];
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = { sent: false, reason: "clear_reject_action" };
  } else if (!duplicate && action === "setLocationPreference") {
    const entry = publicLocationPreferenceEntry(params, nowString(), storageAvailable ? "remote" : "alerts_only");
    if (!entry.label) {
      return { ok: false, error: "missing_city_label" };
    }
    if (entry.approved) {
      state.location_preferences.approved_locations[cityKey] = entry;
    } else {
      delete state.location_preferences.approved_locations[cityKey];
    }
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = { sent: false, reason: "location_preference_action" };
  } else if (!duplicate && action === "setLocationRadius") {
    state.location_preferences.radius_km = parseRadiusKm(params.radius_km);
    state.location_preferences.radius_updated_at = nowString();
    state.events.push(eventEntry({ ...params, event_id: eventId, action }, false));
    state.generated_at = new Date().toISOString();
    if (storageAvailable) {
      await writeRemoteState(endpoint, state);
    }
    telegram = { sent: false, reason: "location_radius_action" };
  } else if (duplicate) {
    telegram = { sent: false, reason: "duplicate_event" };
  } else {
    return { ok: false, error: "unknown_action", action };
  }

  return {
    ok: true,
    duplicate,
    telegram,
    generated_at: state.generated_at,
    manual_submissions: state.manual_submissions,
    manual_rejections: state.manual_rejections,
    location_preferences: state.location_preferences,
    events: state.events,
    storage_status: storageAvailable ? "persistent" : "alerts_only",
    storage_warning: storageWarning,
  };
}
