(function (root) {
  "use strict";

  function getPose(velocityX, velocityY, sprinting, elapsedMs) {
    const vx = Number.isFinite(velocityX) ? velocityX : 0;
    const vy = Number.isFinite(velocityY) ? velocityY : 0;
    const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
    const speed = Math.hypot(vx, vy);
    const moving = speed > 8;
    const running = moving && Boolean(sprinting);
    const state = running ? "run" : moving ? "walk" : "idle";
    const phase = elapsed / (running ? 46 : moving ? 76 : 430);
    const gait = moving
      ? Math.sin(phase) * (running ? 0.82 : 0.52)
      : Math.sin(phase) * 0.065;

    return Object.freeze({
      state,
      speed,
      gait,
      leftArm: -gait * 0.92,
      rightArm: gait * 0.92,
      leftLeg: gait * 0.78,
      rightLeg: -gait * 0.78,
      bodyBob: moving ? Math.abs(Math.sin(phase * 2)) * (running ? 2.2 : 1.1) : 0,
      bodyLean: moving ? Math.max(-0.08, Math.min(0.08, vx / 180 * 0.08)) : 0,
    });
  }

  root.PeakCharacterAnimation = Object.freeze({ getPose });
})(typeof globalThis !== "undefined" ? globalThis : window);
