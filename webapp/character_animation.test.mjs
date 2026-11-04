import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/character_animation.js";

const { getPose, getAnimationKey, getFrameIndex, directions, states, framesPerClip } = globalThis.PeakCharacterAnimation;

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
  const walk = getPose(120, 0, false, 50);
  const run = getPose(120, 0, true, 50);
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

test("maps movement vectors to all eight facing directions", () => {
  const directions = [
    [100, 0, "east"], [100, 100, "southeast"],
    [0, 100, "south"], [-100, 100, "southwest"],
    [-100, 0, "west"], [-100, -100, "northwest"],
    [0, -100, "north"], [100, -100, "northeast"],
  ];
  for (const [vx, vy, expected] of directions) {
    assert.equal(getPose(vx, vy, false, 0).facing, expected);
  }
});

test("walk and run expose stable four-frame gait cycles", () => {
  const walkFrames = [0, 1, 2, 3].map(frame => getPose(90, 0, false, frame * 76 * Math.PI / 2).frameIndex);
  const runFrames = [0, 1, 2, 3].map(frame => getPose(120, 0, true, frame * 46 * Math.PI / 2).frameIndex);
  assert.deepEqual(walkFrames, [0, 1, 2, 3]);
  assert.deepEqual(runFrames, [0, 1, 2, 3]);
  assert.equal(getPose(0, 0, false, 500).frameIndex, 0);
});

test("only an explicit sprint flag selects the running state", () => {
  assert.equal(getPose(100, 0, "yes", 100).state, "walk");
  assert.equal(getPose(100, 0, true, 100).state, "run");
});


test("sprite sheet layout covers every state, direction and frame exactly once", () => {
  assert.deepEqual(states, ["idle", "walk", "run"]);
  assert.equal(directions.length, 8);
  assert.equal(framesPerClip, 4);
  const indices = new Set();
  for (const state of states) {
    for (const facing of directions) {
      assert.equal(getAnimationKey(state, facing), "peak-hero-" + state + "-" + facing);
      for (let frame = 0; frame < framesPerClip; frame += 1) {
        indices.add(getFrameIndex(state, facing, frame));
      }
    }
  }
  assert.equal(indices.size, 96);
  assert.deepEqual([...indices].sort((a, b) => a - b), Array.from({length: 96}, (_, i) => i));
});

test("sprite sheet clip lookup safely falls back for unknown state and direction", () => {
  assert.equal(getAnimationKey("fly", "up"), "peak-hero-idle-south");
  assert.equal(getFrameIndex("fly", "up", 99), getFrameIndex("idle", "south", 3));
});
