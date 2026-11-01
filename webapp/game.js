(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) { tg.ready(); tg.expand(); }
  const initData = tg ? tg.initData : "";
  const ui = {
    coins: document.getElementById("coins"),
    name: document.getElementById("hero-name"),
    heroClass: document.getElementById("hero-class"),
    level: document.getElementById("level"),
    hp: document.getElementById("hp"),
    stamina: document.getElementById("stamina"),
    staminaFill: document.getElementById("stamina-fill"),
    mana: document.getElementById("mana"),
    manaFill: document.getElementById("mana-fill"),
    xp: document.getElementById("xp-fill"),
    region: document.getElementById("region"),
    monster: document.getElementById("monster-label"),
    status: document.getElementById("status"),
    encounter: document.getElementById("encounter"),
    interact: document.getElementById("interact-npc"),
    battlePanel: document.getElementById("battle-panel"),
    battleName: document.getElementById("battle-name"),
    battleHp: document.getElementById("battle-hp"),
    battleHpFill: document.getElementById("battle-hp-fill"),
    battleMessage: document.getElementById("battle-message"),
    potionCount: document.getElementById("potion-count"),
    appearanceStatus: document.getElementById("appearance-status"),
    questList: document.getElementById("quest-list"),
    dailyMissionList: document.getElementById("daily-mission-list"),
    socialOverview: document.getElementById("social-overview"),
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
  const pressedDirections = new Set();
  let nearMonster = false;
  let nearNpc = false;
  let requestInFlight = false;
  let phaserGame = null;
  let soundEnabled = true;
  let audioContext = null;


  function playSound(kind) {
    if (!soundEnabled) return;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      audioContext = audioContext || new AudioContextClass();
      if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
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

  function applyState(data, message) {
    const previousRegion = gameState ? gameState.region : null;
    const previousMonster = gameState ? gameState.monster.level : null;
    gameState = data;
    ui.name.textContent = data.first_name || "Adventurer";
    ui.heroClass.textContent = data.class_selected ? data.hero_class + " · " + data.weapon : "Choose a class in chat";
    ui.level.textContent = "Lv. " + data.level;
    ui.hp.textContent = "❤️ " + data.hp + " / " + data.max_hp;
    if (data.mana && ui.mana) {
      ui.mana.textContent = data.mana.mana + " / " + data.mana.max_mana;
      if (ui.manaFill) ui.manaFill.style.width = (data.mana.mana / data.mana.max_mana * 100) + "%";
    }
    if (data.stamina && ui.stamina) {
      ui.stamina.textContent = data.stamina.stamina + " / " + data.stamina.max_stamina;
      if (ui.staminaFill) ui.staminaFill.style.width = (data.stamina.stamina / data.stamina.max_stamina * 100) + "%";
    }
    ui.coins.textContent = data.coins;
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
      ["race","skin","hair","outfit"].forEach(key => {
        const field = document.getElementById("appearance-" + key);
        if (field) field.value = data.appearance[key];
      });
    }
    renderQuests(data.quests || []);
    renderDailyMissions(data.daily_missions || []);
    renderSocial(data.social || {});
    renderDungeon(data.dungeon || null, data.dungeons || []);
    renderMaterials(data.materials || {});
    renderStory(data.story || []);
    if (data.settings) {
      const notifications = document.getElementById("setting-notifications");
      const privacy = document.getElementById("setting-privacy");
      if (notifications) notifications.value = data.settings.notifications_enabled ? "1" : "0";
      if (privacy) privacy.value = data.settings.profile_visibility;
    }
    ui.xp.style.width = Math.max(0, Math.min(100, data.xp / data.xp_required * 100)) + "%";
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
      ui.battleHpFill.style.width = Math.max(0, battle.hp / battle.max_hp * 100) + "%";
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
        const locked=document.createElement("p");locked.textContent="Reach level "+chapter.level+" and complete the previous chapter.";card.appendChild(locked);
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
    };
    addCard("Friends",(social.friends||[]).map(x=>x.username+" · Lv."+x.level));
    const party=social.party;
    addCard("Party",party ? ["Party #"+party.party_id,...party.members.map(x=>x.username+" · Lv."+x.level)] : ["Not in a party. Use /party create."]);
    const guild=social.guild;
    addCard("Guild",guild ? [guild.name+" · Lv."+guild.level+" · "+guild.role,...guild.members.map(x=>x.username+" · "+x.role)] : ["Not in a guild. Use /guild create."]);
    if (social.pending_trades) {
      const note=document.createElement("p"); note.className="small"; note.textContent="🤝 Pending trades: "+social.pending_trades;
      ui.socialOverview.appendChild(note);
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

  async function loadState() {
    if (!initData) {
      ui.status.textContent = "Open this game from the Telegram bot's private chat.";
      return null;
    }
    const response = await fetch("/api/state", {
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
    const response = await fetch(path, {
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
      const result = await postApi("/api/action", {action});
      playSound(action === "skill" ? "skill" : action === "potion" ? "potion" : action === "attack" ? "attack" : "error");
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
    const g = scene.add.graphics();
    const cloak = {traveler:0x344d68,knight:0x596a86,mage:0x654b88,ranger:0x41684f}[appearance.outfit] || ({Knight:0x344d68,Mage:0x654b88,Archer:0x41684f,Berserker:0x8a4138}[heroClass] || 0x25374a);
    const skin = {fair:0xf1d2b5,warm:0xe2b98d,tan:0xb97850,deep:0x70442f}[appearance.skin] || 0xe2b98d;
    g.fillStyle(cloak,1); g.fillRoundedRect(-15,-5,30,29,8);
    g.lineStyle(3,0x172334,1); g.strokeRoundedRect(-15,-5,30,29,8);
    g.fillStyle(skin,1); g.fillCircle(0,-15,11);
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
    g.fillStyle(0x273a52,1); g.fillRoundedRect(-12,0,24,18,5);
    g.lineStyle(3,0xc9d4dc,1); g.beginPath(); g.moveTo(13,-3); g.lineTo(26,-25); g.strokePath();
    g.lineStyle(4,0x9b7044,1); g.beginPath(); g.moveTo(10,1); g.lineTo(18,-10); g.strokePath();
    g.fillStyle(0x171b25,1); g.fillCircle(-4,-16,1.5); g.fillCircle(4,-16,1.5);
    c.add(g); c.setDepth(10); return c;
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
      const w=this.scale.width*1.5,h=this.scale.height*1.5;
      this.worldWidth=w;this.worldHeight=h;
      const idx=Math.max(0,Math.min(9,gameState ? Math.floor((gameState.level-1)/10):0));
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
      this.obstacles = [
        {x:w*0.39,y:h*0.61,width:42,height:58},
        {x:w*0.57,y:h*0.77,width:58,height:34},
        {x:w*0.68,y:h*0.51,width:46,height:54},
        {x:w*0.31,y:h*0.84,width:50,height:28}
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
      this.hero=makeHero(this,w*0.22,h*0.7,gameState.hero_class,gameState.appearance);
      this.cameras.main.setBounds(0,0,this.worldWidth,this.worldHeight);
      this.cameras.main.startFollow(this.hero,true,0.08,0.08);
      this.npc = makeHero(this,w*0.49,h*0.7,"Mage");
      this.npc.setScale(0.9);
      this.obstacles.push({x:this.npc.x,y:this.npc.y,width:34,height:34});
      this.npcLabel = this.add.text(w*0.49,h*0.7-44,"WANDERER",{fontFamily:"Georgia",fontSize:"12px",color:"#fff4d6",stroke:"#17232a",strokeThickness:3}).setOrigin(0.5);
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
      this.heroIdle = this.tweens.add({
        targets:this.hero, y:this.hero.y-3, duration:650, yoyo:true, repeat:-1, ease:"Sine.easeInOut"
      });
      this.add.text(this.cameras.main.width*0.5,28,worldNames[idx],{fontFamily:"Georgia",fontSize:"19px",color:"#fff4d6",stroke:"#17232a",strokeThickness:4}).setOrigin(0.5).setScrollFactor(0);
      this.cursors=this.input.keyboard.createCursorKeys();
      this.keys=this.input.keyboard.addKeys("W,A,S,D,E");
      this.input.keyboard.addCapture(["UP","DOWN","LEFT","RIGHT","W","A","S","D"]);
      this.input.on("pointerdown",()=>{
        if(nearMonster)this.challenge();
        else if(nearNpc)this.talkToNpc();
      });
      this.physics=null;
    }
    challenge(){
      if(this.selectedMonster)startEncounter(this.selectedMonster.level);
    }
    talkToNpc(){
      if(!nearNpc || (gameState && gameState.battle_active))return;
      const idx=Math.max(0,Math.min(9,Math.floor((gameState.level-1)/10)));
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
      if(gameState && gameState.battle_active){ui.encounter.disabled=true;return;}
      const speed=0.18*delta;
      let dx=0,dy=0;
      if(this.cursors.left.isDown||this.keys.A.isDown||pressedDirections.has("left"))dx=-1;
      if(this.cursors.right.isDown||this.keys.D.isDown||pressedDirections.has("right"))dx=1;
      if(this.cursors.up.isDown||this.keys.W.isDown||pressedDirections.has("up"))dy=-1;
      if(this.cursors.down.isDown||this.keys.S.isDown||pressedDirections.has("down"))dy=1;
      if(dx&&dy){dx*=0.707;dy*=0.707;}
      const nextX=Phaser.Math.Clamp(this.hero.x+dx*speed,24,this.worldWidth-24);
      if(!this.blockedAt(nextX,this.hero.y))this.hero.x=nextX;
      const nextY=Phaser.Math.Clamp(this.hero.y+dy*speed,this.worldHeight*0.46,this.worldHeight-24);
      if(!this.blockedAt(this.hero.x,nextY))this.hero.y=nextY;
      let closest=null,closestDistance=Infinity;
      this.monsters.forEach(entry=>{
        const distance=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,entry.sprite.x,entry.sprite.y);
        if(distance<closestDistance){closestDistance=distance;closest=entry;}
      });
      nearMonster=closestDistance<88;
      this.selectedMonster=nearMonster?closest:null;
      nearNpc=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,this.npc.x,this.npc.y)<72;
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

  document.getElementById("sound-toggle").addEventListener("click", event => {
    soundEnabled = !soundEnabled;
    event.currentTarget.setAttribute("aria-pressed", String(soundEnabled));
    event.currentTarget.textContent = soundEnabled ? "🔊 Sound" : "🔇 Muted";
    if (soundEnabled) playSound("potion");
  });


  if(ui.dailyMissionList) ui.dailyMissionList.addEventListener("click",event=>{
    const button=event.target.closest("[data-daily-mission-id]");
    if(button) claimDailyMission(button);
  });

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
  document.addEventListener("visibilitychange",()=>{
    if (!document.hidden && initData && !requestInFlight) {
      loadState().catch(()=>{});
    }
  });
})();
