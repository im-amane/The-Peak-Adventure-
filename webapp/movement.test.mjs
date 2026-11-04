import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/movement.js";

const { moveWithCollisions, isBlocked } = globalThis.PeakMovement;

const bounds = { minX: 13, maxX: 287, minY: 113, maxY: 287 };

test("moves freely when no obstacles are present", () => {
  assert.deepEqual(
    moveWithCollisions(40, 140, 20, 10, [], bounds, 10),
    { x: 60, y: 150, blockedX: false, blockedY: false },
  );
});

test("stops at world bounds without leaving the playable area", () => {
  const result = moveWithCollisions(280, 280, 50, 50, [], bounds, 10);
  assert.equal(result.x, 287);
  assert.equal(result.y, 287);
});

test("does not tunnel through thin obstacles during a large movement step", () => {
  const obstacle = { x: 100, y: 150, width: 4, height: 80 };
  const result = moveWithCollisions(40, 150, 120, 0, [obstacle], bounds, 8);
  assert.ok(result.x <= obstacle.x - obstacle.width / 2 - 8);
  assert.equal(result.blockedX, true);
});

test("slides along an obstacle when one movement axis is blocked", () => {
  const obstacle = { x: 100, y: 150, width: 20, height: 100 };
  const result = moveWithCollisions(70, 150, 40, 30, [obstacle], bounds, 8);
  assert.ok(result.x <= obstacle.x - obstacle.width / 2 - 8);
  assert.ok(result.y > 150);
  assert.equal(result.blockedX, true);
});

test("keeps the hero outside expanded obstacle rectangles", () => {
  const obstacle = { x: 100, y: 160, width: 40, height: 40 };
  const result = moveWithCollisions(60, 160, 60, 0, [obstacle], bounds, 13);
  assert.equal(isBlocked(result.x, result.y, [obstacle], 13), false);
});

test("ignores malformed obstacles and non-finite movement values safely", () => {
  const result = moveWithCollisions(40, 140, NaN, Infinity, [null, { x: NaN, y: 0 }], bounds, 13);
  assert.deepEqual(result, { x: 40, y: 140, blockedX: false, blockedY: false });
});

test("resolves diagonal movement one axis at a time without corner clipping", () => {
  const obstacles = [{ x: 100, y: 100, width: 30, height: 30 }];
  const result = moveWithCollisions(70, 70, 40, 40, obstacles, { minX: 0, maxX: 200, minY: 0, maxY: 200 }, 8);
  assert.equal(isBlocked(result.x, result.y, obstacles, 8), false);
});

test("handles zero-size bounds and stationary input", () => {
  assert.deepEqual(
    moveWithCollisions(10, 10, 0, 0, [], { minX: 10, maxX: 10, minY: 20, maxY: 20 }, 13),
    { x: 10, y: 20, blockedX: false, blockedY: false },
  );
});
