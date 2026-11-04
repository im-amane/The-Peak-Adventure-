(function (root) {
  "use strict";

  const DIRECTIONS = Object.freeze([
    "east", "southeast", "south", "southwest",
    "west", "northwest", "north", "northeast"
  ]);

  function getFacing(vx, vy, moving) {
    if (!moving) return "south";
    const angle = (Math.atan2(vy, vx) + Math.PI * 2) % (Math.PI * 2);
    const sector = Math.round(angle / (Math.PI / 4)) % 8;
    return DIRECTIONS[sector];
  }

  function getPose(velocityX, velocityY, sprinting, elapsedMs) {
    const vx = Number.isFinite(velocityX) ? velocityX : 0;
    const vy = Number.isFinite(velocityY) ? velocityY : 0;
    const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
    const speed = Math.hypot(vx, vy);
    const moving = speed > 8;
    const running = moving && sprinting === true;
    const state = running ? "run" : moving ? "walk" : "idle";
    const phase = elapsed / (running ? 46 : moving ? 76 : 430);
    const gait = moving
      ? Math.sin(phase) * (running ? 0.82 : 0.52)
      : Math.sin(phase) * 0.065;
    const frameIndex = moving
      ? Math.floor(((phase % (Math.PI * 2)) / (Math.PI / 2))) % 4
      : 0;

    return Object.freeze({
      state,
      speed,
      facing: getFacing(vx, vy, moving),
      frameIndex,
      gait,
      leftArm: -gait * 0.92,
      rightArm: gait * 0.92,
      leftLeg: gait * 0.78,
      rightLeg: -gait * 0.78,
      bodyBob: moving ? Math.abs(Math.sin(phase * 2)) * (running ? 2.2 : 1.1) : 0,
      bodyLean: moving ? Math.max(-0.08, Math.min(0.08, vx / 180 * 0.08)) : 0,
    });
  }

  root.PeakCharacterAnimation = Object.freeze({ getPose, directions: DIRECTIONS });
})(typeof globalThis !== "undefined" ? globalThis : window);
