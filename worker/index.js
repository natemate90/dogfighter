const ENTRY = { topic: "entry.470199097", message: "entry.735761902", email: "entry.128772096" };
const TOPICS = ["Help with installing", "Bug report", "Idea or feedback", "Press or rights", "Something else"];
const SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const PRODUCTION_HOSTS = ["dogfighter.net", "www.dogfighter.net"];
const TEST_SECRET = "1x0000000000000000000000000000000AA";

const MAX_BODY = 16 * 1024;
const MAX_MESSAGE = 5000;
const MAX_EMAIL = 254;
const EMAIL = /^[^\s@"<>]+@[^\s@"<>]+\.[^\s@"<>]+$/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/contact") return contact(request, env, url);
    if (url.pathname.startsWith("/api/")) return reply(404, { ok: false, error: "not_found" });
    return env.ASSETS.fetch(request);
  },
};

async function contact(request, env, url) {
  if (request.method !== "POST") return reply(405, { ok: false, error: "method" }, { Allow: "POST" });

  const origin = request.headers.get("Origin");
  const fetchSite = request.headers.get("Sec-Fetch-Site");
  if (origin !== url.origin || (fetchSite && fetchSite !== "same-origin")) return reply(403, { ok: false, error: "forbidden" });

  const length = Number(request.headers.get("Content-Length") || 0);
  if (length > MAX_BODY) return reply(413, { ok: false, error: "too_large" });

  const fields = await readFields(request);
  if (!fields) return reply(400, { ok: false, error: "bad_request" });

  if (fields.website) return reply(200, { ok: true });

  const topic = fields.topic;
  const message = fields.message.trim();
  const email = fields.email.trim();
  const token = fields["cf-turnstile-response"];
  const invalid = [];
  if (!TOPICS.includes(topic)) invalid.push("topic");
  if (!message || message.length > MAX_MESSAGE) invalid.push("message");
  if (email && (email.length > MAX_EMAIL || !EMAIL.test(email))) invalid.push("email");
  if (!token || token.length > 2048) invalid.push("turnstile");
  if (invalid.length) return reply(422, { ok: false, error: "invalid", fields: invalid });

  const production = PRODUCTION_HOSTS.includes(url.hostname);
  const secret = production ? env.TURNSTILE_SECRET : TEST_SECRET;
  if (!secret || (production && !env.FORM_URL)) {
    console.log("contact: TURNSTILE_SECRET or FORM_URL is not set");
    return reply(503, { ok: false, error: "not_configured" });
  }

  const check = new URLSearchParams({ secret, response: token });
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) check.set("remoteip", ip);
  let verdict;
  try {
    const res = await fetch(SITEVERIFY, { method: "POST", body: check });
    verdict = await res.json();
  } catch {
    console.log("contact: siteverify did not answer");
    return reply(502, { ok: false, error: "challenge_unavailable" });
  }
  if (!verdict.success) {
    console.log(`contact: challenge failed ${JSON.stringify(verdict["error-codes"] || [])}`);
    return reply(403, { ok: false, error: "challenge_failed" });
  }
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

async function readFields(request) {
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
  for (const name of ["topic", "message", "email", "website", "cf-turnstile-response"]) {
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
