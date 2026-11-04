(function (root) {
  "use strict";

  const DURATIONS = Object.freeze({ idle: Infinity, attack: 280, hit: 230, defeated: 680 });

  function getPose(state, elapsedMs, direction = 1) {
    const current = Object.prototype.hasOwnProperty.call(DURATIONS, state) ? state : "idle";
    const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
    const facing = Number.isFinite(direction) && direction < 0 ? -1 : 1;
    const duration = DURATIONS[current];
    const progress = current === "idle" ? 0 : Math.min(1, elapsed / duration);
    const envelope = current === "idle" || progress >= 1 ? 0 : Math.sin(Math.PI * progress);
    let offsetX = 0, offsetY = 0, scaleX = 1, scaleY = 1, rotation = 0, alpha = 1;

    if (current === "idle") {
      const phase = elapsed / 390;
      offsetY = Math.sin(phase) * 2.2;
      scaleY = 1 + Math.sin(phase * 2) * 0.025;
      scaleX = 1 - Math.sin(phase * 2) * 0.012;
    } else if (current === "attack") {
      offsetX = envelope * 18 * facing;
      offsetY = -envelope * 4;
      scaleX = 1 + envelope * 0.1;
      scaleY = 1 + envelope * 0.14;
      rotation = envelope * 0.13 * facing;
    } else if (current === "hit") {
      offsetX = -envelope * 12 * facing;
      offsetY = -envelope * 3;
      scaleX = 1 + envelope * 0.08;
      scaleY = 1 - envelope * 0.07;
      rotation = -envelope * 0.16 * facing;
      alpha = elapsed % 80 < 40 ? 0.48 : 1;
    } else {
      offsetY = progress * 20;
      scaleY = 1 - progress * 0.62;
      rotation = progress * 1.25 * facing;
      alpha = 1 - progress;
    }

    return Object.freeze({
      state: current, progress, complete: current !== "idle" && elapsed >= duration,
      offsetX, offsetY, scaleX, scaleY, rotation, alpha
    });
  }

  root.PeakMonsterAnimation = Object.freeze({ getPose, durations: DURATIONS });
})(typeof globalThis !== "undefined" ? globalThis : window);
