const STATIC_PATHS = new Set(["/", "/style.css", "/game.js"]);

const ROUTES = new Map([
  ["/healthz", new Set(["GET"])],
  ["/api/state", new Set(["GET"])],
  ["/api/explore", new Set(["POST"])],
  ["/api/action", new Set(["POST"])],
  ["/api/appearance", new Set(["POST"])],
]);

const MAX_BODY_BYTES = 32 * 1024;

function json(data, status, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      ...extraHeaders,
    },
  });
}

function resolveOrigin(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const origin = new URL(value);
    if (origin.protocol !== "https:" || origin.username || origin.password) return null;
    if (origin.pathname !== "/" || origin.search || origin.hash) return null;
    return origin;
  } catch {
    return null;
  }
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (STATIC_PATHS.has(incoming.pathname) && request.method === "GET") {
      if (!env.ASSETS) return json({ error: "Static assets are not configured" }, 503);
      return env.ASSETS.fetch(request);
    }
    const allowedMethods = ROUTES.get(incoming.pathname);
    if (!allowedMethods) return json({ error: "Not found" }, 404);
    if (!allowedMethods.has(request.method)) {
      return json({ error: "Method not allowed" }, 405, { allow: [...allowedMethods].join(", ") });
    }

    const origin = resolveOrigin(env.BACKEND_ORIGIN);
    if (!origin) return json({ error: "Edge gateway is not configured" }, 503);

    const upstreamUrl = new URL(incoming.pathname + incoming.search, origin);
    if (upstreamUrl.origin === incoming.origin) {
      return json({ error: "Invalid upstream configuration" }, 503);
    }

    let body;
    if (request.method !== "GET" && request.method !== "HEAD") {
      body = await request.arrayBuffer();
      if (body.byteLength > MAX_BODY_BYTES) {
        return json({ error: "Request body is too large" }, 413);
      }
    }

    const headers = new Headers();
    for (const name of ["accept", "content-type", "x-telegram-init-data"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", incoming.protocol.slice(0, -1));
    const clientIp = request.headers.get("cf-connecting-ip");
    if (clientIp) headers.set("x-forwarded-for", clientIp);

    try {
      const upstream = await fetch(upstreamUrl, {
        method: request.method,
        headers,
        body,
        redirect: "manual",
      });
      const responseHeaders = new Headers(upstream.headers);
      responseHeaders.set("x-content-type-options", "nosniff");
      responseHeaders.set("x-edge-worker", "peak-adventure");
      if (incoming.pathname.startsWith("/api/") || incoming.pathname === "/healthz") {
        responseHeaders.set("cache-control", "no-store");
      }
      return new Response(upstream.body, {
        status: upstream.status,
        statusText: upstream.statusText,
        headers: responseHeaders,
      });
    } catch {
      return json({ error: "Game server is temporarily unavailable" }, 502);
    }
  },
};
