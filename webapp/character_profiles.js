(function (root) {
  "use strict";

  const CLASS_PROFILES = Object.freeze({
    Knight: Object.freeze({ limbColor: 0x4d5b72, cloakColor: 0x344d68, armorColor: 0x71849c, accentColor: 0xd6e0e8, weapon: "sword", weaponColor: 0xc9d4dc }),
    Mage: Object.freeze({ limbColor: 0x49375f, cloakColor: 0x654b88, armorColor: 0x4c3d70, accentColor: 0x9edfff, weapon: "staff", weaponColor: 0x9b7044 }),
    Archer: Object.freeze({ limbColor: 0x36563f, cloakColor: 0x41684f, armorColor: 0x31543f, accentColor: 0xa7d38a, weapon: "bow", weaponColor: 0x9b7044 }),
    Berserker: Object.freeze({ limbColor: 0x6e332d, cloakColor: 0x8a4138, armorColor: 0x6e332d, accentColor: 0xf0a15a, weapon: "axe", weaponColor: 0x9b7044 }),
  });

  const OUTFITS = Object.freeze({
    traveler: Object.freeze({ cloak: 0x344d68, armor: 0x273a52, trim: 0xb6c5d2 }),
    knight: Object.freeze({ cloak: 0x596a86, armor: 0x71849c, trim: 0xd6e0e8 }),
    mage: Object.freeze({ cloak: 0x654b88, armor: 0x4c3d70, trim: 0xc5a9f0 }),
    ranger: Object.freeze({ cloak: 0x41684f, armor: 0x31543f, trim: 0xb5d59b }),
  });

  const SKIN_TONES = Object.freeze({ fair: 0xf1d2b5, warm: 0xe2b98d, tan: 0xb97850, deep: 0x70442f });
  const BODY_SCALES = Object.freeze({ slim: 0.9, balanced: 1, broad: 1.12 });
  const HAIR_STYLES = Object.freeze(["short", "long", "braided", "shaved"]);
  const RACES = Object.freeze(["Human", "Elf", "Dwarf", "Orc"]);
  const FACES = Object.freeze(["soft", "angular", "scarred"]);

  function resolveCharacterProfile(heroClass, appearance) {
    const selectedClass = Object.prototype.hasOwnProperty.call(CLASS_PROFILES, heroClass) ? heroClass : "Knight";
    const selectedAppearance = appearance && typeof appearance === "object" && !Array.isArray(appearance) ? appearance : {};
    const outfitName = Object.prototype.hasOwnProperty.call(OUTFITS, selectedAppearance.outfit) ? selectedAppearance.outfit : "traveler";
    const outfit = OUTFITS[outfitName];
    const skinName = Object.prototype.hasOwnProperty.call(SKIN_TONES, selectedAppearance.skin) ? selectedAppearance.skin : "warm";
    const bodyName = Object.prototype.hasOwnProperty.call(BODY_SCALES, selectedAppearance.body) ? selectedAppearance.body : "balanced";
    const race = RACES.includes(selectedAppearance.race) ? selectedAppearance.race : "Human";
    const hair = HAIR_STYLES.includes(selectedAppearance.hair) ? selectedAppearance.hair : "short";
    const face = FACES.includes(selectedAppearance.face) ? selectedAppearance.face : "soft";
    const classProfile = CLASS_PROFILES[selectedClass];

    return Object.freeze({
      className: selectedClass,
      weapon: classProfile.weapon,
      weaponColor: classProfile.weaponColor,
      limbColor: classProfile.limbColor,
      cloakColor: outfit.cloak,
      armorColor: outfit.armor,
      trimColor: outfit.trim,
      accentColor: classProfile.accentColor,
      skinColor: SKIN_TONES[skinName],
      hairColor: race === "Dwarf" ? 0x60402e : 0x382b2b,
      bodyScale: BODY_SCALES[bodyName],
      race,
      hair,
      face,
      outfit: outfitName,
    });
  }

  root.PeakCharacters = { resolveCharacterProfile, CLASS_PROFILES, OUTFITS };
})(typeof window !== "undefined" ? window : globalThis);
