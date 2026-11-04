(function (root) {
  "use strict";

  function finite(value, fallback) {
    return Number.isFinite(value) ? value : fallback;
  }

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function isBlocked(x, y, obstacles, radius) {
    if (!Array.isArray(obstacles)) return false;
    return obstacles.some(obstacle => {
      if (!obstacle || !Number.isFinite(obstacle.x) || !Number.isFinite(obstacle.y)) return false;
      const halfWidth = Math.max(0, finite(obstacle.width, 0)) / 2 + radius;
      const halfHeight = Math.max(0, finite(obstacle.height, 0)) / 2 + radius;
      return x > obstacle.x - halfWidth && x < obstacle.x + halfWidth &&
        y > obstacle.y - halfHeight && y < obstacle.y + halfHeight;
    });
  }

  function moveWithCollisions(x, y, deltaX, deltaY, obstacles, bounds, radius) {
    const safeBounds = bounds || {};
    const safeRadius = clamp(finite(radius, 13), 0, 128);
    const minX = finite(safeBounds.minX, 0);
    const maxX = Math.max(minX, finite(safeBounds.maxX, minX));
    const minY = finite(safeBounds.minY, 0);
    const maxY = Math.max(minY, finite(safeBounds.maxY, minY));
    let nextX = clamp(finite(x, minX), minX, maxX);
    let nextY = clamp(finite(y, minY), minY, maxY);
    const dx = finite(deltaX, 0);
    const dy = finite(deltaY, 0);
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(dy)) / Math.max(1, safeRadius / 2)));
    const stepX = dx / steps;
    const stepY = dy / steps;
    let blockedX = false;
    let blockedY = false;

    for (let index = 0; index < steps; index++) {
      const candidateX = clamp(nextX + stepX, minX, maxX);
      if (candidateX !== nextX && !isBlocked(candidateX, nextY, obstacles, safeRadius)) {
        nextX = candidateX;
      } else if (candidateX !== nextX) {
        blockedX = true;
      }

      const candidateY = clamp(nextY + stepY, minY, maxY);
      if (candidateY !== nextY && !isBlocked(nextX, candidateY, obstacles, safeRadius)) {
        nextY = candidateY;
      } else if (candidateY !== nextY) {
        blockedY = true;
      }
    }

    return { x: nextX, y: nextY, blockedX, blockedY };
  }

  function integrateVelocity(vx, vy, inputX, inputY, deltaSeconds, options = {}) {
    const dt = clamp(finite(deltaSeconds, 0), 0, 0.05);
    let ix = finite(inputX, 0);
    let iy = finite(inputY, 0);
    const inputLength = Math.hypot(ix, iy);
    if (inputLength > 1) { ix /= inputLength; iy /= inputLength; }
    let x = finite(vx, 0);
    let y = finite(vy, 0);
    const maxSpeed = clamp(finite(options.maxSpeed, 180), 0, 1000);
    const acceleration = clamp(finite(options.acceleration, 900), 0, 5000);
    const friction = clamp(finite(options.friction, 1200), 0, 5000);

    if (inputLength > 0) {
      const targetX = ix * maxSpeed;
      const targetY = iy * maxSpeed;
      const changeX = targetX - x;
      const changeY = targetY - y;
      const changeLength = Math.hypot(changeX, changeY);
      const maxChange = acceleration * dt;
      if (changeLength > maxChange && changeLength > 0) {
        x += changeX / changeLength * maxChange;
        y += changeY / changeLength * maxChange;
      } else {
        x = targetX;
        y = targetY;
      }
    } else {
      const speed = Math.hypot(x, y);
      const nextSpeed = Math.max(0, speed - friction * dt);
      if (speed > 0) {
        x *= nextSpeed / speed;
        y *= nextSpeed / speed;
      }
    }

    const speed = Math.hypot(x, y);
    if (speed > maxSpeed && speed > 0) {
      x *= maxSpeed / speed;
      y *= maxSpeed / speed;
    }
    return { x, y };
  }

  root.PeakMovement = { moveWithCollisions, isBlocked, integrateVelocity };
})(typeof window !== "undefined" ? window : globalThis);
