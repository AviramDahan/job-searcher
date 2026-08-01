import assert from "node:assert/strict";
import { handleSyncAction } from "../lib/sync-api.js";

const calls = [];
let remoteState = {
  ok: true,
  generated_at: "2026-08-02T00:00:00.000Z",
  manual_submissions: {},
  events: [],
};

globalThis.fetch = async (url, options = {}) => {
  calls.push({ url: String(url), options });
  if (String(url).startsWith("https://api.telegram.org/")) {
    return new Response(JSON.stringify({ ok: true, result: { message_id: 123 } }), { status: 200 });
  }
  if (options.method === "PUT") {
    remoteState = JSON.parse(options.body);
    return new Response(JSON.stringify(remoteState), { status: 200 });
  }
  return new Response(JSON.stringify(remoteState), { status: 200 });
};

const env = {
  JSONBLOB_ENDPOINT: "https://jsonblob.example/state",
  TELEGRAM_BOT_TOKEN: "test-token",
  TELEGRAM_CHAT_ID: "-1001",
};

const mark = await handleSyncAction(
  {
    action: "markManualSubmitted",
    event_id: "event-1",
    job_key: "job-1",
    company: "Acme",
    title: "Buyer",
    location: "Sderot",
    link: "https://example.test/job-1",
    score: "90",
    manual_submitted_at: "2026-08-02 08:00",
    requirements: "Excel, suppliers",
    fit: "Procurement experience",
  },
  env
);

assert.equal(mark.ok, true);
assert.equal(mark.telegram.sent, true);
assert.equal(mark.manual_submissions["job-1"].submittedAt, "2026-08-02 08:00");
assert.equal(calls.filter((call) => call.url.startsWith("https://api.telegram.org/")).length, 1);

const duplicate = await handleSyncAction(
  {
    action: "markManualSubmitted",
    event_id: "event-1",
    job_key: "job-1",
    manual_submitted_at: "2026-08-02 09:00",
  },
  env
);

assert.equal(duplicate.duplicate, true);
assert.equal(duplicate.manual_submissions["job-1"].submittedAt, "2026-08-02 08:00");
assert.equal(calls.filter((call) => call.url.startsWith("https://api.telegram.org/")).length, 1);

const clear = await handleSyncAction(
  {
    action: "clearManualSubmitted",
    event_id: "event-2",
    job_key: "job-1",
  },
  env
);

assert.equal(clear.ok, true);
assert.equal(clear.manual_submissions["job-1"], undefined);

console.log(JSON.stringify({ ok: true }));
