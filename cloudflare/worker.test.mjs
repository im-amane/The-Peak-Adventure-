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
