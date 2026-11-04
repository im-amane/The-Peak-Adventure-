import test from "node:test";
import assert from "node:assert/strict";
import "../webapp/character_profiles.js";

const { resolveCharacterProfile } = globalThis.PeakCharacters;

test("resolves a distinct deployable weapon profile for every hero class", () => {
  const expected = { Knight: "sword", Mage: "staff", Archer: "bow", Berserker: "axe" };
  for (const [heroClass, weapon] of Object.entries(expected)) {
    assert.equal(resolveCharacterProfile(heroClass, {}).weapon, weapon);
  }
});

test("maps persisted appearance selections to character render properties", () => {
  const profile = resolveCharacterProfile("Mage", {
    race: "Elf", skin: "deep", hair: "braided", face: "angular",
    body: "broad", outfit: "ranger",
  });
  assert.equal(profile.race, "Elf");
  assert.equal(profile.skinColor, 0x70442f);
  assert.equal(profile.hair, "braided");
  assert.equal(profile.face, "angular");
  assert.equal(profile.bodyScale, 1.12);
  assert.equal(profile.outfit, "ranger");
  assert.equal(profile.weapon, "staff");
  assert.equal(profile.armorColor, 0x31543f);
});

test("falls back safely for unknown classes and malformed appearance values", () => {
  const profile = resolveCharacterProfile("Unknown", { race: "Dragon", skin: "invisible", outfit: "godmode", body: "giant" });
  assert.equal(profile.className, "Knight");
  assert.equal(profile.weapon, "sword");
  assert.equal(profile.race, "Human");
  assert.equal(profile.skinColor, 0xe2b98d);
  assert.equal(profile.outfit, "traveler");
  assert.equal(profile.bodyScale, 1);
});

test("does not mutate caller-owned appearance data", () => {
  const appearance = { race: "Dwarf", skin: "tan", hair: "long", outfit: "knight", face: "scarred", body: "slim" };
  const original = { ...appearance };
  resolveCharacterProfile("Berserker", appearance);
  assert.deepEqual(appearance, original);
});

test("uses balanced defaults when appearance data is absent or non-object", () => {
  for (const value of [null, undefined, "Elf", []]) {
    const profile = resolveCharacterProfile("Archer", value);
    assert.equal(profile.race, "Human");
    assert.equal(profile.bodyScale, 1);
    assert.equal(profile.skinColor, 0xe2b98d);
  }
});
