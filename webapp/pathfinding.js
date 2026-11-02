(function (root) {
  "use strict";

  function findPath(start, goal, obstacles = [], options = {}) {
    const cellSize = Number.isFinite(options.cellSize) ? Math.max(12, options.cellSize) : 32;
    const width = Number.isFinite(options.width) ? options.width : 0;
    const height = Number.isFinite(options.height) ? options.height : 0;
    const minY = Number.isFinite(options.minY) ? options.minY : 0;
    const margin = Number.isFinite(options.margin) ? Math.max(0, options.margin) : 10;

    if (!start || !goal || !Number.isFinite(start.x) || !Number.isFinite(start.y) ||
        !Number.isFinite(goal.x) || !Number.isFinite(goal.y) || width <= 0 || height <= minY ||
        !Array.isArray(obstacles)) return [];

    const pointBlocked = point => {
      if (point.x < 0 || point.x > width || point.y < minY || point.y > height) return true;
      return obstacles.some(obstacle => {
        if (!obstacle || !Number.isFinite(obstacle.x) || !Number.isFinite(obstacle.y)) return false;
        const halfWidth = Math.max(0, Number(obstacle.width) || 0) / 2 + margin;
        const halfHeight = Math.max(0, Number(obstacle.height) || 0) / 2 + margin;
        return Math.abs(point.x - obstacle.x) < halfWidth &&
          Math.abs(point.y - obstacle.y) < halfHeight;
      });
    };
    if (pointBlocked(start) || pointBlocked(goal)) return [];

    // Grid-cell centers alone are not enough for collision safety: a diagonal
    // edge can clip a thin obstacle even when both adjacent cells are walkable.
    // Use a segment-vs-expanded-rectangle test for every movement edge.
    const segmentBlocked = (from, to) => obstacles.some(obstacle => {
      if (!obstacle || !Number.isFinite(obstacle.x) || !Number.isFinite(obstacle.y)) return false;
      const halfWidth = Math.max(0, Number(obstacle.width) || 0) / 2 + margin;
      const halfHeight = Math.max(0, Number(obstacle.height) || 0) / 2 + margin;
      const left = obstacle.x - halfWidth;
      const right = obstacle.x + halfWidth;
      const top = obstacle.y - halfHeight;
      const bottom = obstacle.y + halfHeight;
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      let enter = 0;
      let leave = 1;
      const p = [-dx, dx, -dy, dy];
      const q = [from.x - left, right - from.x, from.y - top, bottom - from.y];
      for (let index = 0; index < 4; index++) {
        if (p[index] === 0) {
          if (q[index] < 0) return false;
          continue;
        }
        const ratio = q[index] / p[index];
        if (p[index] < 0) enter = Math.max(enter, ratio);
        else leave = Math.min(leave, ratio);
        if (enter > leave) return false;
      }
      return true;
    });

    const cols = Math.ceil(width / cellSize);
    const rows = Math.ceil(height / cellSize);
    const totalCells = cols * rows;
    const toCell = point => ({
      x: Math.max(0, Math.min(cols - 1, Math.floor(point.x / cellSize))),
      y: Math.max(0, Math.min(rows - 1, Math.floor(point.y / cellSize))),
    });
    const startCell = toCell(start);
    const goalCell = toCell(goal);
    const indexOf = (x, y) => y * cols + x;
    const startIndex = indexOf(startCell.x, startCell.y);
    const goalIndex = indexOf(goalCell.x, goalCell.y);
    if (startIndex === goalIndex) return segmentBlocked(start, goal) ? [] : [{ x: goal.x, y: goal.y }];

    // Build the collision grid once. Re-testing every obstacle for every A-star
    // neighbor used to multiply collision work by the number of expanded nodes.
    const blocked = new Uint8Array(totalCells);
    for (let y = 0; y < rows; y++) {
      const centerY = y * cellSize + cellSize / 2;
      for (let x = 0; x < cols; x++) {
        const centerX = x * cellSize + cellSize / 2;
        if (centerY < minY || centerX > width || centerY > height) {
          blocked[indexOf(x, y)] = 1;
          continue;
        }
        for (const obstacle of obstacles) {
          if (!obstacle || !Number.isFinite(obstacle.x) || !Number.isFinite(obstacle.y)) continue;
          const halfWidth = Math.max(0, Number(obstacle.width) || 0) / 2 + margin;
          const halfHeight = Math.max(0, Number(obstacle.height) || 0) / 2 + margin;
          if (Math.abs(centerX - obstacle.x) < halfWidth &&
              Math.abs(centerY - obstacle.y) < halfHeight) {
            blocked[indexOf(x, y)] = 1;
            break;
          }
        }
      }
    }
    // The exact endpoints were validated above; their containing cells may
    // have blocked centers when an endpoint sits close to an obstacle edge.
    blocked[startIndex] = 0;
    blocked[goalIndex] = 0;

    const heuristic = (x, y) => {
      const dx = Math.abs(goalCell.x - x);
      const dy = Math.abs(goalCell.y - y);
      return Math.max(dx, dy) + (Math.SQRT2 - 1) * Math.min(dx, dy);
    };
    const directions = [
      [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
      [1, 1, Math.SQRT2], [1, -1, Math.SQRT2],
      [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2],
    ];
    const heap = [];
    const push = node => {
      heap.push(node);
      let i = heap.length - 1;
      while (i > 0) {
        const parent = (i - 1) >> 1;
        if (heap[parent].f < node.f || (heap[parent].f === node.f && heap[parent].g >= node.g)) break;
        heap[i] = heap[parent];
        i = parent;
      }
      heap[i] = node;
    };
    const pop = () => {
      const first = heap[0];
      const last = heap.pop();
      if (heap.length) {
        let i = 0;
        while (true) {
          let child = i * 2 + 1;
          if (child >= heap.length) break;
          if (child + 1 < heap.length && heap[child + 1].f < heap[child].f) child++;
          if (heap[child].f > last.f || (heap[child].f === last.f && heap[child].g <= last.g)) break;
          heap[i] = heap[child];
          i = child;
        }
        heap[i] = last;
      }
      return first;
    };

    const cameFrom = new Int32Array(totalCells);
    cameFrom.fill(-1);
    const bestG = new Float64Array(totalCells);
    bestG.fill(Infinity);
    const closed = new Uint8Array(totalCells);
    bestG[startIndex] = 0;
    push({ x: startCell.x, y: startCell.y, index: startIndex, g: 0, f: heuristic(startCell.x, startCell.y) });

    const requestedLimit = Number.isFinite(options.maxNodes) ? Math.floor(options.maxNodes) : 50000;
    const maxNodes = Math.max(1, Math.min(totalCells, requestedLimit, 50000));
    let visited = 0;

    while (heap.length && visited < maxNodes) {
      const current = pop();
      if (closed[current.index] || current.g !== bestG[current.index]) continue;
      closed[current.index] = 1;
      visited++;

      if (current.index === goalIndex) {
        const path = [];
        let cursor = goalIndex;
        while (cursor !== startIndex) {
          const x = cursor % cols;
          const y = Math.floor(cursor / cols);
          path.push({ x: x * cellSize + cellSize / 2, y: y * cellSize + cellSize / 2 });
          cursor = cameFrom[cursor];
          if (cursor < 0) return [];
        }
        path.reverse();
        const firstWaypoint = path[0];
        const lastWaypoint = path[path.length - 1];
        // Validate the partial-cell connectors too. Without these checks a
        // valid grid route could still clip an obstacle at its first/last edge.
        if (segmentBlocked(start, firstWaypoint) || segmentBlocked(lastWaypoint, goal)) return [];
        path[path.length - 1] = { x: goal.x, y: goal.y };
        return path;
      }

      for (const [dx, dy, cost] of directions) {
        const nx = current.x + dx;
        const ny = current.y + dy;
        if (nx < 0 || nx >= cols || ny < 0 || ny >= rows) continue;
        const nextIndex = indexOf(nx, ny);
        if (blocked[nextIndex] || closed[nextIndex]) continue;
        if (dx && dy && (blocked[indexOf(current.x + dx, current.y)] ||
            blocked[indexOf(current.x, current.y + dy)])) continue;
        const currentPoint = { x: current.x * cellSize + cellSize / 2, y: current.y * cellSize + cellSize / 2 };
        const nextPoint = { x: nx * cellSize + cellSize / 2, y: ny * cellSize + cellSize / 2 };
        if (segmentBlocked(currentPoint, nextPoint)) continue;

        const tentativeG = current.g + cost;
        if (tentativeG >= bestG[nextIndex]) continue;
        cameFrom[nextIndex] = current.index;
        bestG[nextIndex] = tentativeG;
        push({ x: nx, y: ny, index: nextIndex, g: tentativeG, f: tentativeG + heuristic(nx, ny) });
      }
    }

    return [];
  }

  root.PeakPathfinding = { findPath };
})(typeof window !== "undefined" ? window : globalThis);
