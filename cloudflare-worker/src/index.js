const STATE_KEY = "manual_submissions";
const DEFAULT_STATE_NAME = "default";
const MAX_FIELD_LENGTH = 1200;
const MAX_NOTE_LENGTH = 500;
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
  return new Response(null, {
    status: 204,
    headers: CORS_HEADERS,
  });
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

function nowString() {
  const formatter = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Jerusalem",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return formatter.format(new Date()).replace("T", " ");
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

function auditEntry(params, action, submittedAt, duplicate) {
  return {
    created_at: nowString(),
    event_id: clean(params.event_id),
    action,
    duplicate,
    job_key: clean(params.job_key),
    status: action === "markManualSubmitted" ? "הוגש ידנית" : "",
    manual_submitted_at: submittedAt,
    company: clean(params.company),
    title: clean(params.title),
    location: clean(params.location),
    link: clean(params.link, 2000),
    score: clean(params.score, 20),
    requirements: clean(params.requirements),
    fit: clean(params.fit),
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

    if (action === "listUpdates") {
      return respond(request, await this.statePayload());
    }
    if (action === "markManualSubmitted") {
      return respond(request, await this.markManualSubmitted(params));
    }
    if (action === "clearManualSubmitted") {
      return respond(request, await this.clearManualSubmitted(params));
    }
    if (action === "health") {
      return respond(request, { ok: true, service: "job-searcher-live-api", generated_at: nowString() });
    }

    return respond(request, { ok: false, error: "unknown_action", action }, 400);
  }

  async statePayload(extra = {}) {
    const manualSubmissions = (await this.ctx.storage.get(STATE_KEY)) || {};
    return {
      ok: true,
      generated_at: nowString(),
      manual_submissions: manualSubmissions,
      ...extra,
    };
  }

  async markManualSubmitted(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const submittedAt = clean(params.manual_submitted_at, 30) || nowString();
    const eventId = clean(params.event_id, 220) || crypto.randomUUID();
    let duplicate = false;

    await this.ctx.storage.transaction(async (txn) => {
      const eventKey = `event:${eventId}`;
      duplicate = Boolean(await txn.get(eventKey));
      if (duplicate) {
        return;
      }

      const manualSubmissions = (await txn.get(STATE_KEY)) || {};
      manualSubmissions[jobKey] = publicEntry(params, submittedAt, nowString());
      await txn.put(STATE_KEY, manualSubmissions);
      await txn.put(eventKey, auditEntry(params, "markManualSubmitted", submittedAt, false));
    });

    let telegram = { sent: false, reason: duplicate ? "duplicate_event" : "not_attempted" };
    if (!duplicate) {
      telegram = await sendTelegram(this.env, params, submittedAt).catch((error) => ({
        sent: false,
        reason: "telegram_error",
        message: error.message,
      }));
    }

    return this.statePayload({ duplicate, telegram });
  }

  async clearManualSubmitted(params) {
    const jobKey = clean(params.job_key, 2000);
    if (!jobKey) {
      return { ok: false, error: "missing_job_key" };
    }

    const eventId = clean(params.event_id, 220) || crypto.randomUUID();
    let duplicate = false;

    await this.ctx.storage.transaction(async (txn) => {
      const eventKey = `event:${eventId}`;
      duplicate = Boolean(await txn.get(eventKey));
      if (duplicate) {
        return;
      }

      const manualSubmissions = (await txn.get(STATE_KEY)) || {};
      delete manualSubmissions[jobKey];
      await txn.put(STATE_KEY, manualSubmissions);
      await txn.put(eventKey, auditEntry(params, "clearManualSubmitted", "", false));
    });

    return this.statePayload({ duplicate, telegram: { sent: false, reason: "clear_action" } });
  }
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return optionsResponse();
    }

    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      const payload = { ok: true, service: "job-searcher-live-api", generated_at: nowString() };
      return respond(request, payload);
    }

    const stateName = env.STATE_NAME || DEFAULT_STATE_NAME;
    const id = env.JOB_STATE.idFromName(stateName);
    const stub = env.JOB_STATE.get(id);
    return stub.fetch(request);
  },
};
