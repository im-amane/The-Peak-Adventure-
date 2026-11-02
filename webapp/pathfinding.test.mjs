import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/pathfinding.js";

const { findPath } = globalThis.PeakPathfinding;

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
