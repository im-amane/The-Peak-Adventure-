(function (root) {
  "use strict";

  function findPath(start, goal, obstacles = [], options = {}) {
    const cellSize = Number.isFinite(options.cellSize) ? Math.max(12, options.cellSize) : 32;
    const width = Number.isFinite(options.width) ? options.width : 0;
    const height = Number.isFinite(options.height) ? options.height : 0;
    const minY = Number.isFinite(options.minY) ? options.minY : 0;
    const margin = Number.isFinite(options.margin) ? Math.max(0, options.margin) : 10;

    if (!start || !goal || !Number.isFinite(start.x) || !Number.isFinite(start.y) ||
        !Number.isFinite(goal.x) || !Number.isFinite(goal.y) || width <= 0 || height <= minY) {
      return [];
    }

    const cols = Math.ceil(width / cellSize);
    const rows = Math.ceil(height / cellSize);
    const toCell = point => ({
      x: Math.max(0, Math.min(cols - 1, Math.floor(point.x / cellSize))),
      y: Math.max(0, Math.min(rows - 1, Math.floor(point.y / cellSize))),
    });
    const startCell = toCell(start);
    const goalCell = toCell(goal);
    const key = (x, y) => x + "," + y;
    const startKey = key(startCell.x, startCell.y);
    const goalKey = key(goalCell.x, goalCell.y);

    const pointBlocked = point => {
      if (point.x < 0 || point.x > width || point.y < minY || point.y > height) return true;
      return obstacles.some(obstacle => {
        const halfWidth = Math.max(0, Number(obstacle.width) || 0) / 2 + margin;
        const halfHeight = Math.max(0, Number(obstacle.height) || 0) / 2 + margin;
        return Math.abs(point.x - obstacle.x) < halfWidth &&
          Math.abs(point.y - obstacle.y) < halfHeight;
      });
    };

    if (pointBlocked(start) || pointBlocked(goal)) return [];
    if (startKey === goalKey) return [{ x: goal.x, y: goal.y }];

    const blocked = (x, y) => {
      if (x < 0 || x >= cols || y < 0 || y >= rows) return true;
      const center = { x: x * cellSize + cellSize / 2, y: y * cellSize + cellSize / 2 };
      return center.y < minY || obstacles.some(obstacle => {
        const halfWidth = Math.max(0, Number(obstacle.width) || 0) / 2 + margin;
        const halfHeight = Math.max(0, Number(obstacle.height) || 0) / 2 + margin;
        return Math.abs(center.x - obstacle.x) < halfWidth &&
          Math.abs(center.y - obstacle.y) < halfHeight;
      });
    };

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

    const open = [{ x: startCell.x, y: startCell.y, g: 0, f: heuristic(startCell.x, startCell.y) }];
    const openKeys = new Set([startKey]);
    const cameFrom = new Map();
    const bestG = new Map([[startKey, 0]]);
    const maxNodes = Math.min(cols * rows, Number.isFinite(options.maxNodes) ? options.maxNodes : cols * rows);
    let visited = 0;

    while (open.length && visited < maxNodes) {
      open.sort((a, b) => a.f - b.f || a.g - b.g);
      const current = open.shift();
      const currentKey = key(current.x, current.y);
      openKeys.delete(currentKey);
      visited++;

      if (currentKey === goalKey) {
        const path = [];
        let cursor = currentKey;
        while (cursor !== startKey) {
          const [x, y] = cursor.split(",").map(Number);
          path.push({ x: x * cellSize + cellSize / 2, y: y * cellSize + cellSize / 2 });
          cursor = cameFrom.get(cursor);
          if (!cursor) return [];
        }
        path.reverse();
        if (path.length) path[path.length - 1] = { x: goal.x, y: goal.y };
        return path;
      }

      for (const [dx, dy, cost] of directions) {
        const nx = current.x + dx;
        const ny = current.y + dy;
        if (blocked(nx, ny)) continue;
        if (dx && dy && (blocked(current.x + dx, current.y) || blocked(current.x, current.y + dy))) continue;

        const nextKey = key(nx, ny);
        const tentativeG = current.g + cost;
        if (tentativeG >= (bestG.get(nextKey) ?? Infinity)) continue;
        cameFrom.set(nextKey, currentKey);
        bestG.set(nextKey, tentativeG);
        if (!openKeys.has(nextKey)) {
          open.push({ x: nx, y: ny, g: tentativeG, f: tentativeG + heuristic(nx, ny) });
          openKeys.add(nextKey);
        } else {
          const existing = open.find(node => node.x === nx && node.y === ny);
          if (existing) {
            existing.g = tentativeG;
            existing.f = tentativeG + heuristic(nx, ny);
          }
        }
      }
    }

    return [];
  }

  root.PeakPathfinding = { findPath };
})(typeof window !== "undefined" ? window : globalThis);
