import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/monster_animation.js";

const { getPose } = globalThis.PeakMonsterAnimation;

test("idle pose bobs without drifting horizontally", () => {
  const pose = getPose("idle", 120);
  assert.equal(pose.state, "idle");
  assert.equal(pose.offsetX, 0);
  assert.ok(Math.abs(pose.offsetY) <= 2.2);
  assert.equal(pose.complete, false);
});

test("attack lunges in the facing direction and returns to neutral", () => {
  const right = getPose("attack", 140, 1);
  const left = getPose("attack", 140, -1);
  assert.ok(right.offsetX > 0);
  assert.equal(left.offsetX, -right.offsetX);
  assert.ok(right.scaleY > 1);
  assert.equal(getPose("attack", 280).complete, true);
  assert.equal(getPose("attack", 280).offsetX, 0);
});

test("hit reaction recoils opposite the facing direction", () => {
  const pose = getPose("hit", 115, 1);
  assert.ok(pose.offsetX < 0);
  assert.ok(pose.rotation < 0);
  assert.ok(pose.alpha === 0.48 || pose.alpha === 1);
});

test("defeated pose fades, falls and shrinks monotonically", () => {
  const early = getPose("defeated", 170, -1);
  const late = getPose("defeated", 510, -1);
  assert.ok(late.offsetY > early.offsetY);
  assert.ok(late.rotation < early.rotation);
  assert.ok(late.alpha < early.alpha);
  assert.ok(late.scaleY < early.scaleY);
  assert.equal(getPose("defeated", 680).complete, true);
});

test("unknown states and malformed timestamps safely fall back to idle", () => {
  const pose = getPose("teleport", NaN, Infinity);
  assert.equal(pose.state, "idle");
  assert.ok(Number.isFinite(pose.offsetY));
  assert.equal(getPose("hit", -100).progress, 0);
});

test("pose snapshots are immutable", () => {
  assert.equal(Object.isFrozen(getPose("idle", 0)), true);
});
