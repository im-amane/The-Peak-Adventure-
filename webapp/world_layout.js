(function (root) {
  "use strict";

  const ZONE_NAMES = [
    ["Lantern Meadow", "Mossbound Grove", "Whispering Banks", "Old Village"],
    ["Dune Road", "Buried Market", "Glass Basin", "Sunken Temple"],
    ["Stormglass Pass", "Thunderwood", "Cloudbreak Ridge", "Spire Approach"],
    ["Outer Ruins", "Hollow Market", "Shadow Court", "The Fallen Throne"],
    ["Cinder Fields", "Ashen Quarry", "Magma Bridges", "Furnace Gate"],
    ["Snowline Trail", "Frozen Pines", "Glacier Hollow", "Starfall Shelf"],
    ["Rift Verge", "Shattered Causeway", "Echoing Chasm", "The Deep Wound"],
    ["Starlit Steps", "Astral Gardens", "Silent Archive", "Celestial Court"],
    ["Broken Hours", "Pendulum Gardens", "Clockwork District", "The Last Minute"],
    ["Pilgrim's Rise", "Cloud Stair", "First Light Terrace", "Origin Summit"],
  ];

  const OBSTACLE_POINTS = [
    [0.19, 0.56, 42, 56], [0.34, 0.82, 58, 34],
    [0.48, 0.53, 46, 54], [0.70, 0.84, 52, 30],
    [0.91, 0.58, 48, 58], [0.56, 0.79, 40, 36],
    [0.78, 0.49, 44, 38], [0.13, 0.89, 38, 42],
    [0.63, 0.60, 36, 50], [0.84, 0.88, 54, 30],
  ];

  function createLayout(viewportWidth, viewportHeight, worldId) {
    if (!Number.isFinite(viewportWidth) || viewportWidth <= 0 ||
        !Number.isFinite(viewportHeight) || viewportHeight <= 0) {
      throw new RangeError("Viewport dimensions must be positive finite numbers.");
    }
    if (!Number.isInteger(worldId) || worldId < 1 || worldId > ZONE_NAMES.length) {
      throw new RangeError("World ID must be an integer from 1 to 10.");
    }

    const width = Math.round(viewportWidth * 3.8);
    const height = Math.round(viewportHeight * 1.8);
    const zoneWidth = width / 4;
    const zones = ZONE_NAMES[worldId - 1].map((name, index) => ({
      id: index + 1,
      name,
      startX: Math.round(index * zoneWidth),
      endX: Math.round((index + 1) * zoneWidth),
      centerX: Math.round((index + 0.5) * zoneWidth),
    }));
    const obstacles = OBSTACLE_POINTS.map(([x, y, obstacleWidth, obstacleHeight]) => ({
      x: Math.round(width * x),
      y: Math.round(height * y),
      width: obstacleWidth,
      height: obstacleHeight,
    }));

    function monsterPositions(count) {
      if (!Number.isInteger(count) || count < 0 || count > 3) {
        throw new RangeError("Monster count must be between 0 and 3.");
      }
      const fractions = count === 1 ? [0.26] :
        count === 2 ? [0.25, 0.78] : [0.24, 0.57, 0.86];
      return fractions.map((x, index) => ({
        x: Math.round(width * x),
        y: Math.round(height * (index % 2 === 0 ? 0.68 : 0.76)),
      }));
    }

    return {
      width,
      height,
      zoneCount: zones.length,
      zones,
      spawn: { x: Math.round(width * 0.11), y: Math.round(height * 0.70) },
      npc: { x: Math.round(width * 0.40), y: Math.round(height * 0.70) },
      portal: { x: Math.round(width * 0.96), y: Math.round(height * 0.69) },
      obstacles,
      monsterPositions,
    };
  }

  root.PeakWorldLayout = Object.freeze({ createLayout, zoneNames: ZONE_NAMES });
})(typeof globalThis !== "undefined" ? globalThis : window);
