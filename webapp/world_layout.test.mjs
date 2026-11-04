import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/world_layout.js";

const { createLayout } = globalThis.PeakWorldLayout;

test("builds a four-zone world larger than the viewport", () => {
  const layout = createLayout(900, 500, 1);
  assert.equal(layout.zoneCount, 4);
  assert.equal(layout.width, 3420);
  assert.equal(layout.height, 900);
  assert.equal(layout.zones.length, 4);
  assert.ok(layout.width > 900);
  assert.ok(layout.height > 500);
});

test("all ten worlds provide four named sub-zones", () => {
  for (let worldId = 1; worldId <= 10; worldId++) {
    const layout = createLayout(900, 500, worldId);
    assert.equal(layout.zones.length, 4);
    assert.equal(new Set(layout.zones.map(zone => zone.name)).size, 4);
    assert.ok(layout.zones.every(zone => zone.endX > zone.startX));
  }
});

test("spawn, NPC and gate remain inside the world with a safe progression order", () => {
  const layout = createLayout(900, 500, 5);
  assert.ok(layout.spawn.x < layout.npc.x);
  assert.ok(layout.npc.x < layout.portal.x);
  for (const point of [layout.spawn, layout.npc, layout.portal]) {
    assert.ok(point.x > 0 && point.x < layout.width);
    assert.ok(point.y > 0 && point.y < layout.height);
  }
});

test("encounter placements span multiple zones and remain inside map bounds", () => {
  const layout = createLayout(900, 500, 10);
  const monsters = layout.monsterPositions(3);
  assert.equal(monsters.length, 3);
  assert.ok(monsters[0].x < monsters[1].x);
  assert.ok(monsters[1].x < monsters[2].x);
  assert.ok(monsters[0].x < layout.zones[1].endX);
  assert.ok(monsters[2].x > layout.zones[3].startX);
  assert.ok(monsters.every(point => point.x > 0 && point.x < layout.width));
});

test("obstacles are finite, positive and within the playable map", () => {
  const layout = createLayout(1024, 640, 3);
  assert.ok(layout.obstacles.length >= 8);
  for (const obstacle of layout.obstacles) {
    assert.ok(Number.isFinite(obstacle.x) && Number.isFinite(obstacle.y));
    assert.ok(obstacle.width > 0 && obstacle.height > 0);
    assert.ok(obstacle.x > 0 && obstacle.x < layout.width);
    assert.ok(obstacle.y > layout.height * 0.46 && obstacle.y < layout.height);
  }
});

test("rejects invalid viewport, world and monster count inputs", () => {
  assert.throws(() => createLayout(0, 500, 1), RangeError);
  assert.throws(() => createLayout(900, Infinity, 1), RangeError);
  assert.throws(() => createLayout(900, 500, 11), RangeError);
  assert.throws(() => createLayout(900, 500, 1).monsterPositions(4), RangeError);
});
