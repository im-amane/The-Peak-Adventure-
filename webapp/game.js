(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) { tg.ready(); tg.expand(); }
  const initData = tg ? tg.initData : "";
  const ui = {
    coins: document.getElementById("coins"),
    premiumGems: document.getElementById("premium-gems"),
    premiumShopItems: document.getElementById("premium-shop-items"),
    premiumGemBalance: document.getElementById("premium-gem-balance"),
    name: document.getElementById("hero-name"),
    heroClass: document.getElementById("hero-class"),
    level: document.getElementById("level"),
    hp: document.getElementById("hp"),
    hpTrack: document.getElementById("hp-track"),
    hpFill: document.getElementById("hp-fill"),
    stamina: document.getElementById("stamina"),
    staminaTrack: document.getElementById("stamina-track"),
    staminaFill: document.getElementById("stamina-fill"),
    mana: document.getElementById("mana"),
    manaTrack: document.getElementById("mana-track"),
    manaFill: document.getElementById("mana-fill"),
    xpTrack: document.getElementById("xp-track"),
    xp: document.getElementById("xp-fill"),
    region: document.getElementById("region"),
    monster: document.getElementById("monster-label"),
    status: document.getElementById("status"),
    encounter: document.getElementById("encounter"),
    interact: document.getElementById("interact-npc"),
    portalTravel: document.getElementById("portal-travel"),
    battlePanel: document.getElementById("battle-panel"),
    battleName: document.getElementById("battle-name"),
    battleHp: document.getElementById("battle-hp"),
    battleHpFill: document.getElementById("battle-hp-fill"),
    battleMessage: document.getElementById("battle-message"),
    potionCount: document.getElementById("potion-count"),
    appearanceStatus: document.getElementById("appearance-status"),
    questList: document.getElementById("quest-list"),
    dailyMissionList: document.getElementById("daily-mission-list"),
    worldNavigation: document.getElementById("world-navigation"),
    weeklyQuestList: document.getElementById("weekly-quest-list"),
    socialOverview: document.getElementById("social-overview"),
    matchmakingStatus: document.getElementById("matchmaking-status"),
    matchmakingDetails: document.getElementById("matchmaking-details"),
    matchmakingCasual: document.getElementById("matchmaking-casual"),
    matchmakingRanked: document.getElementById("matchmaking-ranked"),
    matchmakingCancel: document.getElementById("matchmaking-cancel"),
    matchmakingRefresh: document.getElementById("matchmaking-refresh"),
    socialSearchForm: document.getElementById("social-search-form"),
    socialSearchInput: document.getElementById("social-player-search"),
    socialSearchResults: document.getElementById("social-search-results"),
    guildChatPanel: document.getElementById("guild-chat-panel"),
    guildChatMessages: document.getElementById("guild-chat-messages"),
    guildChatForm: document.getElementById("guild-chat-form"),
    guildChatInput: document.getElementById("guild-chat-input"),
    guildChatLoad: document.getElementById("guild-chat-load"),
    partyCreate: document.getElementById("party-create"),
    partyTargetId: document.getElementById("party-target-id"),
    partyInvite: document.getElementById("party-invite"),
    partyLeave: document.getElementById("party-leave"),
    dungeonStatus: document.getElementById("dungeon-status")
  };
  const worldPalettes = [
    {sky:0x8fae91,ground:0x5d8059,accent:0xd6c98b},
    {sky:0xd6a96f,ground:0xa97842,accent:0xf1d79a},
    {sky:0x7b9eae,ground:0x57747b,accent:0xd7e3d7},
    {sky:0x6a6c83,ground:0x343b4f,accent:0xb7a8c8},
    {sky:0xb65e3d,ground:0x673b2e,accent:0xf0a15a},
    {sky:0x8faeb7,ground:0x597c8c,accent:0xe4f1f2},
    {sky:0x4b466f,ground:0x25233e,accent:0x9c8dc9},
    {sky:0x6577a8,ground:0x3b456f,accent:0xe4d7a2},
    {sky:0x44445b,ground:0x242537,accent:0xb4a4d2},
    {sky:0x4b354c,ground:0x251c31,accent:0xe4c17d}
  ];
  const worldNames = ["Whispering Meadow","Ashen Desert","Stormglass Highlands","Hollow Kingdom","Ember Abyss","Frostfang Peaks","Primordial Rift","Celestial Ruins","Eternal Hour","Origin Realm"];
  let gameState = null;
  let sceneRef = null;
  let pendingSceneEffects = [];
  const pressedDirections = new Set();
  let sprintTouchHeld = false;
  let sprintKeyboardHeld = false;
  let nearMonster = false;
  let nearNpc = false;
  let nearPortal = false;
  let requestInFlight = false;
  let phaserGame = null;
  let soundEnabled = true;
  let audioContext = null;
  let ambientNodes = [];
  let ambientGain = null;

  function clearMovementInput() {
    pressedDirections.clear();
    sprintTouchHeld = false;
    sprintKeyboardHeld = false;
    const control = document.getElementById("sprint-control");
    if (control) control.setAttribute("aria-pressed", "false");
  }

  window.addEventListener("keydown", event => {
    if (event.code === "ShiftLeft" || event.code === "ShiftRight") sprintKeyboardHeld = true;
  });
  window.addEventListener("keyup", event => {
    if (event.code === "ShiftLeft" || event.code === "ShiftRight") sprintKeyboardHeld = false;
  });
  window.addEventListener("blur", clearMovementInput);
  window.addEventListener("pagehide", clearMovementInput);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearMovementInput();
  });

  function startAmbientMusic() {
    if (!soundEnabled || !audioContext || audioContext.state !== "running" || ambientNodes.length) return;
    const now = audioContext.currentTime;
    ambientGain = audioContext.createGain();
    ambientGain.gain.setValueAtTime(0.0001, now);
    ambientGain.gain.exponentialRampToValueAtTime(0.012, now + 1.8);
    ambientGain.connect(audioContext.destination);
    [110, 164.81, 220, 329.63].forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const voiceGain = audioContext.createGain();
      oscillator.type = index === 3 ? "triangle" : "sine";
      oscillator.frequency.setValueAtTime(frequency, now);
      voiceGain.gain.setValueAtTime(index === 3 ? 0.12 : 0.22, now);
      oscillator.connect(voiceGain);
      voiceGain.connect(ambientGain);
      oscillator.start(now);
      ambientNodes.push(oscillator);
    });
  }

  function stopAmbientMusic() {
    if (!audioContext || !ambientGain) return;
    const now = audioContext.currentTime;
    ambientGain.gain.cancelScheduledValues(now);
    ambientGain.gain.setTargetAtTime(0.0001, now, 0.18);
    ambientNodes.forEach(node => {
      try { node.stop(now + 0.8); } catch (_) {}
    });
    ambientNodes = [];
    ambientGain = null;
  }

  function playSound(kind) {
    if (!soundEnabled) return;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      audioContext = audioContext || new AudioContextClass();
      if (audioContext.state === "suspended") audioContext.resume().then(startAmbientMusic).catch(() => {});
      else startAmbientMusic();
      const notes = {encounter:[260,390],attack:[180,110],skill:[330,660,880],potion:[440,620],victory:[523,659,784],error:[140]};
      const sequence = notes[kind] || [300];
      const start = audioContext.currentTime;
      sequence.forEach((frequency,index) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        oscillator.type = kind === "skill" ? "triangle" : "sine";
        oscillator.frequency.setValueAtTime(frequency,start+index*0.075);
        gain.gain.setValueAtTime(0.0001,start+index*0.075);
        gain.gain.exponentialRampToValueAtTime(0.07,start+index*0.075+0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001,start+index*0.075+0.16);
        oscillator.connect(gain); gain.connect(audioContext.destination);
        oscillator.start(start+index*0.075); oscillator.stop(start+index*0.075+0.17);
      });
    } catch (_) { /* Audio is optional; gameplay must never depend on it. */ }
  }

  function flushSceneEffects() {
    if(!sceneRef || !sceneRef.hero || !pendingSceneEffects.length)return;
    const effects=pendingSceneEffects.splice(0);
    effects.forEach(effect=>{
      if(effect==="levelup"&&sceneRef.playLevelUpAnimation)sceneRef.playLevelUpAnimation();
      if(effect==="death"&&sceneRef.playDeathAnimation)sceneRef.playDeathAnimation();
      if(effect==="respawn"&&sceneRef.playRespawnAnimation)sceneRef.playRespawnAnimation();
    });
  }

  function updateHudMeter(track, fill, current, maximum) {
    if (!track || !fill) return;
    const safeMaximum = Number.isFinite(maximum) && maximum > 0 ? maximum : 0;
    const safeCurrent = Number.isFinite(current) ? Math.max(0, Math.min(safeMaximum, current)) : 0;
    const percentage = safeMaximum > 0 ? (safeCurrent / safeMaximum) * 100 : 0;
    track.setAttribute("aria-valuenow", String(Math.round(percentage)));
    track.setAttribute("aria-valuetext", safeMaximum > 0
      ? safeCurrent + " of " + safeMaximum
      : "Unavailable");
    fill.style.width = percentage + "%";
  }

  function applyState(data, message) {
    const previousRegion = gameState ? gameState.region : null;
    const previousMonster = gameState ? gameState.monster.level : null;
    const previousLevel = gameState ? gameState.level : null;
    const previousHp = gameState ? gameState.hp : null;
    gameState = data;
    if(previousLevel !== null && data.level > previousLevel)pendingSceneEffects.push("levelup");
    if(previousHp !== null && previousHp > 0 && data.hp <= 0)pendingSceneEffects.push("death");
    if(previousHp !== null && previousHp <= 0 && data.hp > 0)pendingSceneEffects.push("respawn");
    ui.name.textContent = data.first_name || "Adventurer";
    ui.heroClass.textContent = data.class_selected ? data.hero_class + " · " + data.weapon : "Choose a class in chat";
    ui.level.textContent = "Lv. " + data.level;
    ui.hp.textContent = "❤️ " + data.hp + " / " + data.max_hp;
    updateHudMeter(ui.hpTrack, ui.hpFill, data.hp, data.max_hp);
    if (data.mana && ui.mana) {
      ui.mana.textContent = data.mana.mana + " / " + data.mana.max_mana;
      updateHudMeter(ui.manaTrack, ui.manaFill, data.mana.mana, data.mana.max_mana);
    }
    if (data.stamina && ui.stamina) {
      ui.stamina.textContent = data.stamina.stamina + " / " + data.stamina.max_stamina;
      updateHudMeter(ui.staminaTrack, ui.staminaFill, data.stamina.stamina, data.stamina.max_stamina);
    }
    ui.coins.textContent = data.coins;
    if(ui.premiumGems)ui.premiumGems.textContent = Number.isFinite(data.premium_gems) ? data.premium_gems : 0;
    const onlineCount = document.getElementById("online-count");
    if (onlineCount) onlineCount.textContent = "🌐 " + (data.online_count || 0) + " online";
    const inventory = {
      "inventory-coins": data.coins,
      "inventory-potions": data.potions,
      "inventory-weapon": data.weapon,
      "inventory-attack": "+" + data.weapon_attack + " ATK",
      "inventory-armor": data.armor,
      "inventory-defense": "+" + data.armor_defense + " DEF"
    };
    Object.entries(inventory).forEach(([id,value]) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    });
    if (data.appearance) {
      ["race","skin","hair","face","body","outfit"].forEach(key => {
        const field = document.getElementById("appearance-" + key);
        if (field) field.value = data.appearance[key];
      });
    }
    renderQuests(data.quests || []);
    renderDailyMissions(data.daily_missions || []);
    renderWeeklyQuests(data.weekly_quests || []);
    renderWorldNavigation(data.worlds || [], data.landmark || null, data.battle_active);
    renderSocial(data.social || {});
    renderMatchmaking(data.matchmaking || null);
    renderDungeon(data.dungeon || null, data.dungeons || []);
    renderMaterials(data.materials || {});
    renderStory(data.story || []);
    if (data.settings) {
      const notifications = document.getElementById("setting-notifications");
      const privacy = document.getElementById("setting-privacy");
      if (notifications) notifications.value = data.settings.notifications_enabled ? "1" : "0";
      if (privacy) privacy.value = data.settings.profile_visibility;
      if (typeof data.settings.sound_enabled !== "undefined") {
        soundEnabled = Boolean(data.settings.sound_enabled);
        const soundButton = document.getElementById("sound-toggle");
        if (soundButton) {
          soundButton.setAttribute("aria-pressed", String(soundEnabled));
          soundButton.textContent = soundEnabled ? "🔊 Sound" : "🔇 Muted";
        }
      }
    }
    updateHudMeter(ui.xpTrack, ui.xp, data.xp, data.xp_required);
    ui.region.textContent = data.region;
    ui.monster.textContent = "Lv. " + data.monster.level + " · " + data.monster.name;
    const battle = data.battle;
    ui.battlePanel.hidden = !battle;
    document.querySelectorAll("[data-action]").forEach(button => {
      const action = button.dataset.action;
      button.disabled = !battle || requestInFlight
        || (action === "skill" && (data.skill_cd > 0 || !data.mana || data.mana.mana < 30))
        || (action === "potion" && (data.potions <= 0 || data.hp >= data.max_hp));
      if (action === "skill") button.textContent = data.skill_cd > 0 ? "⏳ Skill (" + data.skill_cd + ")" : (!data.mana || data.mana.mana < 30 ? "🔮 Need 30 Mana" : "✨ Skill");
      if (action === "potion") button.textContent = "🧪 Potion (" + data.potions + ")";
    });
    if (battle) {
      ui.battleName.textContent = (battle.elite ? "💀 ELITE · " : (battle.evolved ? "✨ ASCENDED · " : "")) + battle.name + " · Lv." + battle.level + (battle.phase > 1 ? " · Phase " + battle.phase : "");
      ui.battleHp.textContent = "❤️ " + battle.hp + " / " + battle.max_hp;
      const enemyHpPercent = Number.isFinite(battle.max_hp) && battle.max_hp > 0
        ? Math.max(0, Math.min(100, battle.hp / battle.max_hp * 100)) : 0;
      ui.battleHpFill.style.width = enemyHpPercent + "%";
      ui.potionCount.textContent = "Health potions: " + data.potions + " · " + battle.special_move;
      ui.battleMessage.textContent = message ? message.replace(/<[^>]*>/g, "") : battle.story;
    }
    ui.status.textContent = (message ? message.replace(/<[^>]*>/g, "") : "") || (battle
      ? "Battle in progress. Choose your action below."
      : data.class_selected ? "The wilds are waiting. Find the creature on the map."
      : "Choose a hero class in the Telegram chat before exploring.");
    ui.encounter.disabled = !nearMonster || !data.class_selected || data.battle_active;
    ui.interact.disabled = !nearNpc || data.battle_active;
    ui.encounter.textContent = data.battle_active ? "⚔️ Battle in progress" : nearMonster ? "⚔️ Challenge Monster" : "⚔️ Find the monster";
    if (sceneRef && previousRegion && (previousRegion !== data.region || previousMonster !== data.monster.level)) {
      sceneRef.scene.restart();
    } else {
      flushSceneEffects();
    }
  }






  function renderStory(chapters) {
    if (!ui.storyChapters) return;
    ui.storyChapters.replaceChildren();
    chapters.forEach(chapter=>{
      const card=document.createElement("article");card.className="story-chapter";
      const title=document.createElement("h3");title.textContent=(chapter.completed?"✅ ":chapter.unlocked?"🔓 ":"🔒 ")+chapter.id+". "+chapter.title;card.appendChild(title);
      const meta=document.createElement("p");meta.textContent=chapter.npc+" · World "+chapter.world+" · Lv."+chapter.level;card.appendChild(meta);
      if (chapter.unlocked || chapter.completed) {
        const scene=document.createElement("p");scene.textContent=chapter.scene;card.appendChild(scene);
      } else {
        const locked=document.createElement("p");
        locked.textContent=chapter.requires_party
          ? "Reach level "+chapter.level+", complete the previous chapter, and join a party."
          : "Reach level "+chapter.level+" and complete the previous chapter.";
        card.appendChild(locked);
      }
      const choices=document.createElement("div");choices.className="story-choices";
      if (chapter.completed) {
        const selected=document.createElement("p");selected.textContent="Your choice: "+chapter.choices[chapter.choice];card.appendChild(selected);
        if (chapter.reward_claimed) {
          const claimed=document.createElement("p");claimed.textContent="Reward claimed.";card.appendChild(claimed);
        } else {
          const claim=document.createElement("button");claim.className="story-choice";claim.textContent="Claim "+chapter.reward+" coins";
          claim.addEventListener("click",()=>storyAction({action:"claim",chapter_id:chapter.id}));choices.appendChild(claim);
        }
      } else if (chapter.unlocked) {
        Object.entries(chapter.choices).forEach(([choiceId,description])=>{
          const button=document.createElement("button");button.className="story-choice";button.textContent=description;
          button.addEventListener("click",()=>storyAction({action:"choose",chapter_id:chapter.id,choice_id:choiceId}));
          choices.appendChild(button);
        });
      }
      card.appendChild(choices);ui.storyChapters.appendChild(card);
    });
  }

  async function storyAction(payload) {
    if (requestInFlight) return;
    requestInFlight=true;
    try {
      const result=await postApi("/api/story",payload);
      applyState(result.state,result.message);
    } catch(error) {
      showStatus(error.message);
    } finally {
      requestInFlight=false;
    }
  }

  function renderMaterials(materials) {
    if (!ui.inventoryMaterials) return;
    ui.inventoryMaterials.replaceChildren();
    const names={iron_ore:"Iron Ore",ember_shard:"Ember Shard",frost_crystal:"Frost Crystal",void_essence:"Void Essence",star_dust:"Star Dust"};
    const entries=Object.entries(materials).filter(([,quantity])=>quantity>0);
    if (!entries.length) {
      const empty=document.createElement("span"); empty.className="small"; empty.textContent="Crafting materials: defeat monsters to collect resources.";
      ui.inventoryMaterials.appendChild(empty); return;
    }
    entries.forEach(([id,quantity])=>{
      const chip=document.createElement("span"); chip.className="material-chip";
      chip.textContent=(names[id]||id)+" ×"+quantity; ui.inventoryMaterials.appendChild(chip);
    });
  }

  function renderDungeon(dungeon, choices) {
    if (!ui.dungeonStatus) return;
    ui.dungeonStatus.replaceChildren();
    const heading=document.createElement("h3");
    heading.textContent="🗝️ Dungeon Expedition";
    ui.dungeonStatus.appendChild(heading);
    if (dungeon && dungeon.status !== "abandoned") {
      const summary=document.createElement("p");
      summary.className="small";
      summary.textContent=dungeon.name+" · Room "+dungeon.room+"/"+dungeon.room_count+" · "+dungeon.status.toUpperCase()
        +(dungeon.status==="active" ? " · Defeat a monster at Lv."+dungeon.target_level+" or higher to advance." : " · Rewards: "+dungeon.reward_coins+" coins and "+dungeon.reward_potions+" potions.");
      ui.dungeonStatus.appendChild(summary);
      if (dungeon.status==="completed") {
        const claim=document.createElement("button");
        claim.type="button"; claim.className="dungeon-action"; claim.dataset.dungeonAction="claim";
        claim.textContent="🎁 Claim dungeon reward";
        ui.dungeonStatus.appendChild(claim);
      } else if (dungeon.status==="active") {
        const abandon=document.createElement("button");
        abandon.type="button"; abandon.className="dungeon-action secondary"; abandon.dataset.dungeonAction="abandon";
        abandon.textContent="Leave dungeon";
        ui.dungeonStatus.appendChild(abandon);
      }
      return;
    }
    const intro=document.createElement("p");
    intro.className="small";
    intro.textContent=dungeon && dungeon.status==="abandoned"
      ? "Your last expedition was abandoned. Choose another dungeon or retry it."
      : "Choose an unlocked dungeon. Each expedition has three guardian rooms.";
    ui.dungeonStatus.appendChild(intro);
    const available=(Array.isArray(choices)?choices:[]).filter(item=>item.unlocked&&!item.claimed);
    if (!available.length) {
      const empty=document.createElement("p"); empty.className="small";
      empty.textContent="No unclaimed dungeons are unlocked yet. Explore and level up to reveal more.";
      ui.dungeonStatus.appendChild(empty);
      return;
    }
    available.forEach(item=>{
      const row=document.createElement("div"); row.className="dungeon-choice";
      const label=document.createElement("span");
      label.textContent="World "+item.world+" · "+item.name+" · Lv."+item.min_level;
      const button=document.createElement("button");
      button.type="button"; button.className="dungeon-action";
      button.dataset.dungeonAction="enter"; button.dataset.dungeonId=String(item.id);
      button.textContent="Enter";
      row.append(label,button); ui.dungeonStatus.appendChild(row);
    });
  }

  async function performDungeonAction(button) {
    if (requestInFlight || !gameState) return;
    const action=button.dataset.dungeonAction;
    const dungeonId=Number(button.dataset.dungeonId);
    if (!["enter","abandon","claim"].includes(action)) return;
    requestInFlight=true;
    ui.dungeonStatus.querySelectorAll("button").forEach(item=>item.disabled=true);
    try {
      const result=await postApi("/api/dungeon",action==="enter"?{action,dungeon_id:dungeonId}:{action});
      applyState(result.state,result.message);
    } catch(error) {
      const notice=document.createElement("p"); notice.className="small"; notice.textContent=error.message;
      ui.dungeonStatus.appendChild(notice);
      await loadState().catch(()=>null);
    } finally {
      requestInFlight=false;
      if(gameState) applyState(gameState);
    }
  }

  function renderPremiumShop(data) {
    if(!ui.premiumShopItems)return;
    ui.premiumShopItems.replaceChildren();
    const balance=Number(data.premium_gems)||0;
    if(ui.premiumGemBalance)ui.premiumGemBalance.textContent=balance+" gems";
    (data.premium_shop||[]).forEach(item=>{
      const card=document.createElement("article");card.className="premium-shop-item";
      const title=document.createElement("strong");title.textContent=item.title+" · "+item.cost+" gems";
      const description=document.createElement("p");description.textContent=item.description;
      const button=document.createElement("button");button.type="button";button.textContent="Buy";
      button.dataset.premiumItem=item.item_id;button.disabled=balance<item.cost;
      card.append(title,description,button);ui.premiumShopItems.appendChild(card);
    });
  }

  function renderMatchmaking(queue) {
    if (!ui.matchmakingStatus) return;
    ui.matchmakingDetails.replaceChildren();
    const queued = Boolean(queue && queue.status === "queued");
    const matched = Boolean(queue && queue.status === "matched");
    if (!queue) {
      ui.matchmakingStatus.textContent = "Not in a queue. Choose Casual or Ranked to find an opponent.";
    } else if (queued) {
      const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - queue.queued_at));
      const minutes = Math.floor(elapsed / 60);
      const seconds = elapsed % 60;
      ui.matchmakingStatus.textContent = "🔎 Searching in " + queue.mode.toUpperCase() + " queue · " + minutes + ":" + String(seconds).padStart(2, "0") + " elapsed";
    } else if (matched) {
      ui.matchmakingStatus.textContent = "⚔️ MATCH FOUND · " + queue.mode.toUpperCase();
    } else {
      const labels = {cancelled:"Queue cancelled",expired:"Queue expired",completed:"Previous match completed"};
      ui.matchmakingStatus.textContent = labels[queue.status] || "Queue status: " + queue.status;
    }
    if (queue) {
      const detail = document.createElement("p");
      detail.className = "matchmaking-detail";
      detail.textContent = queue.mode.toUpperCase() + " · Level " + queue.player_level + " · Rating " + queue.rating;
      ui.matchmakingDetails.appendChild(detail);
      if (matched) {
        const opponent = document.createElement("p");
        opponent.className = "matchmaking-opponent";
        opponent.textContent = "Opponent ID: " + queue.opponent_id + " · Level " + queue.opponent_level + " · Rating gap " + queue.rating_gap;
        ui.matchmakingDetails.appendChild(opponent);
      }
      const battle = queue.battle;
      if (battle) {
        const panel = document.createElement("section");
        panel.className = "matchmaking-battle";
        panel.setAttribute("aria-live", "polite");
        const heading = document.createElement("h4");
        heading.textContent = battle.status === "active" ? "⚔️ Live PvP Battle" : "🏁 PvP Battle Complete";
        panel.appendChild(heading);
        const opponentLine = document.createElement("p");
        opponentLine.textContent = battle.opponent_name + " · Lv." + battle.opponent_level;
        panel.appendChild(opponentLine);
        const hpLine = document.createElement("p");
        hpLine.textContent = "Your HP: " + battle.my_hp + " / " + battle.my_max_hp + " · Opponent HP: " + battle.opponent_hp + " / " + battle.opponent_max_hp;
        panel.appendChild(hpLine);
        const turnLine = document.createElement("p");
        turnLine.className = "small";
        const secondsLeft = Math.max(0, Number(battle.turn_time_remaining) || 0);
        turnLine.textContent = battle.status === "finished"
          ? (battle.is_winner ? "You won this match." : (battle.winner_id ? "Your opponent won this match." : "Match closed."))
          : (battle.is_my_turn
            ? "Your turn. Choose an action · " + secondsLeft + "s remaining."
            : "Waiting for your opponent · " + secondsLeft + "s remaining.");
        panel.appendChild(turnLine);
        if (battle.status === "active") {
          [["attack","⚔️ Attack"],["skill","✨ Class Skill"],["surrender","🏳️ Surrender"]].forEach(([action,label]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "social-action";
            button.textContent = action === "skill"
              ? ((gameState.skill_cd || 0) > 0
                ? "⏳ Skill (" + gameState.skill_cd + ")"
                : (!gameState.mana || gameState.mana.mana < 30 ? "🔮 Need 30 Mana" : label))
              : label;
            button.dataset.pvpAction = action;
            button.dataset.matchId = String(battle.match_id);
            button.disabled = requestInFlight || !battle.is_my_turn
              || (action === "skill" && ((gameState.skill_cd || 0) > 0 || !gameState.mana || gameState.mana.mana < 30));
            panel.appendChild(button);
          });
        }
        ui.matchmakingDetails.appendChild(panel);
      }
    }
    const active = Boolean(queue && ["queued", "matched"].includes(queue.status));
    const disabled = requestInFlight || !gameState || !gameState.class_selected || gameState.battle_active || active;
    ui.matchmakingCasual.disabled = disabled;
    ui.matchmakingRanked.disabled = disabled;
    ui.matchmakingCancel.hidden = !queued;
    ui.matchmakingCancel.disabled = requestInFlight || !queued;
    ui.matchmakingRefresh.disabled = requestInFlight || !gameState;
  }

  async function runMatchmakingAction(action, mode) {
    if (requestInFlight || !gameState) return;
    requestInFlight = true;
    [ui.matchmakingCasual,ui.matchmakingRanked,ui.matchmakingCancel,ui.matchmakingRefresh].forEach(button => { if (button) button.disabled = true; });
    try {
      const payload = action === "join" ? {action,mode} : {action};
      const result = await postApi("/api/matchmaking", payload);
      applyState(result.state, result.message);
    } catch (error) {
      ui.status.textContent = error.message;
      await loadState().catch(() => null);
    } finally {
      requestInFlight = false;
      if (gameState) applyState(gameState);
    }
  }
  async function runMatchmakingBattleAction(action, matchId) {
    if (requestInFlight || !gameState) return;
    requestInFlight = true;
    try {
      const result = await postApi("/api/matchmaking", {action,match_id:matchId});
      applyState(result.state, result.message);
    } catch (error) {
      ui.status.textContent = error.message;
      await loadState().catch(() => null);
    } finally {
      requestInFlight = false;
      if (gameState) applyState(gameState);
    }
  }

  function renderSocial(social) {
    if (!ui.socialOverview) return;
    ui.socialOverview.replaceChildren();
    const addCard=(title,lines)=>{
      const card=document.createElement("article"); card.className="social-card";
      const heading=document.createElement("h3"); heading.textContent=title; card.appendChild(heading);
      if (!lines.length) lines=["No entries yet."];
      lines.forEach(line=>{
        const p=document.createElement("p"); p.className="social-member"; p.textContent=line; card.appendChild(p);
      });
      ui.socialOverview.appendChild(card);
      return card;
    };
    const addAction=(parent,label,action,extra={})=>{
      const button=document.createElement("button"); button.type="button"; button.className="social-action";
      button.textContent=label; button.dataset.socialAction=action;
      Object.entries(extra).forEach(([key,value])=>button.dataset[key]=String(value));
      parent.appendChild(button);
    };
    const friendsCard=addCard("Friends",(social.friends||[]).map(x=>x.username+" · Lv."+x.level));
    (social.friends||[]).forEach(friend=>{
      addAction(friendsCard,"Trade with "+friend.username,"trade_create",{targetId:friend.user_id});
      addAction(friendsCard,"Remove "+friend.username,"friend_remove",{friendId:friend.user_id});
    });
    const requests=social.friend_requests||[];
    if(requests.length){
      const card=addCard("Incoming friend requests",requests.map(x=>x.username+" · Lv."+x.level));
      requests.forEach(request=>{
        addAction(card,"Accept","friend_accept",{requestId:request.request_id});
        addAction(card,"Decline","friend_decline",{requestId:request.request_id});
      });
    }
    const party=social.party;
    addCard("Party",party ? ["Party #"+party.party_id,...party.members.map(x=>x.username+" · Lv."+x.level)] : ["Not in a party."]);
    const invites=social.party_invites||[];
    if(invites.length){
      const card=addCard("Party invitations",invites.map(x=>x.username+" invited you to party #"+x.party_id));
      invites.forEach(invite=>{
        addAction(card,"Accept","party_accept",{inviteId:invite.invite_id});
        addAction(card,"Decline","party_decline",{inviteId:invite.invite_id});
      });
    }
    const guild=social.guild;
    addCard("Guild",guild ? [guild.name+" · Lv."+guild.level+" · "+guild.role,...guild.members.map(x=>x.username+" · "+x.role)] : ["Not in a guild. Use /guild create in Telegram."]);
    if(ui.guildChatPanel)ui.guildChatPanel.hidden=!guild;
    const guildInvites=social.pending_guild_invites||[];
    if(guildInvites.length){
      const card=addCard("Guild invitations",guildInvites.map(x=>x.guild_name+" · invited by "+x.inviter_name));
      guildInvites.forEach(invite=>{
        addAction(card,"Accept","guild_accept",{inviteId:invite.invite_id});
        addAction(card,"Decline","guild_decline",{inviteId:invite.invite_id});
      });
    }
    const pendingTrades=social.pending_trades||[];
    if(pendingTrades.length){
      const card=addCard("Trade invitations",pendingTrades.map(trade=>
        (trade.incoming?"From ":"To ")+trade.other_username+" · #"+trade.trade_id
      ));
      pendingTrades.forEach(trade=>{
        if(trade.incoming){
          addAction(card,"Accept trade","trade_accept",{tradeId:trade.trade_id});
          addAction(card,"Decline","trade_decline",{tradeId:trade.trade_id});
        }else{
          const waiting=document.createElement("p");waiting.className="small";
          waiting.textContent="Waiting for "+trade.other_username+" to respond to trade #"+trade.trade_id+".";
          card.appendChild(waiting);
          addAction(card,"Cancel invitation","trade_cancel",{tradeId:trade.trade_id});
        }
      });
    }else{
      addCard("Trading",["No pending trade invitations."]);
    }
    const openTrades=social.open_trades||[];
    if(openTrades.length){
      const card=addCard("Active trades",openTrades.map(trade=>
        "#"+trade.trade_id+" with "+trade.other_username+
        " · Your offer: "+trade.my_coins+" coins, "+trade.my_potions+" potions"+
        " · Their offer: "+trade.their_coins+" coins, "+trade.their_potions+" potions"+
        " · Gear: "+(trade.my_weapon||"no weapon")+"/"+(trade.my_armor||"no armor")+
        " ↔ "+(trade.their_weapon||"no weapon")+"/"+(trade.their_armor||"no armor")+
        " · Confirmations: "+(trade.my_confirmed?"✅":"⌛")+" / "+(trade.their_confirmed?"✅":"⌛")
      ));
      openTrades.forEach(trade=>{
        const form=document.createElement("form");form.className="social-trade-offer-form";
        const coinsLabel=document.createElement("label");coinsLabel.textContent="Coins to offer";
        const coinsInput=document.createElement("input");coinsInput.type="number";coinsInput.min="0";coinsInput.step="1";coinsInput.required=true;coinsInput.value=String(trade.my_coins);coinsInput.inputMode="numeric";
        const potionsLabel=document.createElement("label");potionsLabel.textContent="Potions to offer";
        const potionsInput=document.createElement("input");potionsInput.type="number";potionsInput.min="0";potionsInput.step="1";potionsInput.required=true;potionsInput.value=String(trade.my_potions);potionsInput.inputMode="numeric";
        const weaponLabel=document.createElement("label");weaponLabel.className="trade-equipment-choice";
        const weaponInput=document.createElement("input");weaponInput.type="checkbox";weaponInput.checked=Boolean(trade.my_weapon);
        weaponLabel.append(weaponInput,document.createTextNode(" Offer equipped weapon ("+(gameState.weapon||"none")+")"));
        const armorLabel=document.createElement("label");armorLabel.className="trade-equipment-choice";
        const armorInput=document.createElement("input");armorInput.type="checkbox";armorInput.checked=Boolean(trade.my_armor);
        armorLabel.append(armorInput,document.createTextNode(" Offer equipped armor ("+(gameState.armor||"none")+")"));
        const save=document.createElement("button");save.type="submit";save.textContent="Save offer";
        form.append(coinsLabel,coinsInput,potionsLabel,potionsInput,weaponLabel,armorLabel,save);
        form.addEventListener("submit",async event=>{
          event.preventDefault();
          const coins=Number(coinsInput.value),potions=Number(potionsInput.value);
          if(!Number.isSafeInteger(coins)||coins<0||!Number.isSafeInteger(potions)||potions<0){
            ui.status.textContent="Enter valid whole-number amounts for your trade offer.";return;
          }
          save.disabled=true;
          try{await runSocialAction({
            action:"trade_offer",trade_id:trade.trade_id,coins,potions,
            offer_weapon:weaponInput.checked,offer_armor:armorInput.checked
          });}
          catch(_){save.disabled=false;}
        });
        card.appendChild(form);
        addAction(card,trade.my_confirmed?"Confirmed":"Confirm trade #"+trade.trade_id,"trade_confirm",{tradeId:trade.trade_id});
        addAction(card,"Cancel trade #"+trade.trade_id,"trade_cancel",{tradeId:trade.trade_id});
      });
    }
    if(ui.partyCreate)ui.partyCreate.hidden=Boolean(party);
    if(ui.partyInvite)ui.partyInvite.hidden=!party;
    if(ui.partyTargetId)ui.partyTargetId.hidden=!party;
    if(ui.partyLeave)ui.partyLeave.hidden=!party;
  }

  function renderGuildChat(messages) {
    if(!ui.guildChatMessages)return;
    ui.guildChatMessages.replaceChildren();
    if(!Array.isArray(messages)||!messages.length){
      const empty=document.createElement("p");empty.className="small";empty.textContent="No guild messages yet.";
      ui.guildChatMessages.appendChild(empty);return;
    }
    messages.forEach(item=>{
      const row=document.createElement("article");row.className="guild-chat-message";
      const author=document.createElement("strong");author.textContent=item.username||"Adventurer";
      const body=document.createElement("p");body.textContent=item.message||"";
      const stamp=document.createElement("time");stamp.textContent=item.created_at||"";
      row.append(author,body,stamp);ui.guildChatMessages.appendChild(row);
    });
    ui.guildChatMessages.scrollTop=ui.guildChatMessages.scrollHeight;
  }

  function renderPlayerSearch(players) {
    if(!ui.socialSearchResults)return;
    ui.socialSearchResults.replaceChildren();
    if(!players.length){
      const empty=document.createElement("p");empty.className="small";empty.textContent="No visible players found.";
      ui.socialSearchResults.appendChild(empty);return;
    }
    players.forEach(player=>{
      const row=document.createElement("div");row.className="social-search-result";
      const label=document.createElement("span");label.textContent=player.username+" · Lv."+player.level;
      const button=document.createElement("button");button.type="button";button.textContent="Add friend";
      button.dataset.socialAction="friend_request";button.dataset.targetId=String(player.user_id);
      row.append(label,button);ui.socialSearchResults.appendChild(row);
    });
  }

  async function runSocialAction(payload) {
    if(requestInFlight||!gameState)return;
    requestInFlight=true;
    try{
      const result=await postApi("/api/social",payload);
      applyState(result.state,result.message);
      return result;
    }catch(error){
      ui.status.textContent=error.message;
      throw error;
    }finally{
      requestInFlight=false;
    }
  }

  function renderQuests(quests) {
    if (!ui.questList) return;
    ui.questList.replaceChildren();
    if (!quests.length) {
      const empty=document.createElement("p"); empty.className="small";
      empty.textContent="Your adventure quests will appear here."; ui.questList.appendChild(empty); return;
    }
    quests.forEach(quest => {
      const card=document.createElement("article"); card.className="quest-card";
      const title=document.createElement("h3"); title.textContent=quest.title;
      const description=document.createElement("p"); description.textContent=quest.description;
      const progress=document.createElement("p");
      progress.textContent=quest.claimed ? "🎁 Reward claimed" : quest.completed
        ? "✅ Completed · Reward ready" : "Progress: "+Math.min(quest.progress,quest.target)+"/"+quest.target;
      const track=document.createElement("div"); track.className="quest-progress";
      const fill=document.createElement("span");
      fill.style.width=Math.max(0,Math.min(100,quest.progress/quest.target*100))+"%";
      track.appendChild(fill); card.append(title,description,progress,track);
      if (quest.completed && !quest.claimed) {
        const button=document.createElement("button"); button.type="button"; button.textContent="Claim "+quest.coins+" coins";
        button.addEventListener("click",()=>claimQuest(quest.id,button)); card.appendChild(button);
      }
      ui.questList.appendChild(card);
    });
  }

  function renderWorldNavigation(worlds, landmark, battleActive) {
    if (!ui.worldNavigation) return;
    ui.worldNavigation.replaceChildren();
    const heading=document.createElement("h3");
    heading.textContent="🌀 World Travel";
    ui.worldNavigation.appendChild(heading);
    const list=document.createElement("div");
    list.className="world-choice-list";
    worlds.forEach(world=>{
      const button=document.createElement("button");
      button.type="button";
      button.className="world-choice"+(world.current?" current":"");
      button.dataset.worldTravelId=String(world.id);
      button.disabled=!world.unlocked||world.current||Boolean(battleActive);
      const marker=world.current?"📍":world.unlocked?"🔓":"🔒";
      button.textContent=marker+" "+world.id+". "+world.name+" · Lv."+world.min_level;
      list.appendChild(button);
    });
    ui.worldNavigation.appendChild(list);
    if(landmark){
      const card=document.createElement("div");
      card.className="landmark-card";
      const title=document.createElement("strong");
      title.textContent=(landmark.discovered?"✅ ":"🗿 ")+landmark.landmark;
      const description=document.createElement("p");
      description.textContent=landmark.description;
      card.append(title,description);
      if(!landmark.discovered){
        const button=document.createElement("button");
        button.type="button";button.className="landmark-action";
        button.dataset.worldDiscover="1";button.textContent="Discover landmark";
        card.appendChild(button);
      }else{
        const note=document.createElement("p");note.className="small";
        note.textContent="Landmark discovered. Its reward has already been collected.";
        card.appendChild(note);
      }
      ui.worldNavigation.appendChild(card);
    }
  }

  async function performWorldAction(button) {
    if(requestInFlight||!gameState)return;
    const worldId=button.dataset.worldTravelId;
    const discover=button.dataset.worldDiscover==="1";
    if(!worldId&&!discover)return;
    requestInFlight=true;
    ui.worldNavigation.querySelectorAll("button").forEach(item=>item.disabled=true);
    try{
      const payload=discover?{action:"discover"}:{action:"travel",world_id:Number(worldId)};
      const result=await postApi("/api/world",payload);
      applyState(result.state,result.message);
    }catch(error){
      ui.status.textContent=error.message;
      await loadState().catch(()=>null);
    }finally{
      requestInFlight=false;
      if(gameState)applyState(gameState);
    }
  }

  function renderDailyMissions(missions) {
    if (!ui.dailyMissionList) return;
    ui.dailyMissionList.replaceChildren();
    if (!missions.length) {
      const empty=document.createElement("p"); empty.className="small";
      empty.textContent="No daily missions are available right now.";
      ui.dailyMissionList.appendChild(empty); return;
    }
    missions.forEach(mission=>{
      const card=document.createElement("article"); card.className="daily-mission-card";
      const title=document.createElement("h4"); title.textContent=(mission.claimed?"✅ ":mission.completed?"🎁 ":"🔹 ")+mission.title;
      const description=document.createElement("p"); description.textContent=mission.description;
      const progress=document.createElement("p"); progress.className="small";
      progress.textContent="Progress: "+mission.progress+"/"+mission.target+" · Reward: "+mission.coins+" coins + "+mission.potions+" potions";
      const track=document.createElement("div"); track.className="quest-progress";
      const fill=document.createElement("span");
      fill.style.width=Math.max(0,Math.min(100,mission.progress/mission.target*100))+"%";
      track.appendChild(fill); card.append(title,description,progress,track);
      if(mission.completed&&!mission.claimed){
        const button=document.createElement("button"); button.type="button";
        button.className="dungeon-action"; button.dataset.dailyMissionId=mission.id;
        button.textContent="Claim reward";
        card.appendChild(button);
      }
      ui.dailyMissionList.appendChild(card);
    });
  }

  function renderWeeklyQuests(quests) {
    if (!ui.weeklyQuestList) return;
    ui.weeklyQuestList.replaceChildren();
    if (!quests.length) {
      const empty=document.createElement("p"); empty.className="small";
      empty.textContent="No weekly quests are available right now.";
      ui.weeklyQuestList.appendChild(empty); return;
    }
    quests.forEach(quest=>{
      const card=document.createElement("article"); card.className="daily-mission-card";
      const title=document.createElement("h4"); title.textContent=(quest.claimed?"✅ ":quest.completed?"🎁 ":"🔹 ")+quest.title;
      const description=document.createElement("p"); description.textContent=quest.description;
      const progress=document.createElement("p"); progress.className="small";
      progress.textContent="Progress: "+quest.progress+"/"+quest.target+" · Reward: "+quest.coins+" coins + "+quest.potions+" potions";
      const track=document.createElement("div"); track.className="quest-progress";
      const fill=document.createElement("span");
      fill.style.width=Math.max(0,Math.min(100,quest.progress/quest.target*100))+"%";
      track.appendChild(fill); card.append(title,description,progress,track);
      if(quest.completed&&!quest.claimed){
        const button=document.createElement("button"); button.type="button";
        button.className="dungeon-action"; button.dataset.weeklyQuestId=quest.id;
        button.textContent="Claim weekly reward"; card.appendChild(button);
      }
      ui.weeklyQuestList.appendChild(card);
    });
  }

  async function claimWeeklyQuest(button) {
    if(requestInFlight||!button.dataset.weeklyQuestId)return;
    requestInFlight=true; button.disabled=true; button.textContent="Claiming...";
    try{
      const result=await postApi("/api/weekly-quest/claim",{quest_id:button.dataset.weeklyQuestId});
      applyState(result.state,result.message);
    }catch(error){
      ui.status.textContent=error.message;
      button.disabled=false;button.textContent="Try again";
    }finally{
      requestInFlight=false;
    }
  }

  async function claimDailyMission(button) {
    if(requestInFlight||!button.dataset.dailyMissionId)return;
    requestInFlight=true; button.disabled=true; button.textContent="Claiming...";
    try{
      const result=await postApi("/api/daily-mission/claim",{mission_id:button.dataset.dailyMissionId});
      applyState(result.state,result.message);
    }catch(error){
      ui.status.textContent=error.message;
      button.disabled=false;button.textContent="Try again";
    }finally{
      requestInFlight=false;
    }
  }

  async function claimQuest(questId,button) {
    if (requestInFlight) return;
    requestInFlight=true; button.disabled=true; button.textContent="Claiming...";
    try {
      const result=await postApi("/api/quest/claim",{quest_id:questId});
      applyState(result.state,result.message);
    } catch(error) {
      ui.status.textContent=error.message; button.disabled=false; button.textContent="Try again";
    } finally {
      requestInFlight=false;
    }
  }

  async function requestWithTimeout(path, options) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 20000);
    try {
      return await fetch(path, {...options, signal: controller.signal});
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error("The game server took too long to respond. Check your connection and try again.");
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function loadState() {
    if (!initData) {
      ui.status.textContent = "Open this game from the Telegram bot's private chat.";
      return null;
    }
    const response = await requestWithTimeout("/api/state", {
      headers: {"X-Telegram-Init-Data": initData},
      cache: "no-store"
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      ui.status.textContent = data.error || "Telegram session could not be verified. Reopen the Mini App from the bot.";
      return null;
    }
    if (!data || typeof data !== "object" || !data.monster || !Number.isFinite(data.level)) {
      throw new Error("The game server returned an invalid player state.");
    }
    applyState(data);
    return data;
  }

  async function postApi(path, body) {
    const response = await requestWithTimeout(path, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Telegram-Init-Data": initData},
      body: JSON.stringify(body || {}),
      cache: "no-store"
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The game request failed.");
    if (!data || typeof data !== "object" || !data.state) {
      throw new Error("The game server returned an invalid response.");
    }
    return data;
  }

  async function startEncounter(monsterLevel) {
    if (!gameState.class_selected) { ui.status.textContent = "Choose your class in the Telegram chat first."; return; }
    if (gameState.battle_active) { ui.status.textContent = "You already have an active battle."; return; }
    if (requestInFlight) return;
    requestInFlight = true;
    ui.encounter.disabled = true;
    try {
      const result = await postApi("/api/explore", {monster_level: monsterLevel});
      playSound("encounter");
      applyState(result.state, result.message);
    } catch (error) {
      ui.status.textContent = error.message;
      await loadState().catch(() => null);
    } finally {
      requestInFlight = false;
      if (gameState) applyState(gameState);
    }
  }

  async function performBattleAction(action) {
    if (requestInFlight || !gameState || !gameState.battle_active) return;
    requestInFlight = true;
    document.querySelectorAll("[data-action]").forEach(button => button.disabled = true);
    try {
      if(sceneRef && sceneRef.playCombatAnimation)sceneRef.playCombatAnimation(action);
      const result = await postApi("/api/action", {action});
      playSound(action === "skill" ? "skill" : action === "potion" ? "potion" : action === "attack" ? "attack" : "error");
      if(sceneRef && result.message){
        if(/hits you|poison deals|reflected for/i.test(result.message))sceneRef.playCombatAnimation("hit");
        if(/you were defeated|your hero has fallen/i.test(result.message))sceneRef.playCombatAnimation("death");
        else if(/victory|monster .* defeated/i.test(result.message))sceneRef.playCombatAnimation("victory");
      }
      applyState(result.state, result.message);
    } catch (error) {
      ui.battleMessage.textContent = error.message;
      await loadState().catch(() => null);
    } finally {
      requestInFlight = false;
      if (gameState) applyState(gameState);
    }
  }

  function makeHero(scene, x, y, heroClass, appearance = {}) {
    const c = scene.add.container(x,y);
    const makeLimb=(px,py,color,width,height)=>{
      const limb=scene.add.container(px,py);
      const shape=scene.add.graphics();
      shape.fillStyle(color,1); shape.fillRoundedRect(-width/2,0,width,height,Math.min(5,width/2));
      shape.lineStyle(2,0x172334,0.9); shape.strokeRoundedRect(-width/2,0,width,height,Math.min(5,width/2));
      limb.add(shape); c.add(limb); return limb;
    };
    const limbColor={Knight:0x4d5b72,Mage:0x49375f,Archer:0x36563f,Berserker:0x6e332d}[heroClass]||0x344d68;
    const limbs={
      leftArm:makeLimb(-13,1,limbColor,8,19),
      rightArm:makeLimb(13,1,limbColor,8,19),
      leftLeg:makeLimb(-7,19,0x29313c,8,13),
      rightLeg:makeLimb(7,19,0x29313c,8,13)
    };
    c.limbs=limbs;
    const g = scene.add.graphics();
    const cloak = {traveler:0x344d68,knight:0x596a86,mage:0x654b88,ranger:0x41684f}[appearance.outfit] || ({Knight:0x344d68,Mage:0x654b88,Archer:0x41684f,Berserker:0x8a4138}[heroClass] || 0x25374a);
    const skin = {fair:0xf1d2b5,warm:0xe2b98d,tan:0xb97850,deep:0x70442f}[appearance.skin] || 0xe2b98d;
    const bodyScale = {slim:0.9,balanced:1,broad:1.12}[appearance.body] || 1;
    g.fillStyle(cloak,1); g.fillRoundedRect(-15,-5,30,29,8);
    g.lineStyle(3,0x172334,1); g.strokeRoundedRect(-15,-5,30,29,8);
    g.fillStyle(skin,1);
    if(appearance.face==="angular"){
      g.fillEllipse(0,-16,20,22);g.fillTriangle(-7,-8,7,-8,0,-1);
    }else{
      g.fillCircle(0,-15,11);
    }
    if (appearance.race === "Elf") {
      g.fillStyle(skin,1); g.fillTriangle(-8,-17,-22,-27,-12,-10); g.fillTriangle(8,-17,22,-27,12,-10);
    } else if (appearance.race === "Orc") {
      g.fillStyle(0xf0e4c8,1); g.fillTriangle(-6,-8,-3,-1,-1,-9); g.fillTriangle(6,-8,3,-1,1,-9);
    } else if (appearance.race === "Dwarf") {
      g.fillStyle(0x68452f,1); g.fillTriangle(-9,-9,0,4,9,-9);
    }
    g.fillStyle(0x382b2b,1);
    if (appearance.hair === "shaved") g.fillEllipse(0,-23,18,5);
    else if (appearance.hair === "long") { g.fillEllipse(0,-23,22,12); g.fillRoundedRect(-11,-20,5,17,3); g.fillRoundedRect(6,-20,5,17,3); }
    else if (appearance.hair === "braided") { g.fillEllipse(0,-23,22,12); g.fillCircle(-12,-15,4); g.fillCircle(12,-15,4); }
    else g.fillEllipse(0,-23,22,12);
    const armor={traveler:0x273a52,knight:0x71849c,mage:0x4c3d70,ranger:0x31543f}[appearance.outfit]||0x273a52;
    g.fillStyle(armor,1); g.fillRoundedRect(-12,0,24,18,5);
    g.lineStyle(3,0xc9d4dc,1);
    if(heroClass==="Mage"){
      g.lineStyle(4,0x9b7044,1);g.beginPath();g.moveTo(17,8);g.lineTo(21,-29);g.strokePath();
      g.fillStyle(0x8edbff,1);g.fillCircle(21,-32,5);g.lineStyle(2,0xdaf6ff,0.9);g.strokeCircle(21,-32,7);
    }else if(heroClass==="Archer"){
      g.lineStyle(3,0x9b7044,1);g.beginPath();g.arc(20,-15,13,-Math.PI/2,Math.PI/2,false);g.strokePath();
      g.lineStyle(1,0xe8dfc8,1);g.beginPath();g.moveTo(20,-28);g.lineTo(20,-2);g.strokePath();
      g.lineStyle(2,0xc9d4dc,1);g.beginPath();g.moveTo(15,-15);g.lineTo(30,-15);g.strokePath();
    }else if(heroClass==="Berserker"){
      g.lineStyle(4,0x9b7044,1);g.beginPath();g.moveTo(17,7);g.lineTo(23,-21);g.strokePath();
      g.fillStyle(0xb7c2cc,1);g.fillTriangle(20,-22,34,-29,31,-11);g.lineStyle(2,0x52606c,1);g.strokeTriangle(20,-22,34,-29,31,-11);
    }else{
      g.lineStyle(3,0xc9d4dc,1);g.beginPath();g.moveTo(13,-3);g.lineTo(26,-25);g.strokePath();
      g.lineStyle(4,0x9b7044,1);g.beginPath();g.moveTo(10,1);g.lineTo(18,-10);g.strokePath();
      g.fillStyle(0xdce6ef,1);g.fillTriangle(26,-25,30,-34,23,-28);
    }
    g.fillStyle(0x171b25,1); g.fillCircle(-4,-16,1.5); g.fillCircle(4,-16,1.5);
    if(appearance.face==="scarred"){
      g.lineStyle(1.8,0x8b3d42,0.95);g.lineBetween(-7,-11,-1,-5);
    }
    c.add(g);c.setScale(bodyScale,1);c.setDepth(10);return c;
  }

  function makeMonster(scene,x,y,level,color) {
    const c=scene.add.container(x,y);
    const g=scene.add.graphics();
    const r=Math.min(34,17+level/12);
    g.fillStyle(color,1); g.fillEllipse(0,2,r*2,r*1.55);
    g.lineStyle(3,0x1b1b27,1); g.strokeEllipse(0,2,r*2,r*1.55);
    g.fillStyle(0xe9d8bd,1); g.fillTriangle(-r+5,-r/2,-r+13,-r-13,-r+18,-r/2);
    g.fillTriangle(r-5,-r/2,r-13,-r-13,r-18,-r/2);
    g.fillStyle(0xffe9c6,1); g.fillCircle(-8,-2,4); g.fillCircle(8,-2,4);
    g.fillStyle(0x261a25,1); g.fillCircle(-8,-2,1.8); g.fillCircle(8,-2,1.8);
    g.lineStyle(2,0x241a24,1); g.beginPath(); g.arc(0,9,7,0.2,Math.PI-0.2,false); g.strokePath();
    c.add(g); c.setDepth(5); return c;
  }

  class AdventureScene extends Phaser.Scene {
    constructor(){super("adventure");}
    create(){
      sceneRef=this;
      const w=this.scale.width*2.6,h=this.scale.height*1.5;
      this.worldWidth=w;this.worldHeight=h;
      const idx=Math.max(0,Math.min(9,gameState ? (gameState.world_id||1)-1:0));
      const palette=worldPalettes[idx];
      this.cameras.main.setBackgroundColor(palette.sky);
      const ground=this.add.graphics();
      ground.fillStyle(palette.ground,1); ground.fillRect(0,h*0.43,w,h*0.57);
      ground.lineStyle(2,0x1e2c2b,0.2);
      for(let x=0;x<w;x+=44){for(let y=h*0.43;y<h;y+=38){ground.strokeRect(x,y,44,38);}}
      for(let i=0;i<12;i++){
        const x=(i*83+31)%w,y=h*0.53+(i*47)%(h*0.4);
        ground.fillStyle(palette.accent,0.24);ground.fillCircle(x,y,2+(i%3));
      }
      const scenery=this.add.graphics();
      if(idx===0){
        for(let i=0;i<8;i++){const x=28+i*118;scenery.fillStyle(0x473d32,1);scenery.fillRect(x-4,h*0.37,8,34);scenery.fillStyle(0x345943,1);scenery.fillTriangle(x-25,h*0.43,x,h*0.22,x+25,h*0.43);scenery.lineStyle(2,0x172b29,0.55);scenery.strokeTriangle(x-25,h*0.43,x,h*0.22,x+25,h*0.43);}
      }else if(idx===1){
        for(let i=0;i<9;i++){const x=i*112+20;scenery.fillStyle(0xe2bd7c,0.45);scenery.fillEllipse(x,h*0.57+(i%3)*36,120,24);scenery.fillStyle(0x47704b,1);scenery.fillRoundedRect(x-5,h*0.37,10,34,4);scenery.fillRect(x-15,h*0.43,10,5);scenery.fillRect(x+5,h*0.45,10,5);}
      }else if(idx===2){
        for(let i=0;i<8;i++){const x=i*125+35;scenery.fillStyle(0x526875,1);scenery.fillTriangle(x-28,h*0.55,x,h*0.24,x+35,h*0.55);scenery.lineStyle(3,0xb7d3d8,0.6);scenery.lineBetween(x,h*0.27,x+12,h*0.4);scenery.lineBetween(x+12,h*0.4,x-4,h*0.47);}
      }else if(idx===3){
        for(let i=0;i<7;i++){const x=i*145+35;scenery.fillStyle(0x554b61,1);scenery.fillRect(x,h*0.28,20,h*0.28);scenery.fillRect(x-8,h*0.25,36,8);scenery.fillStyle(0x29283b,1);scenery.fillRect(x+5,h*0.34,10,h*0.19);scenery.fillStyle(0xb0a0c1,0.7);scenery.fillCircle(x+5,h*0.63,3);}
      }else if(idx===4){
        for(let i=0;i<10;i++){const x=i*100+15;scenery.lineStyle(5,0xf09a51,0.85);scenery.beginPath();scenery.moveTo(x,h*0.48);scenery.lineTo(x+18,h*0.57);scenery.lineTo(x+8,h*0.66);scenery.lineTo(x+31,h*0.75);scenery.strokePath();scenery.fillStyle(0x3d3032,1);scenery.fillTriangle(x-20,h*0.52,x,h*0.35,x+22,h*0.52);}
      }else if(idx===5){
        for(let i=0;i<9;i++){const x=i*110+25;scenery.fillStyle(0xdcecef,0.9);scenery.fillTriangle(x-28,h*0.58,x,h*0.29,x+28,h*0.58);scenery.lineStyle(2,0x9bc4d1,0.8);scenery.lineBetween(x,h*0.32,x,h*0.55);scenery.fillStyle(0xffffff,0.8);scenery.fillEllipse(x+35,h*0.72,45,12);}
      }else if(idx===6){
        for(let i=0;i<8;i++){const x=i*130+20,y=h*0.3+(i%3)*38;scenery.fillStyle(0x554a80,0.85);scenery.fillCircle(x,y,20);scenery.lineStyle(2,0xb5a5df,0.8);scenery.strokeCircle(x,y,28);scenery.fillStyle(0x211d38,1);scenery.fillCircle(x,y,9);}
      }else if(idx===7){
        for(let i=0;i<24;i++){const x=(i*73)%w,y=(i*41)%(h*0.7);scenery.fillStyle(0xf2e6b4,0.85);scenery.fillCircle(x,y,1+(i%3));}for(let i=0;i<6;i++){const x=i*155+50;scenery.fillStyle(0x9eb4e0,0.7);scenery.fillTriangle(x-18,h*0.6,x,h*0.3,x+18,h*0.6);scenery.lineStyle(2,0xe0dcff,0.8);scenery.strokeTriangle(x-18,h*0.6,x,h*0.3,x+18,h*0.6);}
      }else if(idx===8){
        for(let i=0;i<6;i++){const x=i*165+65;scenery.lineStyle(4,0x9587ad,0.7);scenery.strokeCircle(x,h*0.56,28+i%2*8);scenery.lineBetween(x,h*0.56,x,h*0.56-18);scenery.lineBetween(x,h*0.56,x+15,h*0.56+8);}
      }else{
        for(let i=0;i<8;i++){const x=i*120+30;scenery.lineStyle(8,0x725c69,0.9);scenery.beginPath();scenery.moveTo(x,h*0.95);scenery.lineTo(x+20,h*0.65);scenery.lineTo(x-12,h*0.45);scenery.lineTo(x+18,h*0.25);scenery.strokePath();scenery.fillStyle(0xe2c17c,0.7);scenery.fillCircle(x+18,h*0.25,5);}
      }
      // Spread deterministic blockers across the expanded three-zone map.
      // Keep the hero spawn, Wanderer and world gate clear for reliable first input.
      this.obstacles = [
        {x:w*0.14,y:h*0.61,width:42,height:58},
        {x:w*0.32,y:h*0.77,width:58,height:34},
        {x:w*0.43,y:h*0.51,width:46,height:54},
        {x:w*0.62,y:h*0.84,width:50,height:28},
        {x:w*0.76,y:h*0.59,width:54,height:42},
        {x:w*0.86,y:h*0.88,width:46,height:58},
        {x:w*0.27,y:h*0.53,width:38,height:48},
        {x:w*0.69,y:h*0.48,width:44,height:36}
      ];
      this.obstacleGraphics = this.add.graphics();
      this.obstacles.forEach((obstacle,index)=>{
        const color = index % 2 ? 0x514b48 : 0x3b5140;
        this.obstacleGraphics.fillStyle(color,1);
        this.obstacleGraphics.fillEllipse(obstacle.x,obstacle.y,obstacle.width,obstacle.height);
        this.obstacleGraphics.lineStyle(3,0x1d2928,0.8);
        this.obstacleGraphics.strokeEllipse(obstacle.x,obstacle.y,obstacle.width,obstacle.height);
        if(index % 2 === 0){
          this.obstacleGraphics.fillStyle(palette.accent,0.65);
          this.obstacleGraphics.fillCircle(obstacle.x-7,obstacle.y-8,4);
          this.obstacleGraphics.fillCircle(obstacle.x+8,obstacle.y-5,3);
        }
      });
      const zoneLabels=["THE OUTER REACH","THE WILD HEART","THE INNER FRONTIER"];
      zoneLabels.forEach((label,index)=>{
        const x=w*(index+0.5)/3;
        this.add.text(x,h*0.47,label,{
          fontFamily:"Georgia",fontSize:"11px",fontStyle:"bold",color:"#fff1cf",
          stroke:"#17232a",strokeThickness:3,letterSpacing:2
        }).setOrigin(0.5).setAlpha(0.72).setDepth(2);
        if(index>0){
          const divider=this.add.graphics().setDepth(1);
          divider.lineStyle(2,palette.accent,0.22);
          divider.lineBetween(x-w/6,h*0.49,x-w/6,h*0.96);
        }
      });
      this.hero=makeHero(this,w*0.22,h*0.7,gameState.hero_class,gameState.appearance);
      this.heroBaseScaleX=this.hero.scaleX||1;
      this.heroFacing=1;
      this.cameras.main.setBounds(0,0,this.worldWidth,this.worldHeight);
      this.cameras.main.startFollow(this.hero,true,0.08,0.08);
      this.npc = makeHero(this,w*0.49,h*0.7,"Mage");
      this.npc.setScale(0.9);
      this.obstacles.push({x:this.npc.x,y:this.npc.y,width:34,height:34});
      this.npcLabel = this.add.text(w*0.49,h*0.7-44,"WANDERER",{fontFamily:"Georgia",fontSize:"12px",color:"#fff4d6",stroke:"#17232a",strokeThickness:3}).setOrigin(0.5);
      const nextWorld=gameState.worlds.find(world=>world.id===gameState.world_id+1);
      this.portalX=this.worldWidth-78;
      this.portalY=h*0.69;
      this.portalGraphics=this.add.graphics().setDepth(3);
      this.portalGraphics.fillStyle(0x142a42,0.82);
      this.portalGraphics.fillCircle(this.portalX,this.portalY,31);
      this.portalGraphics.lineStyle(4,0x8edbff,0.95);
      this.portalGraphics.strokeCircle(this.portalX,this.portalY,28);
      this.portalGraphics.lineStyle(2,0xd6b7ff,0.8);
      this.portalGraphics.strokeCircle(this.portalX,this.portalY,19);
      this.portalLabel=this.add.text(this.portalX,this.portalY-48,nextWorld?(nextWorld.unlocked?"WORLD GATE":"SEALED GATE"):"ORIGIN GATE",{
        fontFamily:"Georgia",fontSize:"11px",color:"#dff7ff",stroke:"#17232a",strokeThickness:3
      }).setOrigin(0.5);
      this.tweens.add({targets:this.portalGraphics,alpha:0.55,duration:900,yoyo:true,repeat:-1,ease:"Sine.easeInOut"});
      this.npcDialog = [
        "The blue spark you carry once guided the first guardian home.",
        "The desert swallowed a city to hide a promise beneath its oldest dune.",
        "Stormglass remembers every name spoken during the great collapse.",
        "The Hollow Kingdom fell because its king tried to defeat grief itself.",
        "The Ember Abyss burns brighter whenever someone refuses to forget.",
        "A lost child left these footprints before the frost covered the peaks.",
        "The rift is not a wound in the world. It is a door someone locked.",
        "The stars above these ruins are memories, not distant suns.",
        "Time repeats the final hour because one voice has not been heard.",
        "The Alpha God began as a lonely light, not a monster."
      ];
      const monsterColor=[0x79b88b,0xc99a57,0x8ba9b7,0x8b7b9e,0xc66b3e,0x91c4d2,0x7262a5,0x8e9bc9,0x5b547b,0xc49a58][idx];
      const roster=Array.isArray(gameState.nearby_monsters)&&gameState.nearby_monsters.length?gameState.nearby_monsters:[gameState.monster];
      const positions=roster.length===1?[0.77]:roster.length===2?[0.65,0.84]:[0.57,0.73,0.89];
      this.monsters=roster.map((monster,index)=>{
        const x=w*positions[Math.min(index,positions.length-1)];
        const y=h*(index%2===0?0.68:0.76);
        const sprite=makeMonster(this,x,y,monster.level,monsterColor);
        const label=this.add.text(x,y-48,(monster.boss?"👑 ":"")+monster.name,{fontFamily:"Georgia",fontSize:"12px",color:"#fff4d6",stroke:"#1b1b24",strokeThickness:3}).setOrigin(0.5);
        this.tweens.add({targets:sprite,y:sprite.y-5,duration:800+index*90,yoyo:true,repeat:-1,ease:"Sine.easeInOut"});
        return {sprite,data:monster,label};
      });
      this.selectedMonster=null;
      this.movePath=[];
      this.movePathIndex=0;
      // Idle animation changes scale, not world position, so it cannot fight movement.
      this.heroIdle = this.tweens.add({
        targets:this.hero, scaleY:1.025, duration:650, yoyo:true, repeat:-1, ease:"Sine.easeInOut"
      });
      this.add.text(this.cameras.main.width*0.5,28,worldNames[idx],{fontFamily:"Georgia",fontSize:"19px",color:"#fff4d6",stroke:"#17232a",strokeThickness:4}).setOrigin(0.5).setScrollFactor(0);
      this.cursors=this.input.keyboard.createCursorKeys();
      this.keys=this.input.keyboard.addKeys("W,A,S,D,E");
      this.sprintKey=this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SHIFT);
      this.input.keyboard.addCapture(["UP","DOWN","LEFT","RIGHT","W","A","S","D","SHIFT"]);
      if(pendingSceneEffects.length)this.time.delayedCall(80,flushSceneEffects);
      this.input.on("pointerdown",pointer=>{
        if(gameState&&gameState.battle_active||requestInFlight)return;
        if(nearMonster){this.challenge();return;}
        if(nearNpc){this.talkToNpc();return;}
        const point=this.cameras.main.getWorldPoint(pointer.x,pointer.y);
        const target={
          x:Phaser.Math.Clamp(point.x,24,this.worldWidth-24),
          y:Phaser.Math.Clamp(point.y,this.worldHeight*0.46,this.worldHeight-24)
        };
        this.movePath=window.PeakPathfinding
          ? window.PeakPathfinding.findPath(
              {x:this.hero.x,y:this.hero.y},
              target,
              this.obstacles,
              {width:this.worldWidth,height:this.worldHeight,minY:this.worldHeight*0.46,cellSize:32,margin:14,maxNodes:1800}
            )
          : [];
        this.movePathIndex=0;
      });
      this.physics=null;
    }
    playCombatAnimation(action){
      if(!this.hero)return;
      const limbs=this.hero.limbs||{};
      if(action==="attack"||action==="skill"){
        const arm=limbs.rightArm;
        if(arm)this.tweens.add({targets:arm,rotation:action==="skill"?-1.9:-1.45,duration:95,yoyo:true,repeat:1,ease:"Back.easeOut"});
        const target=this.selectedMonster&&this.selectedMonster.sprite;
        if(target)this.tweens.add({targets:target,x:target.x+9,duration:55,yoyo:true,repeat:2,ease:"Sine.easeInOut"});
        if(action==="skill"){
          const pulse=this.add.circle(this.hero.x,this.hero.y,24,0x8edbff,0.28).setDepth(9);
          this.tweens.add({targets:pulse,scale:2.4,alpha:0,duration:300,onComplete:()=>pulse.destroy()});
        }
      }else if(action==="potion"){
        const aura=this.add.circle(this.hero.x,this.hero.y,22,0x8bd89b,0.24).setDepth(9);
        this.tweens.add({targets:aura,scale:2,alpha:0,duration:380,onComplete:()=>aura.destroy()});
      }else if(action==="hit"){
        this.tweens.add({targets:this.hero,alpha:0.35,duration:65,yoyo:true,repeat:2});
      }else if(action==="death"){
        this.tweens.add({targets:this.hero,alpha:0.12,angle:82,y:this.hero.y+9,duration:420,ease:"Cubic.easeIn"});
      }else if(action==="victory"){
        this.tweens.add({targets:this.hero,y:this.hero.y-22,duration:180,yoyo:true,ease:"Back.easeOut"});
      }
    }
    playDeathAnimation(){
      if(!this.hero)return;
      this.tweens.killTweensOf(this.hero);
      if(this.heroWalkTween){this.heroWalkTween.stop();this.heroWalkTween=null;}
      if(this.heroIdle){this.heroIdle.stop();this.heroIdle=null;}
      this.tweens.add({targets:this.hero,alpha:0.35,angle:90,scaleY:0.72,duration:420,ease:"Cubic.easeIn"});
    }
    playRespawnAnimation(){
      if(!this.hero)return;
      this.tweens.killTweensOf(this.hero);
      this.tweens.add({targets:this.hero,alpha:1,angle:0,scaleX:(this.heroBaseScaleX||1)*(this.heroFacing||1),scaleY:1,y:this.hero.y-9,duration:360,ease:"Cubic.easeOut"});
      this.heroIdle=this.tweens.add({targets:this.hero,scaleY:1.025,duration:650,yoyo:true,repeat:-1,ease:"Sine.easeInOut"});
    }
    playLevelUpAnimation(){
      if(!this.hero)return;
      const ring=this.add.circle(this.hero.x,this.hero.y,18,0xffdf83,0).setStrokeStyle(3,0xffdf83,0.9).setDepth(12);
      this.tweens.add({targets:ring,scale:3.2,alpha:0,duration:650,ease:"Cubic.easeOut",onComplete:()=>ring.destroy()});
      for(let index=0;index<10;index++){
        const angle=(Math.PI*2*index)/10;
        const mote=this.add.circle(this.hero.x,this.hero.y,3,0xffe8a8,0.95).setDepth(13);
        this.tweens.add({targets:mote,x:this.hero.x+Math.cos(angle)*52,y:this.hero.y+Math.sin(angle)*52,alpha:0,scale:0.25,duration:520,ease:"Cubic.easeOut",onComplete:()=>mote.destroy()});
      }
    }
    challenge(){
      if(this.selectedMonster)startEncounter(this.selectedMonster.level);
    }
    talkToNpc(){
      if(!nearNpc || (gameState && gameState.battle_active))return;
      const idx=Math.max(0,Math.min(9,(gameState.world_id||1)-1));
      ui.status.textContent="Wanderer: "+this.npcDialog[idx];
    }
    blockedAt(x,y){
      const radius=13;
      return this.obstacles.some(o=>
        x+radius>o.x-o.width/2 && x-radius<o.x+o.width/2 &&
        y+radius>o.y-o.height/2 && y-radius<o.y+o.height/2
      );
    }
    update(_,delta){
      if(!this.hero)return;
      this.cycleTime = (this.cycleTime + delta) % 90000;
      const daylight = (Math.sin((this.cycleTime / 90000) * Math.PI * 2 - Math.PI / 2) + 1) / 2;
      this.timeOverlay.setAlpha(0.28 * (1 - daylight));
      this.weatherGraphics.clear();
      const elapsed = this.time.now;
      if (this.weatherMode === "rain" || this.weatherMode === "sand" || this.weatherMode === "ash" || this.weatherMode === "snow") {
        const weatherColor = this.weatherMode === "snow" ? 0xeaf5ff : this.weatherMode === "sand" ? 0xe9c27a : this.weatherMode === "ash" ? 0xdaa08a : 0xa9d4e8;
        for (let i=0;i<26;i++) {
          const x=(i*71+elapsed*0.11*(this.weatherMode==="sand"?1.8:1))%this.scale.width;
          const y=(i*43+elapsed*0.24)%this.scale.height;
          this.weatherGraphics.lineStyle(this.weatherMode==="snow"?2:1,weatherColor,this.weatherMode==="ash"?0.45:0.6);
          if (this.weatherMode==="snow") this.weatherGraphics.fillStyle(weatherColor,0.65),this.weatherGraphics.fillCircle(x,y,1.5+(i%2));
          else this.weatherGraphics.lineBetween(x,y,x+(this.weatherMode==="sand"?8:3),y+(this.weatherMode==="rain"?10:5));
        }
      } else {
        const moteColor = this.weatherMode==="embers" ? 0xffa05b : this.weatherMode==="stardust" ? 0xe4d6ff : this.weatherMode==="falling-light" ? 0xffe8a4 : 0xb4b4e0;
        for (let i=0;i<14;i++) {
          const x=(i*83+Math.sin(elapsed/1300+i)*22)%this.scale.width;
          const y=(i*47+elapsed*(this.weatherMode==="embers"?-0.025:0.035))%this.scale.height;
          this.weatherGraphics.fillStyle(moteColor,0.35+(i%3)*0.15);
          this.weatherGraphics.fillCircle(x,y,1+(i%3));
        }
      }
      if(gameState && gameState.battle_active){clearMovementInput();ui.encounter.disabled=true;return;}
      // Clamp long frames after tab suspension to prevent large movement jumps.
      const frameDelta=Phaser.Math.Clamp(Number(delta)||0,0,50);
      const baseSpeed=0.18*frameDelta;
      const sprintHeld=Boolean(sprintKeyboardHeld||sprintTouchHeld);
      const speed=baseSpeed*(sprintHeld?1.45:1);
      let dx=0,dy=0;
      if(this.cursors.left.isDown||this.keys.A.isDown||pressedDirections.has("left"))dx=-1;
      if(this.cursors.right.isDown||this.keys.D.isDown||pressedDirections.has("right"))dx=1;
      if(this.cursors.up.isDown||this.keys.W.isDown||pressedDirections.has("up"))dy=-1;
      if(this.cursors.down.isDown||this.keys.S.isDown||pressedDirections.has("down"))dy=1;
      if(dx||dy){
        this.movePath=[];
        this.movePathIndex=0;
      }else if(this.movePath&&this.movePathIndex<this.movePath.length){
        const waypoint=this.movePath[this.movePathIndex];
        const diffX=waypoint.x-this.hero.x;
        const diffY=waypoint.y-this.hero.y;
        const distance=Math.hypot(diffX,diffY);
        if(distance<=speed+2){
          this.hero.x=waypoint.x;
          this.hero.y=waypoint.y;
          this.movePathIndex++;
          if(this.movePathIndex>=this.movePath.length)this.movePath=[];
        }else{
          dx=diffX/distance;
          dy=diffY/distance;
        }
      }
      if(dx&&dy){dx*=0.707;dy*=0.707;}
      const moving=dx!==0||dy!==0;
      const sprinting=moving&&sprintHeld;
      if(dx < -0.01 || dx > 0.01){
        const nextFacing=dx<0?-1:1;
        if(nextFacing!==this.heroFacing){
          this.heroFacing=nextFacing;
          if(this.heroWalkTween){this.heroWalkTween.stop();this.heroWalkTween=null;}
          this.hero.setScale(this.heroBaseScaleX*this.heroFacing,1);
        }
      }
      if(moving){
        if(this.heroIdle){
          this.heroIdle.stop();
          this.heroIdle=null;
        }
        if(!this.heroWalkTween){
          this.hero.setScale(this.heroBaseScaleX*this.heroFacing,1);
          this.heroWalkTween=this.tweens.add({targets:this.hero,scaleX:this.heroBaseScaleX*this.heroFacing*0.96,scaleY:1.04,duration:115,yoyo:true,repeat:-1,ease:"Sine.easeInOut"});
        }
        this.hero.setRotation(dx*0.045);
      }else{
        if(this.heroWalkTween){
          this.heroWalkTween.stop();
          this.heroWalkTween=null;
          this.hero.setScale(this.heroBaseScaleX*this.heroFacing,1);
          this.hero.setRotation(0);
        }
        if(!this.heroIdle){
          this.heroIdle=this.tweens.add({targets:this.hero,scaleY:1.025,duration:650,yoyo:true,repeat:-1,ease:"Sine.easeInOut"});
        }
      }
      const nextX=Phaser.Math.Clamp(this.hero.x+dx*speed,24,this.worldWidth-24);
      if(!this.blockedAt(nextX,this.hero.y))this.hero.x=nextX;
      const nextY=Phaser.Math.Clamp(this.hero.y+dy*speed,this.worldHeight*0.46,this.worldHeight-24);
      if(!this.blockedAt(this.hero.x,nextY))this.hero.y=nextY;
      const walking=Boolean(dx||dy);
      const gait=walking?Math.sin(this.time.now/(sprinting?46:76))*(sprinting?0.82:0.52):Math.sin(this.time.now/430)*0.065;
      if(this.hero.limbs){
        this.hero.limbs.leftArm.rotation=-gait*0.92;
        this.hero.limbs.rightArm.rotation=gait*0.92;
        this.hero.limbs.leftLeg.rotation=gait*0.78;
        this.hero.limbs.rightLeg.rotation=-gait*0.78;
      }
      if(sprinting&&this.time.now-(this.lastSprintDustAt||0)>160){
        this.lastSprintDustAt=this.time.now;
        const dust=this.add.circle(this.hero.x-dx*5,this.hero.y+15,2,0xd9c8a0,0.42).setDepth(8);
        this.tweens.add({targets:dust,x:dust.x-dx*11,y:dust.y+5-dy*4,alpha:0,scale:2.1,duration:260,onComplete:()=>dust.destroy()});
      }
      if(this.npc && this.npc.limbs){
        const idle=Math.sin(this.time.now/520)*0.045;
        this.npc.limbs.leftArm.rotation=idle;
        this.npc.limbs.rightArm.rotation=-idle;
      }
      let closest=null,closestDistance=Infinity;
      this.monsters.forEach(entry=>{
        const distance=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,entry.sprite.x,entry.sprite.y);
        if(distance<closestDistance){closestDistance=distance;closest=entry;}
      });
      nearMonster=closestDistance<88;
      this.selectedMonster=nearMonster?closest:null;
      nearNpc=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,this.npc.x,this.npc.y)<72;
      nearPortal=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,this.portalX,this.portalY)<72;
      const nextWorld=gameState.worlds.find(world=>world.id===gameState.world_id+1);
      this.portalLabel.setText(nextWorld?(nextWorld.unlocked?"WORLD GATE":"SEALED GATE"):"ORIGIN GATE");
      ui.portalTravel.dataset.worldTravelId=nextWorld?String(nextWorld.id):"";
      ui.portalTravel.disabled=!nearPortal||!nextWorld||!nextWorld.unlocked||gameState.battle_active||requestInFlight;
      ui.portalTravel.textContent=!nearPortal?"🌀 Find portal":!nextWorld?"🏁 Origin Gate":nextWorld.unlocked?"🌀 Enter "+nextWorld.name:"🔒 Portal · Lv."+nextWorld.min_level;
      ui.interact.disabled=!nearNpc;
      ui.interact.textContent=nearNpc?"💬 Talk to Wanderer":"💬 Find Wanderer";
      if(Phaser.Input.Keyboard.JustDown(this.keys.E))this.talkToNpc();
      ui.encounter.disabled=!nearMonster||!gameState.class_selected||gameState.battle_active;
      ui.encounter.textContent=nearMonster?"⚔️ Challenge "+closest.data.name:"⚔️ Find a monster";
      ui.monster.textContent=nearMonster?"Lv. "+closest.data.level+" · "+closest.data.name:(rosterCountText());
      if(nearMonster)ui.status.textContent=closest.data.name+" has noticed you. Prepare for battle.";
    }
  }

  function rosterCountText(){return "Nearby threats: "+(gameState&&Array.isArray(gameState.nearby_monsters)?gameState.nearby_monsters.length:1);}

  function bootGame(){
    if(!gameState)return;
    const config={type:Phaser.AUTO,parent:"game",width:900,height:500,backgroundColor:"#344b3e",scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH},scene:[AdventureScene]};
    if (phaserGame) phaserGame.destroy(true);
    phaserGame = new Phaser.Game(config);
  }

  document.getElementById("sound-toggle").addEventListener("click", async event => {
    if (requestInFlight || !gameState) return;
    const button = event.currentTarget;
    const previous = soundEnabled;
    const next = !previous;
    soundEnabled = next;
    if (!next) stopAmbientMusic();
    requestInFlight = true;
    button.disabled = true;
    button.setAttribute("aria-pressed", String(next));
    button.textContent = next ? "🔊 Sound" : "🔇 Muted";
    try {
      const result = await postApi("/api/settings", {sound_enabled: next});
      requestInFlight = false;
      applyState(result.state, result.message);
      if (next) playSound("potion");
    } catch (error) {
      requestInFlight = false;
      soundEnabled = previous;
      button.setAttribute("aria-pressed", String(previous));
      button.textContent = previous ? "🔊 Sound" : "🔇 Muted";
      ui.status.textContent = error.message;
    } finally {
      requestInFlight = false;
      button.disabled = false;
    }
  });


  if(ui.dailyMissionList) ui.dailyMissionList.addEventListener("click",event=>{
    const button=event.target.closest("[data-daily-mission-id]");
    if(button) claimDailyMission(button);
  });

  if(ui.weeklyQuestList) ui.weeklyQuestList.addEventListener("click",event=>{
    const button=event.target.closest("[data-weekly-quest-id]");
    if(button) claimWeeklyQuest(button);
  });

  if(ui.worldNavigation) ui.worldNavigation.addEventListener("click",event=>{
    const button=event.target.closest("[data-world-travel-id],[data-world-discover]");
    if(button) performWorldAction(button);
  });
  if(ui.portalTravel) ui.portalTravel.addEventListener("click",event=>performWorldAction(event.currentTarget));

  if(ui.guildChatLoad)ui.guildChatLoad.addEventListener("click",async()=>{
    try{
      const result=await runSocialAction({action:"guild_chat"});
      renderGuildChat(result.result.messages||[]);
    }catch(_){}
  });
  if(ui.guildChatForm)ui.guildChatForm.addEventListener("submit",async event=>{
    event.preventDefault();
    const message=ui.guildChatInput.value.trim();
    if(!message)return;
    try{
      const result=await runSocialAction({action:"guild_send",message});
      renderGuildChat(result.result.messages||[]);
      ui.guildChatInput.value="";
    }catch(_){}
  });

  if(ui.premiumShopItems)ui.premiumShopItems.addEventListener("click",async event=>{
    const button=event.target.closest("[data-premium-item]");
    if(!button||button.disabled||requestInFlight)return;
    button.disabled=true;
    try{
      const result=await postApi("/api/premium-shop",{item_id:button.dataset.premiumItem});
      applyState(result.state,result.message);
    }catch(error){ui.status.textContent=error.message;button.disabled=false;}
  });
  if(ui.socialSearchForm)ui.socialSearchForm.addEventListener("submit",async event=>{
    event.preventDefault();
    const query=ui.socialSearchInput.value.trim();
    if(query.length<2)return;
    try{
      const result=await runSocialAction({action:"friend_search",query});
      renderPlayerSearch(result.result.players||[]);
    }catch(_){}
  });
  if(ui.socialOverview)ui.socialOverview.addEventListener("click",async event=>{
    const button=event.target.closest("[data-social-action]");
    if(!button||button.disabled)return;
    const action=button.dataset.socialAction;
    const payload={action};
    if(action==="friend_request")payload.target_id=Number(button.dataset.targetId);
    if(action==="trade_create")payload.target_id=Number(button.dataset.targetId);
    if(action==="friend_accept"||action==="friend_decline")payload.request_id=Number(button.dataset.requestId);
    if(action==="friend_remove")payload.friend_id=Number(button.dataset.friendId);
    if(action==="party_accept"||action==="party_decline"||action==="guild_accept"||action==="guild_decline")payload.invite_id=Number(button.dataset.inviteId);
    if(action==="trade_accept"||action==="trade_decline"||action==="trade_cancel"||action==="trade_confirm")payload.trade_id=Number(button.dataset.tradeId);
    button.disabled=true;
    try{await runSocialAction(payload);}catch(_){button.disabled=false;}
  });
  if(ui.matchmakingCasual)ui.matchmakingCasual.addEventListener("click",()=>runMatchmakingAction("join","casual"));
  if(ui.matchmakingRanked)ui.matchmakingRanked.addEventListener("click",()=>runMatchmakingAction("join","ranked"));
  if(ui.matchmakingCancel)ui.matchmakingCancel.addEventListener("click",()=>runMatchmakingAction("cancel"));
  if(ui.matchmakingDetails)ui.matchmakingDetails.addEventListener("click",event=>{
    const button=event.target.closest("[data-pvp-action]");
    if(!button||button.disabled)return;
    const matchId=Number(button.dataset.matchId);
    if(Number.isSafeInteger(matchId)&&matchId>0)runMatchmakingBattleAction(button.dataset.pvpAction,matchId);
  });
  if(ui.matchmakingRefresh)ui.matchmakingRefresh.addEventListener("click",async()=>{
    if(requestInFlight)return;
    requestInFlight=true;ui.matchmakingRefresh.disabled=true;
    try{await loadState();}catch(error){ui.status.textContent=error.message;}
    finally{requestInFlight=false;if(gameState)applyState(gameState);}
  });
  if(ui.partyCreate)ui.partyCreate.addEventListener("click",async()=>{try{await runSocialAction({action:"party_create"});}catch(_){}});
  if(ui.partyInvite)ui.partyInvite.addEventListener("click",async()=>{
    const targetId=Number(ui.partyTargetId.value);
    if(!Number.isSafeInteger(targetId)||targetId<=0){ui.status.textContent="Enter a valid player ID.";return;}
    try{await runSocialAction({action:"party_invite",target_id:targetId});ui.partyTargetId.value="";}catch(_){}
  });
  if(ui.partyLeave)ui.partyLeave.addEventListener("click",async()=>{try{await runSocialAction({action:"party_leave"});}catch(_){}});
  ui.dungeonStatus.addEventListener("click",event=>{
    const button=event.target.closest("[data-dungeon-action]");
    if(button) performDungeonAction(button);
  });

  document.getElementById("save-settings").addEventListener("click", async () => {
    if (requestInFlight || !gameState) return;
    const button=document.getElementById("save-settings");
    requestInFlight=true;button.disabled=true;
    ui.settingsStatus.textContent="Saving settings...";
    try {
      const payload={
        notifications_enabled:document.getElementById("setting-notifications").value==="1",
        profile_visibility:document.getElementById("setting-privacy").value
      };
      const result=await postApi("/api/settings",payload);
      applyState(result.state,result.message);
      ui.settingsStatus.textContent="Privacy and notification settings saved.";
    } catch(error) {
      ui.settingsStatus.textContent=error.message;
    } finally {
      requestInFlight=false;button.disabled=false;
    }
  });

  document.getElementById("save-appearance").addEventListener("click", async () => {
    if (requestInFlight || !gameState) return;
    const button = document.getElementById("save-appearance");
    const payload = {};
    ["race","skin","hair","outfit"].forEach(key => {
      payload[key] = document.getElementById("appearance-" + key).value;
    });
    requestInFlight = true;
    button.disabled = true;
    ui.appearanceStatus.textContent = "Saving your hero...";
    try {
      const result = await postApi("/api/appearance", payload);
      applyState(result.state, result.message);
      if (sceneRef) sceneRef.scene.restart();
      ui.appearanceStatus.textContent = "Appearance saved successfully.";
    } catch (error) {
      ui.appearanceStatus.textContent = error.message;
    } finally {
      requestInFlight = false;
      button.disabled = false;
    }
  });
  document.getElementById("encounter").addEventListener("click",()=>{if(sceneRef)sceneRef.challenge();});
  document.getElementById("interact-npc").addEventListener("click",()=>{if(sceneRef)sceneRef.talkToNpc();});
  document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",()=>performBattleAction(button.dataset.action)));
  const sprintControl=document.getElementById("sprint-control");
  if(sprintControl){
    const setSprint=(active,event)=>{
      if(event)event.preventDefault();
      sprintTouchHeld=active;
      sprintControl.setAttribute("aria-pressed",String(active));
    };
    sprintControl.addEventListener("pointerdown",event=>{
      setSprint(true,event);
      if(sprintControl.setPointerCapture&&event.pointerId!==undefined){try{sprintControl.setPointerCapture(event.pointerId);}catch(_){}}
    });
    ["pointerup","pointercancel","lostpointercapture"].forEach(type=>sprintControl.addEventListener(type,event=>setSprint(false,event)));
    sprintControl.addEventListener("contextmenu",event=>event.preventDefault());
    sprintControl.addEventListener("keydown",event=>{if(event.key===" "||event.key==="Enter"){event.preventDefault();setSprint(true,event);}});
    sprintControl.addEventListener("keyup",event=>{if(event.key===" "||event.key==="Enter")setSprint(false,event);});
    sprintControl.addEventListener("blur",()=>setSprint(false));
  }
  document.querySelectorAll("[data-dir]").forEach(button=>{
    const dir=button.dataset.dir;
    const start=event=>{
      event.preventDefault();
      pressedDirections.add(dir);
      if (button.setPointerCapture && event.pointerId !== undefined) {
        try { button.setPointerCapture(event.pointerId); } catch (_) {}
      }
    };
    const stop=event=>{event.preventDefault();pressedDirections.delete(dir);};
    button.addEventListener("pointerdown",start);
    button.addEventListener("pointerup",stop);
    button.addEventListener("pointercancel",stop);
    button.addEventListener("lostpointercapture",stop);
    button.addEventListener("contextmenu",event=>event.preventDefault());
  });
  loadState().then(data=>{
    if (data && window.Phaser) bootGame();
    else if (data && !window.Phaser) ui.status.textContent="The 2D engine could not load. Check your connection and reopen the Mini App.";
  }).catch(error=>{
    ui.status.textContent=error.message || "Could not load the game. Reopen it from Telegram.";
  });
  window.setInterval(()=>{
    if(document.hidden||requestInFlight||!gameState||!gameState.matchmaking||gameState.matchmaking.status!=="matched")return;
    loadState().catch(()=>{});
  },10000);
  document.addEventListener("visibilitychange",()=>{
    if (!document.hidden && initData && !requestInFlight) {
      loadState().catch(()=>{});
    }
  });
})();
