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
    potionCount: document.getElementById("potion-count")
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

  function applyState(data, message) {
    const previousRegion = gameState ? gameState.region : null;
    const previousMonster = gameState ? gameState.monster.level : null;
    gameState = data;
    ui.name.textContent = data.first_name || "Adventurer";
    ui.heroClass.textContent = data.class_selected ? data.hero_class + " · " + data.weapon : "Choose a class in chat";
    ui.level.textContent = "Lv. " + data.level;
    ui.hp.textContent = "❤️ " + data.hp + " / " + data.max_hp;
    ui.coins.textContent = data.coins;
    ui.xp.style.width = Math.max(0, Math.min(100, data.xp / data.xp_required * 100)) + "%";
    ui.region.textContent = data.region;
    ui.monster.textContent = "Lv. " + data.monster.level + " · " + data.monster.name;
    const battle = data.battle;
    ui.battlePanel.hidden = !battle;
    document.querySelectorAll("[data-action]").forEach(button => {
      button.disabled = !battle || requestInFlight;
    });
    if (battle) {
      ui.battleName.textContent = battle.name + " · Lv." + battle.level;
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

  async function startEncounter() {
    if (!gameState.class_selected) { ui.status.textContent = "Choose your class in the Telegram chat first."; return; }
    if (gameState.battle_active) { ui.status.textContent = "You already have an active battle."; return; }
    if (requestInFlight) return;
    requestInFlight = true;
    ui.encounter.disabled = true;
    try {
      const result = await postApi("/api/explore", {});
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
      applyState(result.state, result.message);
    } catch (error) {
      ui.battleMessage.textContent = error.message;
      await loadState().catch(() => null);
    } finally {
      requestInFlight = false;
      if (gameState) applyState(gameState);
    }
  }

  function makeHero(scene, x, y, heroClass) {
    const c = scene.add.container(x,y);
    const g = scene.add.graphics();
    const cloak = {Knight:0x344d68,Mage:0x654b88,Archer:0x41684f,Berserker:0x8a4138}[heroClass] || 0x25374a;
    g.fillStyle(cloak,1); g.fillRoundedRect(-15,-5,30,29,8);
    g.lineStyle(3,0x172334,1); g.strokeRoundedRect(-15,-5,30,29,8);
    g.fillStyle(0xe2b98d,1); g.fillCircle(0,-15,11);
    g.fillStyle(0x382b2b,1); g.fillEllipse(0,-23,22,12);
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
      const w=this.scale.width,h=this.scale.height;
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
      this.hero=makeHero(this,w*0.22,h*0.7,gameState.hero_class);
      this.npc = makeHero(this,w*0.49,h*0.7,"Mage");
      this.npc.setScale(0.9);
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
      this.monster=makeMonster(this,w*0.77,h*0.68,gameState.monster.level,monsterColor);
      this.heroIdle = this.tweens.add({
        targets:this.hero, y:this.hero.y-3, duration:650, yoyo:true, repeat:-1, ease:"Sine.easeInOut"
      });
      this.monsterIdle = this.tweens.add({
        targets:this.monster, y:this.monster.y-5, duration:850, yoyo:true, repeat:-1, ease:"Sine.easeInOut"
      });
      this.add.text(w*0.77,h*0.68-54,gameState.monster.name,{fontFamily:"Georgia",fontSize:"13px",color:"#fff4d6",stroke:"#1b1b24",strokeThickness:3}).setOrigin(0.5);
      this.add.text(w*0.5,h*0.12,worldNames[idx],{fontFamily:"Georgia",fontSize:"19px",color:"#fff4d6",stroke:"#17232a",strokeThickness:4}).setOrigin(0.5);
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
      startEncounter();
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
      if(gameState && gameState.battle_active){ui.encounter.disabled=true;return;}
      const speed=0.18*delta;
      let dx=0,dy=0;
      if(this.cursors.left.isDown||this.keys.A.isDown||pressedDirections.has("left"))dx=-1;
      if(this.cursors.right.isDown||this.keys.D.isDown||pressedDirections.has("right"))dx=1;
      if(this.cursors.up.isDown||this.keys.W.isDown||pressedDirections.has("up"))dy=-1;
      if(this.cursors.down.isDown||this.keys.S.isDown||pressedDirections.has("down"))dy=1;
      if(dx&&dy){dx*=0.707;dy*=0.707;}
      const nextX=Phaser.Math.Clamp(this.hero.x+dx*speed,24,this.scale.width-24);
      if(!this.blockedAt(nextX,this.hero.y))this.hero.x=nextX;
      const nextY=Phaser.Math.Clamp(this.hero.y+dy*speed,this.scale.height*0.46,this.scale.height-24);
      if(!this.blockedAt(this.hero.x,nextY))this.hero.y=nextY;
      const distance=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,this.monster.x,this.monster.y);
      nearMonster=distance<88;
      nearNpc=Phaser.Math.Distance.Between(this.hero.x,this.hero.y,this.npc.x,this.npc.y)<72;
      ui.interact.disabled=!nearNpc;
      ui.interact.textContent=nearNpc?"💬 Talk to Wanderer":"💬 Find Wanderer";
      if(Phaser.Input.Keyboard.JustDown(this.keys.E))this.talkToNpc();
      ui.encounter.disabled=!nearMonster||!gameState.class_selected||gameState.battle_active;
      ui.encounter.textContent=nearMonster?"⚔️ Challenge Monster":"⚔️ Find the monster";
      if(nearMonster)ui.status.textContent="The creature has noticed you. Prepare for battle.";
    }
  }

  function bootGame(){
    if(!gameState)return;
    const config={type:Phaser.AUTO,parent:"game",width:900,height:500,backgroundColor:"#344b3e",scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH},scene:[AdventureScene]};
    if (phaserGame) phaserGame.destroy(true);
    phaserGame = new Phaser.Game(config);
  }
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
