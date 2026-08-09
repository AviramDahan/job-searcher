import assert from "node:assert/strict";
import { handleSyncAction } from "../lib/sync-api.js";

const calls = [];
let remoteState = {
  ok: true,
  generated_at: "2026-08-02T00:00:00.000Z",
  manual_submissions: {},
  manual_rejections: {},
  location_preferences: { approved_locations: {} },
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

const reject = await handleSyncAction(
  {
    action: "markManualRejected",
    event_id: "event-3",
    job_key: "job-2",
    company: "Acme",
    title: "Procurement Coordinator",
    location: "Ashdod",
    link: "https://example.test/job-2",
    score: "84",
    manual_rejected_at: "2026-08-02 10:00",
    note: "נפסל בבחירה ידנית",
  },
  env
);

assert.equal(reject.ok, true);
assert.equal(reject.telegram.sent, false);
assert.equal(reject.telegram.reason, "manual_reject_action");
assert.equal(reject.manual_rejections["job-2"].rejectedAt, "2026-08-02 10:00");
assert.equal(reject.manual_submissions["job-2"], undefined);
assert.equal(calls.filter((call) => call.url.startsWith("https://api.telegram.org/")).length, 1);

const clearReject = await handleSyncAction(
  {
    action: "clearManualRejected",
    event_id: "event-4",
    job_key: "job-2",
  },
  env
);

assert.equal(clearReject.ok, true);
assert.equal(clearReject.manual_rejections["job-2"], undefined);

const approveLocation = await handleSyncAction(
  {
    action: "setLocationPreference",
    event_id: "event-5",
    city_key: "rehovot",
    city_label: "רחובות",
    city_terms: "רחובות|rehovot",
    approved: "true",
  },
  env
);

assert.equal(approveLocation.ok, true);
assert.equal(approveLocation.location_preferences.approved_locations.rehovot.approved, true);
assert.equal(approveLocation.location_preferences.approved_locations.rehovot.label, "רחובות");
assert.deepEqual(approveLocation.location_preferences.approved_locations.rehovot.terms, ["רחובות", "rehovot"]);

const rejectLocation = await handleSyncAction(
  {
    action: "setLocationPreference",
    event_id: "event-6",
    city_key: "rehovot",
    city_label: "רחובות",
    city_terms: "רחובות|rehovot",
    approved: "false",
  },
  env
);

assert.equal(rejectLocation.ok, true);
assert.equal(rejectLocation.location_preferences.approved_locations.rehovot.approved, false);

console.log(JSON.stringify({ ok: true }));
