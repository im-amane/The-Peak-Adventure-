import test from "node:test";
import assert from "node:assert/strict";
import worker from "./worker.mjs";
import "../webapp/pathfinding.js";
import { readFileSync } from "node:fs";

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

test("dungeon API is POST-only and forwards authenticated requests", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  let forwardedBody;
  globalThis.fetch = async (url, init) => {
    forwardedUrl = String(url);
    forwardedBody = init.body;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const getResponse = await worker.fetch(
      new Request("https://edge.example/api/dungeon", { method: "GET" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(getResponse.status, 405);
    assert.equal(getResponse.headers.get("allow"), "POST");
    const postResponse = await worker.fetch(
      new Request("https://edge.example/api/dungeon", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": "signed-data", "Content-Type": "application/json" },
        body: JSON.stringify({ action: "enter", dungeon_id: 1 }),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(postResponse.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/dungeon");
    assert.equal(new TextDecoder().decode(forwardedBody), JSON.stringify({ action: "enter", dungeon_id: 1 }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("daily mission claim API is POST-only and forwards Telegram auth", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  let forwardedAuth;
  let forwardedBody;
  globalThis.fetch = async (url, init) => {
    forwardedUrl = String(url);
    forwardedAuth = new Headers(init.headers).get("x-telegram-init-data");
    forwardedBody = init.body;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const getResponse = await worker.fetch(
      new Request("https://edge.example/api/daily-mission/claim", { method: "GET" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(getResponse.status, 405);
    assert.equal(getResponse.headers.get("allow"), "POST");
    const postResponse = await worker.fetch(
      new Request("https://edge.example/api/daily-mission/claim", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": "signed-data", "Content-Type": "application/json" },
        body: JSON.stringify({ mission_id: "daily_hunter" }),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(postResponse.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/daily-mission/claim");
    assert.equal(forwardedAuth, "signed-data");
    assert.equal(new TextDecoder().decode(forwardedBody), JSON.stringify({ mission_id: "daily_hunter" }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("weekly quest claim API forwards authenticated request", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  let forwardedAuth;
  let forwardedBody;
  globalThis.fetch = async (url, init) => {
    forwardedUrl = String(url);
    forwardedAuth = new Headers(init.headers).get("x-telegram-init-data");
    forwardedBody = init.body;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const getResponse = await worker.fetch(
      new Request("https://edge.example/api/weekly-quest/claim", { method: "GET" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(getResponse.status, 405);
    assert.equal(getResponse.headers.get("allow"), "POST");
    const postResponse = await worker.fetch(
      new Request("https://edge.example/api/weekly-quest/claim", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": "signed-data", "Content-Type": "application/json" },
        body: JSON.stringify({ quest_id: "weekly_hunter" }),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(postResponse.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/weekly-quest/claim");
    assert.equal(forwardedAuth, "signed-data");
    assert.equal(new TextDecoder().decode(forwardedBody), JSON.stringify({ quest_id: "weekly_hunter" }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("world API is POST-only and forwards authenticated travel requests", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  let forwardedAuth;
  let forwardedBody;
  globalThis.fetch = async (url, init) => {
    forwardedUrl = String(url);
    forwardedAuth = new Headers(init.headers).get("x-telegram-init-data");
    forwardedBody = init.body;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const getResponse = await worker.fetch(
      new Request("https://edge.example/api/world", { method: "GET" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(getResponse.status, 405);
    assert.equal(getResponse.headers.get("allow"), "POST");
    const postResponse = await worker.fetch(
      new Request("https://edge.example/api/world", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": "signed-data", "Content-Type": "application/json" },
        body: JSON.stringify({ action: "travel", world_id: 2 }),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(postResponse.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/world");
    assert.equal(forwardedAuth, "signed-data");
    assert.equal(new TextDecoder().decode(forwardedBody), JSON.stringify({ action: "travel", world_id: 2 }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("social management API is POST-only and forwards signed requests", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  let forwardedAuth;
  let forwardedBody;
  globalThis.fetch = async (url, init) => {
    forwardedUrl = String(url);
    forwardedAuth = new Headers(init.headers).get("x-telegram-init-data");
    forwardedBody = init.body;
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const getResponse = await worker.fetch(
      new Request("https://edge.example/api/social", { method: "GET" }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(getResponse.status, 405);
    assert.equal(getResponse.headers.get("allow"), "POST");
    const body = JSON.stringify({ action: "party_create" });
    const postResponse = await worker.fetch(
      new Request("https://edge.example/api/social", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": "signed-social-data", "Content-Type": "application/json" },
        body,
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(postResponse.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/social");
    assert.equal(forwardedAuth, "signed-social-data");
    assert.equal(new TextDecoder().decode(forwardedBody), body);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("serves current Mini App source files from the embedded fallback assets", async () => {
  const assets = [
    { route: "/", file: "../webapp/index.html", type: "text/html; charset=utf-8" },
    { route: "/style.css", file: "../webapp/style.css", type: "text/css; charset=utf-8" },
    { route: "/game.js", file: "../webapp/game.js", type: "application/javascript; charset=utf-8" },
    { route: "/pathfinding.js", file: "../webapp/pathfinding.js", type: "application/javascript; charset=utf-8" },
  ];

  for (const asset of assets) {
    const expected = readFileSync(new URL(asset.file, import.meta.url), "utf8");
    const response = await worker.fetch(
      new Request("https://edge.example" + asset.route),
      {},
    );
    assert.equal(response.status, 200, asset.route);
    assert.equal(response.headers.get("content-type"), asset.type, asset.route);
    assert.equal(await response.text(), expected, asset.route);
  }
});


test("world portal requires proximity and an unlocked next world", () => {
  const html = readFileSync(new URL("../webapp/index.html", import.meta.url), "utf8");
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(html, /id="portal-travel"/);
  assert.match(game, /nearPortal=Phaser\.Math\.Distance\.Between\(this\.hero\.x,this\.hero\.y,this\.portalX,this\.portalY\)<72/);
  assert.match(game, /ui\.portalTravel\.disabled=!nearPortal\|\|!nextWorld\|\|!nextWorld\.unlocked/);
  assert.match(game, /ui\.portalTravel\.addEventListener\("click"/);
});


test("A-star pathfinding routes around obstacles without cutting corners", () => {
  const path = globalThis.PeakPathfinding.findPath(
    { x: 50, y: 50 },
    { x: 250, y: 50 },
    [{ x: 150, y: 50, width: 60, height: 80 }],
    { width: 320, height: 200, cellSize: 20, margin: 0 },
  );
  assert.ok(path.length > 0);
  assert.deepEqual(path[path.length - 1], { x: 250, y: 50 });
  for (const point of path) {
    assert.ok(Math.abs(point.x - 150) >= 30 || Math.abs(point.y - 50) >= 40);
  }
});

test("A-star pathfinding rejects blocked and out-of-bounds destinations", () => {
  const options = { width: 200, height: 160, cellSize: 20, margin: 0 };
  const obstacle = [{ x: 120, y: 80, width: 60, height: 60 }];
  assert.deepEqual(
    globalThis.PeakPathfinding.findPath({ x: 20, y: 20 }, { x: 120, y: 80 }, obstacle, options),
    [],
  );
  assert.deepEqual(
    globalThis.PeakPathfinding.findPath({ x: 20, y: 20 }, { x: 240, y: 80 }, [], options),
    [],
  );
});


test("Mini App loads A-star and uses it for tap-to-move navigation", () => {
  const html = readFileSync(new URL("../webapp/index.html", import.meta.url), "utf8");
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(html, /<script src="\/pathfinding\.js"><\/script>/);
  assert.match(game, /window\.PeakPathfinding\.findPath/);
  assert.match(game, /this\.movePathIndex/);
  assert.match(game, /this\.cameras\.main\.getWorldPoint/);
});


test("A-star pathfinding routes around blocked map obstacles", () => {
  const path = globalThis.PeakPathfinding.findPath(
    { x: 32, y: 96 },
    { x: 256, y: 96 },
    [{ x: 144, y: 96, width: 64, height: 64 }],
    { width: 320, height: 220, minY: 32, cellSize: 32 },
  );
  assert.ok(path.length > 0);
  assert.deepEqual(path[path.length - 1], { x: 256, y: 96 });
  assert.ok(path.some(point => Math.abs(point.y - 96) > 32));
});

test("A-star returns a direct destination inside the same grid cell", () => {
  const destination = { x: 42, y: 90 };
  const path = globalThis.PeakPathfinding.findPath(
    { x: 35, y: 82 }, destination, [],
    { width: 320, height: 220, minY: 32, cellSize: 32 },
  );
  assert.deepEqual(path, [destination]);
});

test("A-star rejects blocked goals and invalid world bounds", () => {
  const blockedGoal = globalThis.PeakPathfinding.findPath(
    { x: 32, y: 96 },
    { x: 144, y: 96 },
    [{ x: 144, y: 96, width: 64, height: 64 }],
    { width: 320, height: 220, minY: 32, cellSize: 32 },
  );
  const invalidBounds = globalThis.PeakPathfinding.findPath(
    { x: 32, y: 96 }, { x: 256, y: 96 }, [], { width: 0, height: 0 },
  );
  assert.deepEqual(blockedGoal, []);
  assert.deepEqual(invalidBounds, []);
});


test("hero workshop persists face and body customization controls", () => {
  const html = readFileSync(new URL("../webapp/index.html", import.meta.url), "utf8");
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(html, /id="appearance-face"/);
  assert.match(html, /id="appearance-body"/);
  assert.match(game, /appearance\.face==="angular"/);
  assert.match(game, /appearance\.face==="scarred"/);
  assert.match(game, /bodyScale/);
  assert.match(game, /this\.heroBaseScaleX=this\.hero\.scaleX/);
  assert.match(game, /this\.hero\.setScale\(this\.heroBaseScaleX,1\)/);
  assert.match(game, /\["race","skin","hair","face","body","outfit"\]/);
});


test("hero level-up, defeat and respawn effects are wired to state changes", () => {
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(game, /previousLevel !== null && data\.level > previousLevel/);
  assert.match(game, /previousHp !== null && previousHp > 0 && data\.hp <= 0/);
  assert.match(game, /playDeathAnimation\(\)/);
  assert.match(game, /playRespawnAnimation\(\)/);
  assert.match(game, /playLevelUpAnimation\(\)/);
  assert.match(game, /let pendingSceneEffects = \[\]/);
  assert.match(game, /function flushSceneEffects\(\)/);
  assert.match(game, /pendingSceneEffects\.push\("levelup"\)/);
});


test("A-star does not move diagonally through two blocked corner cells", () => {
  const path = globalThis.PeakPathfinding.findPath(
    { x: 10, y: 10 },
    { x: 30, y: 30 },
    [
      { x: 30, y: 10, width: 20, height: 20 },
      { x: 10, y: 30, width: 20, height: 20 },
    ],
    { width: 40, height: 40, cellSize: 20, margin: 0 },
  );
  assert.deepEqual(path, []);
});


test("premium shop API is forwarded through the edge allowlist", async () => {
  const originalFetch = globalThis.fetch;
  let forwardedUrl;
  globalThis.fetch = async url => {
    forwardedUrl = String(url);
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    const response = await worker.fetch(
      new Request("https://edge.example/api/premium-shop", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "catalog" }),
      }),
      { BACKEND_ORIGIN: "https://game.example" },
    );
    assert.equal(response.status, 200);
    assert.equal(forwardedUrl, "https://game.example/api/premium-shop");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("hero idle animation does not tween world position and yields to walking", () => {
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(game, /targets:this\.hero, scaleY:1\.025, duration:650/);
  assert.match(game, /if\(this\.heroIdle\)\{\s*this\.heroIdle\.stop\(\);\s*this\.heroIdle=null;/);
  assert.match(game, /if\(!this\.heroIdle\)\{\s*this\.heroIdle=this\.tweens\.add\(\{targets:this\.hero,scaleY:1\.025/);
  assert.doesNotMatch(game, /targets:this\.hero, y:this\.hero\.y-3/);
});


test("movement clamps long frame deltas after tab suspension", () => {
  const game = readFileSync(new URL("../webapp/game.js", import.meta.url), "utf8");
  assert.match(game, /const frameDelta=Phaser\.Math\.Clamp\(Number\(delta\)\|\|0,0,50\)/);
  assert.match(game, /const baseSpeed=0\.18\*frameDelta/);
  assert.doesNotMatch(game, /const baseSpeed=0\.18\*delta/);
});
