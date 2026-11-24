const ENTRY = { topic: "entry.470199097", message: "entry.735761902", email: "entry.128772096" };
const TOPICS = ["Help with installing", "Bug report", "Idea or feedback", "Press or rights", "Something else"];
const SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const PRODUCTION_HOSTS = ["dogfighter.net", "www.dogfighter.net"];
const TEST_SECRET = "1x0000000000000000000000000000000AA";

const MAX_BODY = 16 * 1024;
const MAX_MESSAGE = 5000;
const MAX_EMAIL = 254;
const EMAIL = /^[^\s@"<>]+@[^\s@"<>]+\.[^\s@"<>]+$/;

const NOTIFY_ENTRY = {
  email: "entry.1012705176",
  country: "entry.363929210",
  devices: "entry.1744446073",
  store: "entry.1288670731",
  online: "entry.2024524730",
  played: "entry.382346384",
  cd: "entry.1407845707",
  wishes: "entry.1323108092",
  signedUpAt: "entry.162156460",
  consent: "entry.1691053737",
};
const QUESTIONS = {
  devices: { multi: true, options: ["Windows", "Mac", "Linux / Steam Deck", "iPad"] },
  store: { options: ["Steam", "GOG", "dogfighter.net", "No preference"] },
  online: { options: ["Yes", "Maybe", "No"] },
  played: { options: ["Yes, back then", "Yes, recently", "No"] },
  cd: { options: ["Yes", "No", "Not sure"] },
  wishes: { multi: true, other: true, options: ["Online multiplayer", "Widescreen", "Controller support", "New missions", "Level editor"] },
};
const ANSWER_WINDOW = 30 * 60 * 1000;
const SEND_GRACE = 2 * 60 * 1000;
const MAX_OTHER = 200;
const MAX_SENDS = 40;
const TICKET = /^[0-9a-f]{32}$/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/contact") return contact(request, env, url);
    if (url.pathname === "/api/notify") return notify(request, env, url);
    if (url.pathname === "/api/notify/answer") return answer(request, env, url);
    if (url.pathname.startsWith("/api/")) return reply(404, { ok: false, error: "not_found" });
    return env.ASSETS.fetch(request);
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(sendPending(env));
  },
};

function refuse(request, url) {
  if (request.method !== "POST") return reply(405, { ok: false, error: "method" }, { Allow: "POST" });

  const origin = request.headers.get("Origin");
  const fetchSite = request.headers.get("Sec-Fetch-Site");
  if (origin !== url.origin || (fetchSite && fetchSite !== "same-origin")) return reply(403, { ok: false, error: "forbidden" });

  const length = Number(request.headers.get("Content-Length") || 0);
  if (length > MAX_BODY) return reply(413, { ok: false, error: "too_large" });
  return null;
}

async function contact(request, env, url) {
  const refused = refuse(request, url);
  if (refused) return refused;

  const fields = await readFields(request, ["topic", "message", "email", "website", "cf-turnstile-response"]);
  if (!fields) return reply(400, { ok: false, error: "bad_request" });

  if (fields.website) return reply(200, { ok: true });

  const topic = fields.topic;
  const message = fields.message.trim();
  const email = fields.email.trim();
  const token = fields["cf-turnstile-response"];
  const invalid = [];
  if (!TOPICS.includes(topic)) invalid.push("topic");
  if (!message || message.length > MAX_MESSAGE) invalid.push("message");
  if (!email || email.length > MAX_EMAIL || !EMAIL.test(email)) invalid.push("email");
  if (!token || token.length > 2048) invalid.push("turnstile");
  if (invalid.length) return reply(422, { ok: false, error: "invalid", fields: invalid });

  const production = PRODUCTION_HOSTS.includes(url.hostname);
  const secret = production ? env.TURNSTILE_SECRET : TEST_SECRET;
  if (!secret || (production && !env.FORM_URL)) {
    console.log("contact: TURNSTILE_SECRET or FORM_URL is not set");
    return reply(503, { ok: false, error: "not_configured" });
  }

  const failed = await challenge(request, secret, token, "contact");
  if (failed) return failed;
  if (!production) return reply(200, { ok: true, dryRun: true });

  const form = new URLSearchParams({
    [ENTRY.topic]: topic,
    [ENTRY.message]: message,
    [ENTRY.email]: email,
    fvv: "1",
    pageHistory: "0",
  });
  let status;
  try {
    const res = await fetch(env.FORM_URL, { method: "POST", body: form, redirect: "manual" });
    status = res.status;
    await res.body?.cancel();
  } catch {
    status = 0;
  }
  if (status !== 200) {
    console.log(`contact: form answered ${status}`);
    return reply(502, { ok: false, error: "forward_failed" });
  }
  return reply(200, { ok: true });
}

async function notify(request, env, url) {
  const refused = refuse(request, url);
  if (refused) return refused;

  const fields = await readFields(request, ["email", "consent", "website", "cf-turnstile-response"]);
  if (!fields) return reply(400, { ok: false, error: "bad_request" });

  if (fields.website) return reply(200, { ok: true, ticket: hex(16) });

  const email = fields.email.trim();
  const token = fields["cf-turnstile-response"];
  const invalid = [];
  if (!email || email.length > MAX_EMAIL || !EMAIL.test(email)) invalid.push("email");
  if (fields.consent !== "yes") invalid.push("consent");
  if (!token || token.length > 2048) invalid.push("turnstile");
  if (invalid.length) return reply(422, { ok: false, error: "invalid", fields: invalid });

  const production = PRODUCTION_HOSTS.includes(url.hostname);
  const secret = production ? env.TURNSTILE_SECRET : TEST_SECRET;
  const kv = env.RELEASE_LIST;
  if (!secret || !kv) {
    console.log("notify: TURNSTILE_SECRET or RELEASE_LIST is not set");
    return reply(503, { ok: false, error: "not_configured" });
  }

  const failed = await challenge(request, secret, token, "notify");
  if (failed) return failed;

  const prefix = production ? "" : "preview:";
  const keep = production ? {} : { expirationTtl: 86400 };
  const ticket = hex(16);
  const now = new Date();
  const signedUpAt = now.toISOString();
  const sendAfter = new Date(now.getTime() + ANSWER_WINDOW).toISOString();
  try {
    const fingerprint = await sha256((await salt(kv, prefix)) + email.toLowerCase());
    const known = (await kv.get(`${prefix}fp:${fingerprint}`)) !== null;
    const record = known
      ? { discard: true, signedUpAt, sendAfter, answers: {} }
      : {
          email,
          country: request.cf?.country || "",
          signedUpAt,
          consent: `yes, ${signedUpAt}`,
          sendAfter,
          answers: Object.fromEntries(Object.keys(QUESTIONS).map((name) => [name, ""])),
        };
    await kv.put(`${prefix}pending:${ticket}`, JSON.stringify(record), { ...keep, metadata: { sendAfter } });
    if (!known) {
      await kv.put(`${prefix}fp:${fingerprint}`, "1", keep).catch(() => console.log("notify: fingerprint not stored"));
      if (production) await countOne(kv);
    }
  } catch {
    console.log("notify: storage failed");
    return reply(503, { ok: false, error: "storage" });
  }
  return reply(200, production ? { ok: true, ticket } : { ok: true, ticket, dryRun: true });
}

async function answer(request, env, url) {
  const refused = refuse(request, url);
  if (refused) return refused;
  if ((request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase() !== "application/json") return reply(400, { ok: false, error: "bad_request" });

  let body;
  try {
    const text = await request.text();
    if (text.length > MAX_BODY) return reply(413, { ok: false, error: "too_large" });
    body = JSON.parse(text);
  } catch {
    return reply(400, { ok: false, error: "bad_request" });
  }
  if (!body || typeof body !== "object" || typeof body.ticket !== "string" || !TICKET.test(body.ticket)) return reply(400, { ok: false, error: "bad_request" });
  const value = cleanAnswer(body.question, body.value);
  if (value === null) return reply(422, { ok: false, error: "invalid" });

  const kv = env.RELEASE_LIST;
  if (!kv) return reply(503, { ok: false, error: "not_configured" });
  const prefix = PRODUCTION_HOSTS.includes(url.hostname) ? "" : "preview:";
  const key = `${prefix}pending:${body.ticket}`;
  try {
    const stored = await kv.getWithMetadata(key);
    if (stored.value === null) return reply(404, { ok: false, error: "unknown" });
    const record = JSON.parse(stored.value);
    if (!(Date.now() - Date.parse(record.signedUpAt) < ANSWER_WINDOW)) return reply(410, { ok: false, error: "closed" });
    record.answers[body.question] = value;
    await kv.put(key, JSON.stringify(record), prefix ? { expirationTtl: 86400, metadata: stored.metadata } : { metadata: stored.metadata });
  } catch {
    console.log("notify: answer not stored");
    return reply(503, { ok: false, error: "storage" });
  }
  return reply(200, { ok: true });
}

function cleanAnswer(question, value) {
  if (typeof question !== "string" || !Object.hasOwn(QUESTIONS, question)) return null;
  const { multi, other, options } = QUESTIONS[question];
  if (!multi) return typeof value === "string" && options.includes(value) ? value : null;
  if (!Array.isArray(value) || value.length > options.length + 1) return null;
  const picked = [];
  let extra = "";
  for (const item of value) {
    if (typeof item !== "string") return null;
    if (options.includes(item)) picked.push(item);
    else if (other && item.startsWith("Other:") && !extra) extra = item.slice(6).replace(/\s+/g, " ").trim();
    else return null;
  }
  if (extra.length > MAX_OTHER) return null;
  const chosen = options.filter((option) => picked.includes(option));
  if (extra) chosen.push(`Other: ${extra}`);
  return chosen.join(", ");
}

async function sendPending(env) {
  const kv = env.RELEASE_LIST;
  if (!kv || !env.NOTIFY_FORM_URL) return;
  const due = Date.now() - SEND_GRACE;
  let sent = 0;
  let failed = 0;
  let cursor;
  do {
    const page = await kv.list({ prefix: "pending:", cursor });
    for (const { name, metadata } of page.keys) {
      if (sent + failed >= MAX_SENDS) break;
      if (metadata?.sendAfter && Date.parse(metadata.sendAfter) > due) continue;
      try {
        const raw = await kv.get(name);
        if (raw === null) continue;
        const record = JSON.parse(raw);
        if (Date.parse(record.sendAfter) > due) continue;
        if (record.discard) {
          await kv.delete(name);
          continue;
        }
        if (await postEntry(env.NOTIFY_FORM_URL, record)) {
          sent++;
          await kv.delete(name);
        } else {
          failed++;
        }
      } catch {
        failed++;
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor && sent + failed < MAX_SENDS);
  if (sent || failed) console.log(`notify: sent ${sent}, failed ${failed}`);
}

async function postEntry(formUrl, record) {
  const answers = record.answers || {};
  const form = new URLSearchParams({
    [NOTIFY_ENTRY.email]: record.email,
    [NOTIFY_ENTRY.country]: record.country || "",
    [NOTIFY_ENTRY.devices]: answers.devices || "",
    [NOTIFY_ENTRY.store]: answers.store || "",
    [NOTIFY_ENTRY.online]: answers.online || "",
    [NOTIFY_ENTRY.played]: answers.played || "",
    [NOTIFY_ENTRY.cd]: answers.cd || "",
    [NOTIFY_ENTRY.wishes]: answers.wishes || "",
    [NOTIFY_ENTRY.signedUpAt]: record.signedUpAt,
    [NOTIFY_ENTRY.consent]: record.consent,
    fvv: "1",
    pageHistory: "0",
  });
  let status;
  try {
    const res = await fetch(formUrl, { method: "POST", body: form, redirect: "manual" });
    status = res.status;
    await res.body?.cancel();
  } catch {
    status = 0;
  }
  if (status !== 200) console.log(`notify: form answered ${status}`);
  return status === 200;
}

async function salt(kv, prefix) {
  const key = `${prefix}salt`;
  const stored = await kv.get(key);
  if (stored) return stored;
  const fresh = hex(32);
  await kv.put(key, fresh);
  return fresh;
}

async function countOne(kv) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const count = Number((await kv.get("count")) || 0);
      await kv.put("count", String(count + 1));
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 1100));
    }
  }
  console.log("notify: count not updated");
}

function hex(bytes) {
  return [...crypto.getRandomValues(new Uint8Array(bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function challenge(request, secret, token, label) {
  const check = new URLSearchParams({ secret, response: token });
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) check.set("remoteip", ip);
  let verdict;
  try {
    const res = await fetch(SITEVERIFY, { method: "POST", body: check });
    verdict = await res.json();
  } catch {
    console.log(`${label}: siteverify did not answer`);
    return reply(502, { ok: false, error: "challenge_unavailable" });
  }
  if (!verdict.success) {
    console.log(`${label}: challenge failed ${JSON.stringify(verdict["error-codes"] || [])}`);
    return reply(403, { ok: false, error: "challenge_failed" });
  }
  return null;
}

async function readFields(request, names) {
  const type = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  let raw;
  try {
    if (type === "application/json") {
      const text = await request.text();
      if (text.length > MAX_BODY) return null;
      raw = JSON.parse(text);
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    } else if (type === "application/x-www-form-urlencoded") {
      const text = await request.text();
      if (text.length > MAX_BODY) return null;
      raw = Object.fromEntries(new URLSearchParams(text));
    } else if (type === "multipart/form-data") {
      if (!request.headers.get("Content-Length")) return null;
      raw = Object.fromEntries(await request.formData());
    } else {
      return null;
    }
  } catch {
    return null;
  }
  const fields = {};
  for (const name of names) {
    const value = raw[name] ?? "";
    if (typeof value !== "string") return null;
    fields[name] = value;
  }
  return fields;
}

function reply(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}
