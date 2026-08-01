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

console.log(JSON.stringify({ ok: true }));
