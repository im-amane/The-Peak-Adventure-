(function (root) {
  "use strict";

  const DIRECTIONS = Object.freeze([
    "east", "southeast", "south", "southwest",
    "west", "northwest", "north", "northeast"
  ]);
  const STATES = Object.freeze(["idle", "walk", "run"]);
  const FRAME_WIDTH = 64;
  const FRAME_HEIGHT = 80;
  const FRAMES_PER_CLIP = 4;
  let sheetSequence = 0;

  function getFacing(vx, vy, moving) {
    if (!moving) return "south";
    const angle = (Math.atan2(vy, vx) + Math.PI * 2) % (Math.PI * 2);
    const sector = Math.round(angle / (Math.PI / 4)) % 8;
    return DIRECTIONS[sector];
  }

  function getAnimationKey(state, facing) {
    const safeState = STATES.includes(state) ? state : "idle";
    const safeFacing = DIRECTIONS.includes(facing) ? facing : "south";
    return "peak-hero-" + safeState + "-" + safeFacing;
  }

  function getFrameIndex(state, facing, frame) {
    const stateIndex = Math.max(0, STATES.indexOf(STATES.includes(state) ? state : "idle"));
    const directionIndex = Math.max(0, DIRECTIONS.indexOf(DIRECTIONS.includes(facing) ? facing : "south"));
    const frameIndex = Number.isInteger(frame) ? Math.max(0, Math.min(FRAMES_PER_CLIP - 1, frame)) : 0;
    return (stateIndex * DIRECTIONS.length + directionIndex) * FRAMES_PER_CLIP + frameIndex;
  }

  function color(value, fallback) {
    return Number.isInteger(value) ? "#" + value.toString(16).padStart(6, "0").slice(-6) : fallback;
  }

  function drawFrame(ctx, profile, state, facing, frame) {
    const angles = {
      east: Math.PI / 2, southeast: Math.PI / 4, south: 0,
      southwest: -Math.PI / 4, west: -Math.PI / 2,
      northwest: -3 * Math.PI / 4, north: Math.PI,
      northeast: 3 * Math.PI / 4
    };
    const phase = frame * Math.PI / 2;
    const amplitude = state === "run" ? 0.78 : state === "walk" ? 0.48 : 0.055;
    const gait = Math.sin(phase) * amplitude;
    const bob = state === "idle" ? Math.sin(phase) * 0.8 : Math.abs(Math.sin(phase * 2)) * (state === "run" ? 2.1 : 1.1);
    const skin = color(profile.skinColor, "#e2b98d");
    const hair = color(profile.hairColor, "#382b2b");
    const cloak = color(profile.cloakColor, "#344d68");
    const armor = color(profile.armorColor, "#71849c");
    const trim = color(profile.trimColor, "#d6e0e8");
    const limb = color(profile.limbColor, "#4d5b72");
    const accent = color(profile.accentColor, "#d6e0e8");
    const weapon = color(profile.weaponColor, "#c9d4dc");

    ctx.save();
    ctx.translate(FRAME_WIDTH / 2, FRAME_HEIGHT / 2 + 5 + bob);
    ctx.rotate(angles[facing]);
    ctx.scale(profile.bodyScale || 1, 1);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    // Ground shadow and articulated legs.
    ctx.fillStyle = "rgba(12,18,25,0.28)";
    ctx.beginPath(); ctx.ellipse(0, 25, 13, 4, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#202b38"; ctx.lineWidth = 8;
    ctx.beginPath(); ctx.moveTo(-6, 9); ctx.lineTo(-7 + gait * 9, 22); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(6, 9); ctx.lineTo(7 - gait * 9, 22); ctx.stroke();
    ctx.strokeStyle = "#29313c"; ctx.lineWidth = 5;
    ctx.beginPath(); ctx.moveTo(-7 + gait * 9, 22); ctx.lineTo(-10 + gait * 9, 25); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(7 - gait * 9, 22); ctx.lineTo(10 - gait * 9, 25); ctx.stroke();

    // Arms swing opposite the legs, with class-colored sleeves.
    ctx.strokeStyle = limb; ctx.lineWidth = 7;
    ctx.beginPath(); ctx.moveTo(-11, -5); ctx.lineTo(-17 - gait * 10, 8); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(11, -5); ctx.lineTo(17 + gait * 10, 8); ctx.stroke();

    // Layered outfit and belt.
    ctx.fillStyle = cloak; ctx.strokeStyle = "#172334"; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.roundRect(-13, -12, 26, 28, 6); ctx.fill(); ctx.stroke();
    ctx.fillStyle = armor; ctx.beginPath(); ctx.roundRect(-10, -8, 20, 19, 4); ctx.fill();
    ctx.strokeStyle = trim; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(-11, 12); ctx.lineTo(11, 12); ctx.stroke();
    ctx.fillStyle = accent; ctx.fillRect(-3, 8, 6, 5);

    // Head, face and selected cosmetic details.
    ctx.fillStyle = skin; ctx.strokeStyle = "#172334"; ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (profile.face === "angular") {
      ctx.moveTo(0, -35); ctx.lineTo(10, -28); ctx.lineTo(8, -17);
      ctx.lineTo(0, -13); ctx.lineTo(-8, -17); ctx.lineTo(-10, -28); ctx.closePath();
    } else {
      ctx.arc(0, -25, 10, 0, Math.PI * 2);
    }
    ctx.fill(); ctx.stroke();
    if (profile.race === "Elf") {
      ctx.fillStyle = skin;
      ctx.beginPath(); ctx.moveTo(-7, -28); ctx.lineTo(-20, -37); ctx.lineTo(-12, -20); ctx.fill();
      ctx.beginPath(); ctx.moveTo(7, -28); ctx.lineTo(20, -37); ctx.lineTo(12, -20); ctx.fill();
    } else if (profile.race === "Orc") {
      ctx.fillStyle = "#f0e4c8";
      ctx.beginPath(); ctx.moveTo(-6, -18); ctx.lineTo(-3, -11); ctx.lineTo(-1, -19); ctx.fill();
      ctx.beginPath(); ctx.moveTo(6, -18); ctx.lineTo(3, -11); ctx.lineTo(1, -19); ctx.fill();
    } else if (profile.race === "Dwarf") {
      ctx.fillStyle = "#68452f";
      ctx.beginPath(); ctx.moveTo(-8, -19); ctx.lineTo(0, -8); ctx.lineTo(8, -19); ctx.fill();
    }
    ctx.fillStyle = hair;
    if (profile.hair !== "shaved") {
      ctx.beginPath(); ctx.arc(0, -30, 10, Math.PI, Math.PI * 2); ctx.fill();
      if (profile.hair === "long") {
        ctx.fillRect(-10, -30, 4, 17); ctx.fillRect(6, -30, 4, 17);
      } else if (profile.hair === "braided") {
        ctx.beginPath(); ctx.arc(-11, -18, 3, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(11, -18, 3, 0, Math.PI * 2); ctx.fill();
      }
    } else {
      ctx.fillRect(-7, -34, 14, 2);
    }
    ctx.fillStyle = "#171b25";
    ctx.beginPath(); ctx.arc(-4, -25, 1.3, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(4, -25, 1.3, 0, Math.PI * 2); ctx.fill();
    if (profile.face === "scarred") {
      ctx.strokeStyle = "#8b3d42"; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(-7, -21); ctx.lineTo(-1, -15); ctx.stroke();
    }

    // Signature class weapon is drawn into every frame.
    ctx.strokeStyle = weapon; ctx.lineWidth = 3;
    if (profile.weapon === "staff") {
      ctx.beginPath(); ctx.moveTo(19, 12); ctx.lineTo(21, -29); ctx.stroke();
      ctx.fillStyle = accent; ctx.beginPath(); ctx.arc(21, -32, 5, 0, Math.PI * 2); ctx.fill();
    } else if (profile.weapon === "bow") {
      ctx.beginPath(); ctx.arc(19, -15, 12, -Math.PI / 2, Math.PI / 2); ctx.stroke();
      ctx.strokeStyle = trim; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(19, -27); ctx.lineTo(19, -3); ctx.stroke();
    } else if (profile.weapon === "axe") {
      ctx.beginPath(); ctx.moveTo(18, 12); ctx.lineTo(22, -22); ctx.stroke();
      ctx.fillStyle = "#b7c2cc"; ctx.beginPath(); ctx.moveTo(20, -22); ctx.lineTo(34, -29); ctx.lineTo(31, -11); ctx.closePath(); ctx.fill();
    } else {
      ctx.beginPath(); ctx.moveTo(18, 12); ctx.lineTo(27, -25); ctx.stroke();
      ctx.fillStyle = "#dce6ef"; ctx.beginPath(); ctx.moveTo(27, -25); ctx.lineTo(31, -36); ctx.lineTo(23, -28); ctx.closePath(); ctx.fill();
      ctx.fillStyle = accent; ctx.beginPath(); ctx.roundRect(-22, 1, 8, 15, 2); ctx.fill();
    }
    ctx.restore();
  }

  function createSpriteSheet(scene, profile, x, y) {
    if (!root.document || !scene || !scene.textures || !scene.add) return null;
    const canvas = root.document.createElement("canvas");
    canvas.width = FRAME_WIDTH * FRAMES_PER_CLIP;
    canvas.height = FRAME_HEIGHT * STATES.length * DIRECTIONS.length;
    const context = canvas.getContext && canvas.getContext("2d");
    if (!context) return null;

    STATES.forEach((state, stateIndex) => {
      DIRECTIONS.forEach((facing, directionIndex) => {
        for (let frame = 0; frame < FRAMES_PER_CLIP; frame += 1) {
          context.save();
          context.translate(frame * FRAME_WIDTH, (stateIndex * DIRECTIONS.length + directionIndex) * FRAME_HEIGHT);
          drawFrame(context, profile, state, facing, frame);
          context.restore();
        }
      });
    });

    const key = "peak-character-sheet-" + (++sheetSequence);
    scene.textures.addSpriteSheet(key, canvas, {
      frameWidth: FRAME_WIDTH, frameHeight: FRAME_HEIGHT
    });
    const sprite = scene.add.sprite(x, y, key, 0).setOrigin(0.5, 0.58).setDepth(10);
    sprite.characterProfile = profile;
    sprite.characterAnimations = Object.freeze(
      STATES.flatMap((state) => DIRECTIONS.map((facing) => {
        const animationKey = getAnimationKey(state, facing);
        const start = getFrameIndex(state, facing, 0);
        scene.anims.create({
          key: key + "-" + animationKey,
          frames: scene.anims.generateFrameNumbers(key, { start, end: start + FRAMES_PER_CLIP - 1 }),
          frameRate: state === "idle" ? 5 : state === "walk" ? 10 : 15,
          repeat: -1
        });
        return { state, facing, key: key + "-" + animationKey };
      }))
    );
    sprite.characterSheetKey = key;
    sprite.play(key + "-" + getAnimationKey("idle", "south"));
    return sprite;
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
      ? Math.floor(((phase % (Math.PI * 2)) / (Math.PI / 2))) % FRAMES_PER_CLIP
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

  root.PeakCharacterAnimation = Object.freeze({
    getPose, getAnimationKey, getFrameIndex, createSpriteSheet,
    directions: DIRECTIONS, states: STATES,
    frameWidth: FRAME_WIDTH, frameHeight: FRAME_HEIGHT, framesPerClip: FRAMES_PER_CLIP
  });
})(typeof globalThis !== "undefined" ? globalThis : window);
