import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/pathfinding.js";

const { findPath } = globalThis.PeakPathfinding;

function segmentIntersectsExpandedRect(from, to, obstacle, margin) {
  const halfWidth = obstacle.width / 2 + margin;
  const halfHeight = obstacle.height / 2 + margin;
  const left = obstacle.x - halfWidth;
  const right = obstacle.x + halfWidth;
  const top = obstacle.y - halfHeight;
  const bottom = obstacle.y + halfHeight;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  let enter = 0;
  let leave = 1;
  const p = [-dx, dx, -dy, dy];
  const q = [from.x - left, right - from.x, from.y - top, bottom - from.y];
  for (let index = 0; index < 4; index++) {
    if (p[index] === 0) {
      if (q[index] < 0) return false;
      continue;
    }
    const ratio = q[index] / p[index];
    if (p[index] < 0) enter = Math.max(enter, ratio);
    else leave = Math.min(leave, ratio);
    if (enter > leave) return false;
  }
  return true;
}

test("smooths unobstructed A-star routes to a single destination waypoint", () => {
  const destination = { x: 272, y: 272 };
  const path = findPath(
    { x: 16, y: 16 },
    destination,
    [],
    { width: 320, height: 320, cellSize: 16 },
  );

  assert.deepEqual(path, [destination]);
});

test("finds a route around an obstacle without entering its clearance area", () => {
  const obstacle = { x: 96, y: 80, width: 60, height: 60 };
  const path = findPath(
    { x: 16, y: 80 },
    { x: 176, y: 80 },
    [obstacle],
    { width: 224, height: 160, cellSize: 32, margin: 8 },
  );

  assert.ok(path.length > 1, "a route should be found around the obstacle");
  for (const point of path) {
    assert.ok(
      Math.abs(point.x - obstacle.x) >= obstacle.width / 2 + 8 ||
      Math.abs(point.y - obstacle.y) >= obstacle.height / 2 + 8,
      "path points must remain outside the obstacle clearance area",
    );
  }
  assert.deepEqual(path.at(-1), { x: 176, y: 80 });
});

test("does not cut diagonally between two blocked orthogonal cells", () => {
  const obstacles = [
    { x: 48, y: 16, width: 32, height: 32 },
    { x: 16, y: 48, width: 32, height: 32 },
  ];
  const path = findPath(
    { x: 16, y: 16 },
    { x: 80, y: 80 },
    obstacles,
    { width: 96, height: 96, cellSize: 32, margin: 0 },
  );

  assert.deepEqual(path, []);
});

test("returns no route when the destination is blocked", () => {
  const path = findPath(
    { x: 16, y: 16 },
    { x: 80, y: 80 },
    [{ x: 80, y: 80, width: 40, height: 40 }],
    { width: 128, height: 128, cellSize: 32 },
  );

  assert.deepEqual(path, []);
});

test("returns an empty route for invalid bounds or coordinates", () => {
  assert.deepEqual(findPath({ x: NaN, y: 0 }, { x: 20, y: 20 }, [], { width: 100, height: 100 }), []);
  assert.deepEqual(findPath({ x: 0, y: 0 }, { x: 20, y: 20 }, [], { width: 0, height: 100 }), []);
});

test("returns the requested destination when start and goal share a grid cell", () => {
  const destination = { x: 27, y: 25 };
  const path = findPath(
    { x: 16, y: 16 },
    destination,
    [],
    { width: 128, height: 128, cellSize: 32 },
  );

  assert.deepEqual(path, [destination]);
});


test("rejects a path when the starting position is blocked", () => {
  const path = findPath(
    { x: 48, y: 48 },
    { x: 112, y: 48 },
    [{ x: 48, y: 48, width: 40, height: 40 }],
    { width: 160, height: 128, cellSize: 32, margin: 0 },
  );

  assert.deepEqual(path, []);
});


test("respects the configured A-star node budget", () => {
  const path = findPath(
    { x: 16, y: 16 },
    { x: 272, y: 272 },
    [],
    { width: 320, height: 320, cellSize: 16, maxNodes: 1 },
  );
  assert.deepEqual(path, []);
});

test("ignores malformed obstacles without breaking valid routes", () => {
  const path = findPath(
    { x: 16, y: 16 },
    { x: 112, y: 16 },
    [{ x: NaN, y: 40, width: 20, height: 20 }, null],
    { width: 160, height: 96, cellSize: 16, margin: 0 },
  );
  assert.ok(path.length > 0);
  assert.deepEqual(path.at(-1), { x: 112, y: 16 });
});

test("routes around thin obstacles crossed by diagonal movement segments", () => {
  const obstacle = { x: 32, y: 32, width: 8, height: 8 };
  const path = findPath(
    { x: 16, y: 16 },
    { x: 48, y: 48 },
    [obstacle],
    { width: 96, height: 96, cellSize: 32, margin: 0 },
  );

  assert.ok(path.length >= 2, "a safe orthogonal detour should be found");
  const points = [{ x: 16, y: 16 }, ...path];
  for (let index = 1; index < points.length; index++) {
    const from = points[index - 1];
    const to = points[index];
    // This fixture's obstacle is centered on the direct diagonal. A route
    // must not use that diagonal even though both endpoint cells are open.
    assert.ok(
      !(from.x === 16 && from.y === 16 && to.x === 48 && to.y === 48),
      "the path must not cut through the thin obstacle",
    );
  }
  assert.deepEqual(path.at(-1), { x: 48, y: 48 });
});

test("checks direct movement when start and goal share a grid cell", () => {
  const path = findPath(
    { x: 5, y: 16 },
    { x: 27, y: 16 },
    [{ x: 16, y: 16, width: 4, height: 4 }],
    { width: 96, height: 96, cellSize: 32, margin: 0 },
  );

  assert.deepEqual(path, []);
});


test("smoothed obstacle routes keep every movement segment outside clearance", () => {
  const start = { x: 16, y: 80 };
  const obstacle = { x: 96, y: 80, width: 60, height: 60 };
  const path = findPath(
    start,
    { x: 176, y: 80 },
    [obstacle],
    { width: 224, height: 160, cellSize: 32, margin: 8 },
  );
  const points = [start, ...path];

  assert.ok(path.length >= 2, "the obstacle should require a detour");
  assert.ok(path.length < 6, "line-of-sight smoothing should remove grid zigzags");
  for (let index = 1; index < points.length; index++) {
    assert.equal(
      segmentIntersectsExpandedRect(points[index - 1], points[index], obstacle, 8),
      false,
      "smoothed movement segments must not cross the obstacle clearance area",
    );
  }
});


test("rasterizes obstacle rectangles only into the cells they actually cover", () => {
  const start = { x: 16, y: 48 };
  const goal = { x: 112, y: 48 };
  const obstacle = { x: 64, y: 48, width: 32, height: 32 };
  const path = findPath(
    start,
    goal,
    [
      obstacle,
      ...Array.from({ length: 250 }, (_, index) => ({
        x: 1000 + index * 40,
        y: 1000 + index * 40,
        width: 24,
        height: 24,
      })),
    ],
    { width: 160, height: 128, cellSize: 32, margin: 0 },
  );

  assert.ok(path.length > 1, "the route should detour around the one in-bounds obstacle");
  assert.deepEqual(path.at(-1), goal);
  const points = [start, ...path];
  for (let index = 1; index < points.length; index++) {
    assert.equal(
      segmentIntersectsExpandedRect(points[index - 1], points[index], obstacle, 0),
      false,
      "the optimized grid must preserve exact segment collision checks",
    );
  }
});

test("keeps obstacles outside the map from corrupting the collision grid", () => {
  const destination = { x: 112, y: 48 };
  const path = findPath(
    { x: 16, y: 48 },
    destination,
    [
      { x: -500, y: -500, width: 200, height: 200 },
      { x: 800, y: 800, width: 400, height: 400 },
    ],
    { width: 160, height: 128, cellSize: 32, margin: 0 },
  );

  assert.deepEqual(path, [destination]);
});


test("uses local obstacle candidates without missing edge or long-segment collisions", () => {
  const obstacles = [
    { x: 320, y: 192, width: 48, height: 48 },
    { x: 160, y: 64, width: 24, height: 24 },
    { x: 480, y: 320, width: 30, height: 30 },
    { x: 8, y: 190, width: 12, height: 70 },
    ...Array.from({ length: 180 }, (_, index) => ({
      x: 1200 + index * 30,
      y: 900 + index * 17,
      width: 20,
      height: 20,
    })),
  ];
  const start = { x: 24, y: 192 };
  const goal = { x: 616, y: 192 };
  const path = findPath(start, goal, obstacles, {
    width: 640,
    height: 384,
    minY: 16,
    cellSize: 32,
    margin: 4,
  });

  assert.ok(path.length > 1, "the central obstacle should require a safe detour");
  assert.deepEqual(path.at(-1), goal);
  const points = [start, ...path];
  for (let index = 1; index < points.length; index++) {
    for (const obstacle of obstacles) {
      assert.equal(
        segmentIntersectsExpandedRect(points[index - 1], points[index], obstacle, 4),
        false,
        "broadphase candidates must preserve exact collision safety",
      );
    }
  }
});
