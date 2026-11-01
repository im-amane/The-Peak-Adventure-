import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";

test("rejects paths outside the game API allowlist", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/private"),
    { BACKEND_ORIGIN: "https://game.example" },
  );
  assert.equal(response.status, 404);
});

test("rejects methods that are not allowed for a route", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/api/action", { method: "GET" }),
    { BACKEND_ORIGIN: "https://game.example" },
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "POST");
});

test("requires a valid HTTPS backend origin", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/healthz"),
    { BACKEND_ORIGIN: "http://insecure.example" },
  );
  assert.equal(response.status, 503);
});

test("forwards Telegram init data and disables API caching", async () => {
  const originalFetch = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (url, init) => {
    forwarded = { url: String(url), headers: new Headers(init.headers) };
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const response = await worker.fetch(
      new Request("https://edge.example/api/state", {
        headers: { "X-Telegram-Init-Data": "user=%7B%7D&hash=abc" },
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(response.status, 200);
    assert.equal(forwarded.url, "https://game.example/api/state");
    assert.equal(forwarded.headers.get("x-telegram-init-data"), "user=%7B%7D&hash=abc");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("x-edge-worker"), "peak-adventure");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects oversized POST bodies before forwarding", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("upstream must not be called");
  };
  try {
    const response = await worker.fetch(
      new Request("https://edge.example/api/action", {
        method: "POST",
        body: "x".repeat(32 * 1024 + 1),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(response.status, 413);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("does not forward browser cookies or arbitrary authorization headers", async () => {
  const originalFetch = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (_url, init) => {
    forwarded = new Headers(init.headers);
    return new Response("ok", { status: 200 });
  };
  try {
    await worker.fetch(
      new Request("https://edge.example/api/state", {
        headers: {
          "X-Telegram-Init-Data": "safe-init-data",
          "Cookie": "session=private",
          "Authorization": "Bearer private",
        },
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(forwarded.get("x-telegram-init-data"), "safe-init-data");
    assert.equal(forwarded.get("cookie"), null);
    assert.equal(forwarded.get("authorization"), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("serves the Mini App shell through the Cloudflare static assets binding", async () => {
  let requestedPath;
  const response = await worker.fetch(
    new Request("https://edge.example/"),
    {
      ASSETS: {
        fetch: async (request) => {
          requestedPath = new URL(request.url).pathname;
          return new Response("<main>Peak Adventure</main>", { status: 200 });
        },
      },
    },
  );
  assert.equal(response.status, 200);
  assert.equal(requestedPath, "/");
  assert.match(await response.text(), /Peak Adventure/);
});

test("rejects backend URLs that contain paths or query strings", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/api/state"),
    { BACKEND_ORIGIN: "https://game.example/internal?debug=1" },
  );
  assert.equal(response.status, 503);
});

test("allows appearance API POST route", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/api/appearance", { method: "GET" }),
    { BACKEND_ORIGIN: "https://game.example" },
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "POST");
});

test("quest claim API is POST-only", async () => {
  const response = await worker.fetch(
    new Request("https://edge.example/api/quest/claim", { method: "GET" }),
    { BACKEND_ORIGIN: "https://game.example" },
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "POST");
});

test("settings API allows GET and POST only", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ ok: true }), { status: 200 });
  try {
    for (const method of ["GET", "POST"]) {
      const response = await worker.fetch(
        new Request("https://edge.example/api/settings", { method }),
        { BACKEND_ORIGIN: "https://game.example" },
      );
      assert.equal(response.status, 200);
    }
    const response = await worker.fetch(
      new Request("https://edge.example/api/settings", { method: "DELETE" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(response.status, 405);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
