import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/character_animation.js";

const { getPose } = globalThis.PeakCharacterAnimation;

test("selects idle pose below the movement threshold", () => {
  const pose = getPose(3, 4, true, 500);
  assert.equal(pose.state, "idle");
  assert.equal(pose.speed, 5);
  assert.equal(pose.bodyBob, 0);
});

test("selects walking pose and swings opposite limbs", () => {
  const pose = getPose(90, 0, false, 120);
  assert.equal(pose.state, "walk");
  assert.equal(pose.leftArm, -pose.rightArm);
  assert.equal(pose.leftLeg, -pose.rightLeg);
  assert.ok(pose.bodyBob >= 0);
});

test("selects running pose with a stronger gait", () => {
  const walk = getPose(120, 0, false, 150);
  const run = getPose(120, 0, true, 150);
  assert.equal(run.state, "run");
  assert.ok(Math.abs(run.gait) > Math.abs(walk.gait));
  assert.ok(run.bodyBob >= walk.bodyBob);
});

test("uses vertical speed without introducing horizontal body lean", () => {
  const pose = getPose(0, 100, false, 100);
  assert.equal(pose.state, "walk");
  assert.equal(pose.bodyLean, 0);
});

test("clamps body lean and tolerates malformed input", () => {
  const malformed = getPose(NaN, Infinity, true, NaN);
  assert.equal(malformed.state, "idle");
  assert.ok(Number.isFinite(malformed.gait));
  const fast = getPose(100000, 0, false, 500);
  assert.ok(Math.abs(fast.bodyLean) <= 0.08);
});

test("returns an immutable pose snapshot", () => {
  const pose = getPose(20, 0, false, 80);
  assert.equal(Object.isFrozen(pose), true);
});
