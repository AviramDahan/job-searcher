import worker, { JobState } from "./src/index.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  async get(key) {
    return this.values.get(key);
  }

  async put(key, value) {
    this.values.set(key, value);
  }

  async transaction(callback) {
    return callback(this);
  }
}

const env = {
  JOB_STATE: {
    idFromName: (name) => name,
    get: () => ({
      fetch: (request) => state.fetch(request),
    }),
  },
};

const storage = new MemoryStorage();
const state = new JobState({ storage }, {});

async function readJson(response) {
  return response.json();
}

const health = await readJson(await worker.fetch(new Request("https://api.test/health"), env));
if (!health.ok) {
  throw new Error("health failed");
}

const mark = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "markManualSubmitted",
        event_id: "event-1",
        job_key: "job-1",
        company: "Acme",
        title: "Buyer",
        link: "https://example.test/job-1",
        score: "90",
        manual_submitted_at: "2026-08-02 01:00",
      }),
    }),
    env
  )
);
if (!mark.ok || mark.manual_submissions["job-1"].submittedAt !== "2026-08-02 01:00") {
  throw new Error("mark failed");
}

const duplicate = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "markManualSubmitted",
        event_id: "event-1",
        job_key: "job-1",
        manual_submitted_at: "2026-08-02 02:00",
      }),
    }),
    env
  )
);
if (!duplicate.duplicate || duplicate.manual_submissions["job-1"].submittedAt !== "2026-08-02 01:00") {
  throw new Error("dedupe failed");
}

const clear = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "clearManualSubmitted",
        event_id: "event-2",
        job_key: "job-1",
      }),
    }),
    env
  )
);
if (!clear.ok || clear.manual_submissions["job-1"]) {
  throw new Error("clear failed");
}

const reject = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "markManualRejected",
        event_id: "event-3",
        job_key: "job-2",
        manual_rejected_at: "2026-08-02 03:00",
      }),
    }),
    env
  )
);
if (!reject.ok || reject.manual_rejections["job-2"].rejectedAt !== "2026-08-02 03:00") {
  throw new Error("manual rejection failed");
}

const clearReject = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "clearManualRejected",
        event_id: "event-4",
        job_key: "job-2",
      }),
    }),
    env
  )
);
if (!clearReject.ok || clearReject.manual_rejections["job-2"]) {
  throw new Error("clear manual rejection failed");
}

const location = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "setLocationPreference",
        event_id: "event-5",
        city_key: "city_ofakim",
        city_label: "אופקים",
        city_terms: "אופקים|ofakim",
        approved: "true",
      }),
    }),
    env
  )
);
if (!location.ok || !location.location_preferences.approved_locations.city_ofakim) {
  throw new Error("location preference failed");
}

const radius = await readJson(
  await worker.fetch(
    new Request("https://api.test/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "setLocationRadius",
        event_id: "event-6",
        radius_km: "40",
      }),
    }),
    env
  )
);
if (!radius.ok || radius.location_preferences.radius_km !== 40) {
  throw new Error("location radius failed");
}

const telegramCalls = [];
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, options = {}) => {
  telegramCalls.push({ url: String(url), body: JSON.parse(options.body || "{}") });
  return new Response(JSON.stringify({ ok: true, result: { message_id: 44 } }), {
    status: 200,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
try {
  const hebrewTelegram = await readJson(
    await new JobState({ storage: new MemoryStorage() }, { TELEGRAM_BOT_TOKEN: "token", TELEGRAM_CHAT_ID: "-1001" }).fetch(
      new Request("https://api.test/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "markManualSubmitted",
          event_id: "event-hebrew-1",
          job_key: "job-hebrew-1",
          company: "אסם נסטלה",
          title: "קניינית רכש",
          location: "שדרות",
          link: "https://example.test/hebrew",
          score: "91",
          requirements: "תואר ראשון, רכש, ספקים, Excel",
          fit: "ניסיון ברכש ועבודה מול ספקים",
          manual_submitted_at: "2026-08-12 10:00",
        }),
      })
    )
  );
  if (!hebrewTelegram.telegram.sent || telegramCalls.length !== 1) {
    throw new Error("telegram send was not attempted");
  }
  const sentText = telegramCalls[0].body.text;
  if (!sentText.includes("הוגשה ידנית") || /\?{3,}/.test(sentText)) {
    throw new Error("telegram text encoding guard failed");
  }
} finally {
  globalThis.fetch = originalFetch;
}

const list = await readJson(await worker.fetch(new Request("https://api.test/sync?action=listUpdates"), env));
if (!list.ok || list.events.length !== 6 || list.location_preferences.radius_km !== 40) {
  throw new Error("list updates failed");
}

console.log(JSON.stringify({ ok: true }));
