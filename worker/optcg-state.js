// Cloudflare Worker: optcg-state (https://optcg-state.46jwnf9v56.workers.dev/)
// Saves / loads Utility Cards page state as saved_states/<name>.json in the GitHub repo.
//
// Deploy: paste this file into the Worker in the Cloudflare dashboard (or `wrangler deploy`).
// Secrets (Settings → Variables and Secrets, type "Secret"):
//   PASSWORD      the save/load password
//   GITHUB_TOKEN  fine-grained token, ONLY this repo, permission "Contents: Read and write"
//
// API (all JSON, all POST so the password never appears in a URL or access log):
//   {action:"save",   password, name, state}  -> {ok, name}
//   {action:"load",   password, name}         -> {name, state}
//   {action:"exists", password, name}         -> {exists}
// A body with no `action` but with `state` is treated as "save" (old page compatibility).
//
// NOTE: the repo is public, so saved_states/*.json can be read on GitHub by anyone. The password
// protects writes and this API, not the files themselves.

const REPO = "JakeVestal/optcg_playbook";
const ALLOWED_ORIGINS = [
  "https://jakevestal.github.io",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];
const MAX_BODY_BYTES = 512 * 1024;

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function json(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(request), "Content-Type": "application/json" },
  });
}

// Constant-time string compare so the password can't be guessed by timing.
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const x = enc.encode(String(a ?? ""));
  const y = enc.encode(String(b ?? ""));
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

// UTF-8 safe base64 (GitHub contents API uses base64).
function toBase64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
function fromBase64(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, c => c.charCodeAt(0)));
}

function ghHeaders(env, extra = {}) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    "User-Agent": "optcg-state",
    Accept: "application/vnd.github+json",
    ...extra,
  };
}

async function getFile(env, path) {
  const res = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, { headers: ghHeaders(env) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`github read failed: ${res.status}`);
  return res.json();
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders(request) });
    if (request.method !== "POST") return json(request, { error: "method not allowed" }, 405);

    const len = Number(request.headers.get("Content-Length") || 0);
    if (len > MAX_BODY_BYTES) return json(request, { error: "state too large" }, 413);

    let body;
    try {
      const text = await request.text();
      if (text.length > MAX_BODY_BYTES) return json(request, { error: "state too large" }, 413);
      body = JSON.parse(text);
    } catch {
      return json(request, { error: "invalid JSON" }, 400);
    }

    const { password, name, state } = body || {};
    const action = body?.action || (state ? "save" : "");
    if (!env.PASSWORD || !safeEqual(password, env.PASSWORD)) return json(request, { error: "bad password" }, 401);
    if (!name || typeof name !== "string") return json(request, { error: "missing name" }, 400);

    const safeName = name.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 64);
    const path = `saved_states/${safeName}.json`;

    try {
      if (action === "exists") {
        return json(request, { exists: !!(await getFile(env, path)) });
      }

      if (action === "load") {
        const file = await getFile(env, path);
        if (!file) return json(request, { error: "not found" }, 404);
        return json(request, { name: safeName, state: JSON.parse(fromBase64(file.content)) });
      }

      if (action === "save") {
        if (!state || typeof state !== "object") return json(request, { error: "missing state" }, 400);
        const existing = await getFile(env, path);
        const putRes = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, {
          method: "PUT",
          headers: ghHeaders(env, { "Content-Type": "application/json" }),
          body: JSON.stringify({
            message: `state: ${safeName}`,
            content: toBase64(JSON.stringify(state, null, 2) + "\n"),
            ...(existing ? { sha: existing.sha } : {}),
          }),
        });
        if (!putRes.ok) {
          console.error("github write failed", putRes.status, await putRes.text());
          return json(request, { error: "github write failed" }, 502);
        }
        return json(request, { ok: true, name: safeName });
      }

      return json(request, { error: "unknown action" }, 400);
    } catch (e) {
      console.error(e);
      return json(request, { error: "server error" }, 500);
    }
  },
};
