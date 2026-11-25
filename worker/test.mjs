import assert from "node:assert/strict";
import worker from "./index.js";

class MemoryKV {
  constructor() {
    this.items = new Map();
    this.writes = 0;
  }
  async get(key) {
    return this.items.get(key)?.value ?? null;
  }
  async getWithMetadata(key) {
    const item = this.items.get(key);
    return { value: item?.value ?? null, metadata: item?.metadata ?? null };
  }
  async put(key, value, options = {}) {
    this.writes++;
    this.items.set(key, { value: String(value), metadata: options.metadata });
  }
  async delete(key) {
    this.items.delete(key);
  }
  async list({ prefix = "" } = {}) {
    const keys = [...this.items.keys()].filter((key) => key.startsWith(prefix)).sort().map((name) => ({ name, metadata: this.items.get(name).metadata }));
    return { keys, list_complete: true };
  }
}

const FORM = "https://forms.example.invalid/formResponse";
const calls = [];
let formStatus = 200;
globalThis.fetch = async (input, init = {}) => {
  const url = String(input);
  calls.push({ url, body: init.body ? String(init.body) : "" });
  if (url.includes("siteverify")) return new Response(JSON.stringify({ success: true }), { status: 200 });
  if (url === FORM) return new Response("ok", { status: formStatus });
  throw new Error(`unexpected fetch ${url}`);
};

const kv = new MemoryKV();
const env = { RELEASE_LIST: kv, TURNSTILE_SECRET: "secret", NOTIFY_FORM_URL: FORM, ASSETS: { fetch: () => new Response("asset") } };
const call = (host, path, body, target = env) =>
  worker.fetch(new Request(`https://${host}${path}`, {
    method: "POST",
    headers: { Origin: `https://${host}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }), target);
const signUp = async (host, email, extra = {}, target = env) => {
  const res = await call(host, "/api/notify", { email, consent: "yes", website: "", "cf-turnstile-response": "tok", ...extra }, target);
  return { status: res.status, body: await res.json() };
};
const save = async (ticket, seq, answers, final = false, host = "dogfighter.net") => {
  const res = await call(host, "/api/notify/answer", { ticket, seq, answers, final });
  return { status: res.status, body: await res.json() };
};
const stored = async (ticket) => JSON.parse(await kv.get(`pending:${ticket}`));
const test = async (name, run) => {
  await run();
  console.log(`ok ${name}`);
};

let first, record;

await test("a new sign-up stores the record and the fingerprint, and no counter", async () => {
  const before = kv.writes;
  const r = await signUp("dogfighter.net", "Pilot@Example.com ");
  assert.equal(r.status, 200);
  assert.match(r.body.ticket, /^[0-9a-f]{32}$/);
  first = r.body.ticket;
  record = await stored(first);
  assert.equal(record.email, "Pilot@Example.com");
  assert.match(record.consent, /^yes, \d{4}-/);
  assert.equal(Date.parse(record.sendAfter) - Date.parse(record.signedUpAt), 30 * 60 * 1000);
  assert.equal(await kv.get("count"), null);
  assert.equal(kv.writes - before, 3, "salt, pending and fingerprint on the very first sign-up");
});

await test("the number of sign-ups is the number of fingerprint keys", async () => {
  const before = kv.writes;
  await signUp("dogfighter.net", "second@example.com");
  assert.equal(kv.writes - before, 2, "pending and fingerprint");
  await signUp("dogfighter.net", "  pilot@example.COM");
  assert.equal((await kv.list({ prefix: "fp:" })).keys.length, 2);
});

await test("a known address gets the same answer but stores no address", async () => {
  const r = await signUp("dogfighter.net", "PILOT@example.com");
  assert.equal(r.status, 200);
  assert.equal((await stored(r.body.ticket)).email, undefined);
});

await test("honeypot, bad email, missing consent and a foreign origin are refused", async () => {
  assert.equal((await signUp("dogfighter.net", "bot@example.com", { website: "x" })).status, 200);
  assert.deepEqual((await signUp("dogfighter.net", "nope")).body.fields, ["email"]);
  assert.deepEqual((await signUp("dogfighter.net", "a@b.co", { consent: "" })).body.fields, ["consent"]);
  assert.deepEqual((await signUp("dogfighter.net", `${"x".repeat(250)}@b.co`)).body.fields, ["email"]);
  const res = await worker.fetch(new Request("https://dogfighter.net/api/notify", { method: "POST", headers: { Origin: "https://evil.example", "Content-Type": "application/json" }, body: "{}" }), env);
  assert.equal(res.status, 403);
});

await test("previews and localhost make no KV calls at all", async () => {
  const used = [];
  const spy = { ...env, RELEASE_LIST: new Proxy(kv, { get: (target, name) => (typeof target[name] === "function" ? (...args) => (used.push(name), target[name](...args)) : target[name]) }) };
  for (const host of ["feat-x-dogfighter.example.workers.dev", "localhost"]) {
    const r = await signUp(host, "prev@example.com", {}, spy);
    assert.equal(r.body.dryRun, true);
    const res = await call(host, "/api/notify/answer", { ticket: r.body.ticket, seq: 1, answers: { store: ["GOG"] } }, spy);
    assert.equal(res.status, 200);
  }
  assert.deepEqual(used, []);
});

await test("a full set of answers replaces the stored set", async () => {
  const r = await save(first, 1, { devices: ["Xbox", "Mac", "Windows PC", "Android tablet"], store: ["App Store", "GOG"], online: "Yes", wishes: ["Widescreen", "Other:  Co-op   campaign "] });
  assert.equal(r.status, 200);
  assert.deepEqual((await stored(first)).answers, { devices: "Windows PC, Mac, Android tablet, Xbox", store: "GOG, App Store", online: "Yes", played: "", cd: "", wishes: "Widescreen, Other: Co-op campaign" });
  await save(first, 2, { devices: ["Mac"], store: ["GOG"], online: "No", played: "No" });
  assert.deepEqual((await stored(first)).answers, { devices: "Mac", store: "GOG", online: "No", played: "No", cd: "", wishes: "" });
  assert.ok((await kv.getWithMetadata(`pending:${first}`)).metadata.sendAfter);
});

await test("unknown questions and values are refused and change nothing", async () => {
  const before = JSON.stringify(await stored(first));
  for (const answers of [{ nope: "Yes" }, { store: ["Epic"] }, { store: ["No preference", "GOG"] }, { store: ["GOG", "GOG"] }, { devices: ["Mac", "Amiga"] }, { online: "Sometimes" }, { wishes: [`Other: ${"x".repeat(201)}`] }]) {
    assert.equal((await save(first, 50, answers)).status, 422, JSON.stringify(answers));
  }
  assert.equal((await call("dogfighter.net", "/api/notify/answer", { ticket: first, question: "store", value: "GOG" })).status, 400);
  assert.equal(JSON.stringify(await stored(first)), before);
});

await test("an older set arriving late is ignored", async () => {
  const before = kv.writes;
  const r = await save(first, 1, { devices: ["Linux"] });
  assert.deepEqual(r.body, { ok: true, kept: "newer" });
  assert.equal((await stored(first)).answers.devices, "Mac");
  assert.equal(kv.writes, before);
});

await test("an unchanged set with a newer number records the number, so an older set cannot win", async () => {
  const r = await signUp("dogfighter.net", "race@example.com");
  const ticket = r.body.ticket;
  assert.equal((await save(ticket, 3, {})).body.kept, "same");
  assert.equal((await stored(ticket)).seq, 3);
  assert.equal((await save(ticket, 2, { store: ["Steam"] })).body.kept, "newer");
  assert.equal((await stored(ticket)).answers.store, "");
});

await test("a ticket stops writing after ten saves and says so", async () => {
  const r = await signUp("dogfighter.net", "busy@example.com");
  const ticket = r.body.ticket;
  const before = kv.writes;
  for (let i = 1; i <= 40; i++) assert.equal((await save(ticket, i, { online: i % 2 ? "Yes" : "No" })).status, 200);
  assert.equal(kv.writes - before, 10);
  assert.equal((await stored(ticket)).saves, 10);
  assert.equal((await save(ticket, 41, { online: "Maybe" })).body.kept, "limit");
});

await test("after the cap, up to three final saves still go through", async () => {
  const ticket = (await signUp("dogfighter.net", "final@example.com")).body.ticket;
  for (let i = 1; i <= 10; i++) await save(ticket, i, { online: i % 2 ? "Yes" : "No" });
  const before = kv.writes;
  assert.equal((await save(ticket, 11, { online: "Maybe", cd: "Yes" }, true)).body.kept, "saved");
  assert.equal((await stored(ticket)).answers.cd, "Yes");
  assert.equal((await save(ticket, 12, { online: "No" }, true)).body.kept, "saved");
  assert.equal((await save(ticket, 13, { online: "Yes" }, true)).body.kept, "saved");
  assert.equal((await save(ticket, 14, { online: "Maybe" }, true)).body.kept, "limit");
  assert.equal(kv.writes - before, 3);
  assert.equal((await stored(ticket)).answers.online, "Yes");
});

await test("unknown tickets are refused", async () => {
  assert.equal((await save("0".repeat(32), 1, { online: "Yes" })).status, 404);
});

const realNow = Date.now;
let waiting;
const runCron = async () => {
  await worker.scheduled({}, env, { waitUntil: (promise) => (waiting = promise) });
  await waiting;
};

await test("answers after 30 minutes are refused", async () => {
  Date.now = () => realNow() + 30 * 60 * 1000 + 1000;
  assert.equal((await save(first, 99, { online: "Yes" })).status, 410);
});

await test("the cron leaves records that are not due", async () => {
  Date.now = () => realNow() + 10 * 60 * 1000;
  calls.length = 0;
  await runCron();
  assert.equal(calls.length, 0);
});

await test("a failed post keeps the record", async () => {
  Date.now = () => realNow() + 33 * 60 * 1000;
  formStatus = 500;
  calls.length = 0;
  await runCron();
  assert.ok(calls.some((c) => c.url === FORM));
  assert.ok(await kv.get(`pending:${first}`));
});

await test("the cron posts one entry per sign-up and deletes every due record", async () => {
  formStatus = 200;
  calls.length = 0;
  await runCron();
  const posts = calls.filter((c) => c.url === FORM).map((c) => new URLSearchParams(c.body));
  assert.equal(posts.length, 5);
  const pilot = posts.find((p) => p.get("entry.1012705176") === "Pilot@Example.com");
  assert.equal(pilot.get("entry.1744446073"), "Mac");
  assert.equal(pilot.get("entry.1288670731"), "GOG");
  assert.equal(pilot.get("entry.2024524730"), "No");
  assert.equal(pilot.get("entry.162156460"), record.signedUpAt);
  assert.equal(pilot.get("entry.1691053737"), record.consent);
  assert.equal(pilot.get("fvv"), "1");
  assert.equal((await kv.list({ prefix: "pending:" })).keys.length, 0);
});

await test("a record saved by an older page with a single store still posts", async () => {
  const old = { email: "old@example.com", country: "NL", signedUpAt: new Date(realNow() - 3600000).toISOString(), consent: "yes, then", sendAfter: new Date(realNow() - 1800000).toISOString(), answers: { devices: "", store: "Steam", online: "", played: "", cd: "", wishes: "" } };
  await kv.put(`pending:${"a".repeat(32)}`, JSON.stringify(old), { metadata: { sendAfter: old.sendAfter } });
  calls.length = 0;
  await runCron();
  assert.equal(new URLSearchParams(calls.find((c) => c.url === FORM).body).get("entry.1288670731"), "Steam");
});
Date.now = realNow;
