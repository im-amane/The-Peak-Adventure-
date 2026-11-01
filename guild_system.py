"""Advanced guild roles, invitations, missions and shared boss raids."""
from datetime import datetime, timezone

class GuildFeatureError(ValueError):
    pass

MISSIONS={
 "battles":("Battle Together",5,60),
 "boss":("Boss Breakers",1,120),
 "trades":("Guild Traders",3,45),
}
ACTIVITY={"battle":"battles","boss":"boss","trade":"trades"}

def valid_id(value):
    return isinstance(value,int) and not isinstance(value,bool) and value>0

async def init_guild_features(db):
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS guild_invites(
      invite_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,
      inviter_id INTEGER NOT NULL,target_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','cancelled')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,responded_at TEXT
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_invite_pending
      ON guild_invites(target_id) WHERE status='pending';
    CREATE TABLE IF NOT EXISTS guild_announcements(
      guild_id INTEGER PRIMARY KEY,message TEXT NOT NULL,author_id INTEGER NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS guild_missions(
      guild_id INTEGER NOT NULL,mission_date TEXT NOT NULL,mission_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0,claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(guild_id,mission_date,mission_id)
    );
    CREATE TABLE IF NOT EXISTS guild_raids(
      raid_id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,
      boss_level INTEGER NOT NULL,boss_name TEXT NOT NULL,max_hp INTEGER NOT NULL,hp INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','won')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS guild_raid_contributions(
      raid_id INTEGER NOT NULL,user_id INTEGER NOT NULL,damage INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(raid_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS guild_raid_cooldowns(
      raid_id INTEGER NOT NULL,user_id INTEGER NOT NULL,last_attack_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(raid_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS guild_wars(
      war_id INTEGER PRIMARY KEY AUTOINCREMENT,challenger_guild INTEGER NOT NULL,
      target_guild INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending'
      CHECK(status IN ('pending','active','completed','declined')),
      winner_guild INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      challenger_score INTEGER NOT NULL DEFAULT 0,target_score INTEGER NOT NULL DEFAULT 0,
      CHECK(challenger_guild!=target_guild)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_war_pair
      ON guild_wars(challenger_guild,target_guild) WHERE status IN ('pending','active');
    """)
    await db.commit()

async def guild_role(db,guild_id,user_id):
    cur=await db.execute("SELECT role FROM guild_members WHERE guild_id=? AND user_id=?",(guild_id,user_id))
    row=await cur.fetchone()
    return row["role"] if row else None

async def _officer(db,guild_id,user_id):
    role=await guild_role(db,guild_id,user_id)
    return role in {"leader","officer"}

async def create_guild_invite(db,guild_id,actor_id,target_id):
    if not all(valid_id(x) for x in (guild_id,actor_id,target_id)) or actor_id==target_id:
        raise GuildFeatureError("Invalid guild invitation.")
    if not await _officer(db,guild_id,actor_id):
        raise GuildFeatureError("Only guild leaders and officers can invite players.")
    cur=await db.execute("SELECT 1 FROM players WHERE user_id=?",(target_id,))
    if not await cur.fetchone(): raise GuildFeatureError("That player has not registered yet.")
    cur=await db.execute("SELECT 1 FROM guild_members WHERE user_id=?",(target_id,))
    if await cur.fetchone(): raise GuildFeatureError("That player is already in a guild.")
    cur=await db.execute("SELECT COUNT(*) n FROM guild_members WHERE guild_id=?",(guild_id,))
    if (await cur.fetchone())["n"]>=20: raise GuildFeatureError("This guild is full.")
    try:
        cur=await db.execute("INSERT INTO guild_invites(guild_id,inviter_id,target_id) VALUES(?,?,?)",(guild_id,actor_id,target_id))
        await db.commit()
        return int(cur.lastrowid)
    except Exception as exc:
        await db.rollback()
        raise GuildFeatureError("That player already has a pending guild invitation.") from exc

async def respond_guild_invite(db,invite_id,target_id,accept):
    if not valid_id(invite_id) or not valid_id(target_id): raise GuildFeatureError("Invalid guild invitation.")
    cur=await db.execute("SELECT guild_id,target_id,status FROM guild_invites WHERE invite_id=?",(invite_id,))
    invite=await cur.fetchone()
    if not invite or invite["status"]!="pending": raise GuildFeatureError("This invitation is no longer active.")
    if invite["target_id"]!=target_id: raise GuildFeatureError("Only the invited player can respond.")
    if accept:
        cur=await db.execute("SELECT 1 FROM guild_members WHERE user_id=?",(target_id,))
        if await cur.fetchone(): raise GuildFeatureError("You are already in a guild.")
        cur=await db.execute("SELECT COUNT(*) n FROM guild_members WHERE guild_id=?",(invite["guild_id"],))
        if (await cur.fetchone())["n"]>=20: raise GuildFeatureError("That guild is already full.")
        await db.execute("INSERT INTO guild_members(user_id,guild_id,role) VALUES(?,?,'member')",(target_id,invite["guild_id"]))
        status="accepted"
    else: status="declined"
    await db.execute("UPDATE guild_invites SET status=?,responded_at=CURRENT_TIMESTAMP WHERE invite_id=? AND status='pending'",(status,invite_id))
    await db.commit()
    return invite["guild_id"]

async def set_guild_role(db,guild_id,actor_id,target_id,role):
    if not all(valid_id(x) for x in (guild_id,actor_id,target_id)) or role not in {"officer","member"}:
        raise GuildFeatureError("Invalid guild role update.")
    cur=await db.execute("SELECT role FROM guild_members WHERE guild_id=? AND user_id=?",(guild_id,actor_id))
    actor=await cur.fetchone()
    if not actor or actor["role"]!="leader": raise GuildFeatureError("Only the guild leader can change roles.")
    cur=await db.execute("SELECT role FROM guild_members WHERE guild_id=? AND user_id=?",(guild_id,target_id))
    target=await cur.fetchone()
    if not target: raise GuildFeatureError("That player is not in this guild.")
    if target["role"]=="leader": raise GuildFeatureError("Guild leader role cannot be changed.")
    await db.execute("UPDATE guild_members SET role=? WHERE guild_id=? AND user_id=?",(role,guild_id,target_id))
    await db.commit()

async def set_guild_announcement(db,guild_id,actor_id,message):
    if not await _officer(db,guild_id,actor_id): raise GuildFeatureError("Only guild leaders and officers can post announcements.")
    message=" ".join(str(message or "").split())
    if not message or len(message)>500: raise GuildFeatureError("Announcement must contain 1 to 500 characters.")
    await db.execute("""INSERT INTO guild_announcements(guild_id,message,author_id) VALUES(?,?,?)
      ON CONFLICT(guild_id) DO UPDATE SET message=excluded.message,author_id=excluded.author_id,updated_at=CURRENT_TIMESTAMP""",
      (guild_id,message,actor_id))
    await db.commit()
    return message

async def get_guild_announcement(db,guild_id):
    cur=await db.execute("SELECT message,author_id,updated_at FROM guild_announcements WHERE guild_id=?",(guild_id,))
    return await cur.fetchone()

def _date(value=None):
    return value or datetime.now(timezone.utc).date().isoformat()

async def get_guild_missions(db,guild_id,mission_date=None):
    date=_date(mission_date)
    for key in MISSIONS:
        await db.execute("INSERT OR IGNORE INTO guild_missions(guild_id,mission_date,mission_id) VALUES(?,?,?)",(guild_id,date,key))
    await db.commit()
    cur=await db.execute("SELECT mission_id,progress,claimed FROM guild_missions WHERE guild_id=? AND mission_date=?",(guild_id,date))
    rows=await cur.fetchall()
    return [{"id":r["mission_id"],"title":MISSIONS[r["mission_id"]][0],"target":MISSIONS[r["mission_id"]][1],
      "xp":MISSIONS[r["mission_id"]][2],"progress":r["progress"],"claimed":bool(r["claimed"]),
      "completed":r["progress"]>=MISSIONS[r["mission_id"]][1]} for r in rows]

async def record_guild_activity(db,guild_id,user_id,kind,amount=1):
    key=ACTIVITY.get(kind)
    if key is None or not valid_id(guild_id) or not valid_id(user_id) or not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=20:
        raise GuildFeatureError("Invalid guild activity.")
    cur=await db.execute("SELECT 1 FROM guild_members WHERE guild_id=? AND user_id=?",(guild_id,user_id))
    if not await cur.fetchone(): return []
    date=_date()
    await get_guild_missions(db,guild_id,date)
    target=MISSIONS[key][1]
    await db.execute("UPDATE guild_missions SET progress=MIN(?,progress+?) WHERE guild_id=? AND mission_date=? AND mission_id=?",(target,amount,guild_id,date,key))
    await db.commit()
    return await get_guild_missions(db,guild_id,date)

async def claim_guild_mission(db,guild_id,user_id,mission_id,mission_date=None):
    if mission_id not in MISSIONS or not await _officer(db,guild_id,user_id):
        raise GuildFeatureError("Only guild leaders and officers can claim a completed mission.")
    date=_date(mission_date)
    missions=await get_guild_missions(db,guild_id,date)
    mission=next(x for x in missions if x["id"]==mission_id)
    if not mission["completed"]: raise GuildFeatureError("This guild mission is not complete.")
    if mission["claimed"]: raise GuildFeatureError("This guild mission reward was already claimed.")
    await db.execute("UPDATE guild_missions SET claimed=1 WHERE guild_id=? AND mission_date=? AND mission_id=? AND claimed=0",(guild_id,date,mission_id))
    cur=await db.execute("SELECT guild_level,guild_xp FROM guilds WHERE guild_id=?",(guild_id,))
    guild=await cur.fetchone()
    if not guild: raise GuildFeatureError("Guild not found.")
    level,xp=guild["guild_level"],guild["guild_xp"]+mission["xp"]
    while level<100 and xp>=level*500: xp-=level*500; level+=1
    await db.execute("UPDATE guilds SET guild_level=?,guild_xp=? WHERE guild_id=?",(level,xp,guild_id))
    await db.commit()
    return mission["xp"]

async def start_guild_raid(db,guild_id,user_id,boss_level,boss_name,boss_hp):
    if not await _officer(db,guild_id,user_id): raise GuildFeatureError("Only guild leaders and officers can start guild raids.")
    if not isinstance(boss_level,int) or isinstance(boss_level,bool) or not 10<=boss_level<=100 or boss_level%10:
        raise GuildFeatureError("Raid boss level must be a milestone from 10 to 100.")
    if not isinstance(boss_hp,int) or isinstance(boss_hp,bool) or not 1<=boss_hp<=10_000_000:
        raise GuildFeatureError("Invalid guild raid boss health.")
    cur=await db.execute("SELECT 1 FROM guild_raids WHERE guild_id=? AND status='active'",(guild_id,))
    if await cur.fetchone(): raise GuildFeatureError("Your guild already has an active raid.")
    cur=await db.execute("INSERT INTO guild_raids(guild_id,boss_level,boss_name,max_hp,hp) VALUES(?,?,?,?,?)",(guild_id,boss_level,str(boss_name)[:80],boss_hp,boss_hp))
    await db.commit()
    return int(cur.lastrowid)

async def attack_guild_raid(db,guild_id,user_id,damage):
    if not all(valid_id(x) for x in (guild_id,user_id)) or not isinstance(damage,int) or isinstance(damage,bool) or not 1<=damage<=10000:
        raise GuildFeatureError("Invalid guild raid attack.")
    cur=await db.execute("SELECT 1 FROM guild_members WHERE guild_id=? AND user_id=?",(guild_id,user_id))
    if not await cur.fetchone(): raise GuildFeatureError("Only guild members can join this raid.")
    cur=await db.execute("SELECT * FROM guild_raids WHERE guild_id=? AND status='active' ORDER BY raid_id DESC LIMIT 1",(guild_id,))
    raid=await cur.fetchone()
    if not raid: raise GuildFeatureError("There is no active guild raid.")
    cur=await db.execute("SELECT 1 FROM guild_raid_cooldowns WHERE raid_id=? AND user_id=? AND julianday(CURRENT_TIMESTAMP)-julianday(last_attack_at)<(5.0/86400)",(raid["raid_id"],user_id))
    if await cur.fetchone(): raise GuildFeatureError("Guild raid cooldown: wait 5 seconds before attacking again.")
    dealt=min(damage,raid["hp"]); hp=raid["hp"]-dealt; status="won" if hp==0 else "active"
    await db.execute("UPDATE guild_raids SET hp=?,status=? WHERE raid_id=? AND status='active'",(hp,status,raid["raid_id"]))
    await db.execute("INSERT INTO guild_raid_cooldowns(raid_id,user_id,last_attack_at) VALUES(?,?,CURRENT_TIMESTAMP) ON CONFLICT(raid_id,user_id) DO UPDATE SET last_attack_at=CURRENT_TIMESTAMP",(raid["raid_id"],user_id))
    await db.execute("""INSERT INTO guild_raid_contributions(raid_id,user_id,damage) VALUES(?,?,?)
      ON CONFLICT(raid_id,user_id) DO UPDATE SET damage=damage+excluded.damage""",(raid["raid_id"],user_id,dealt))
    await db.commit()
    if status=="won":
        await db.execute("UPDATE guilds SET guild_xp=guild_xp+100 WHERE guild_id=?",(guild_id,))
        await db.commit()
    return {"boss_name":raid["boss_name"],"hp":hp,"max_hp":raid["max_hp"],"damage":dealt,"status":status}


async def declare_guild_war(db, guild_id, leader_id, target_guild_id):
    if not all(valid_id(x) for x in (guild_id,leader_id,target_guild_id)) or guild_id==target_guild_id:
        raise GuildFeatureError("Invalid guild war challenge.")
    if await guild_role(db,guild_id,leader_id)!="leader":
        raise GuildFeatureError("Only guild leaders can declare a war.")
    cur=await db.execute("SELECT 1 FROM guilds WHERE guild_id=?",(target_guild_id,))
    if not await cur.fetchone(): raise GuildFeatureError("Target guild not found.")
    cur=await db.execute("""SELECT 1 FROM guild_wars WHERE status IN ('pending','active')
      AND ((challenger_guild=? AND target_guild=?) OR (challenger_guild=? AND target_guild=?))""",
      (guild_id,target_guild_id,target_guild_id,guild_id))
    if await cur.fetchone(): raise GuildFeatureError("A war between these guilds is already pending or active.")
    cur=await db.execute("INSERT INTO guild_wars(challenger_guild,target_guild) VALUES(?,?)",(guild_id,target_guild_id))
    await db.commit()
    return int(cur.lastrowid)


async def respond_guild_war(db, war_id, leader_id, accept):
    if not valid_id(war_id) or not valid_id(leader_id): raise GuildFeatureError("Invalid guild war response.")
    cur=await db.execute("SELECT * FROM guild_wars WHERE war_id=? AND status='pending'",(war_id,))
    war=await cur.fetchone()
    if not war: raise GuildFeatureError("This guild war challenge is no longer pending.")
    if await guild_role(db,war["target_guild"],leader_id)!="leader":
        raise GuildFeatureError("Only the challenged guild leader can respond.")
    status="active" if accept else "declined"
    await db.execute("UPDATE guild_wars SET status=? WHERE war_id=? AND status='pending'",(status,war_id))
    await db.commit()
    return status


async def record_guild_war_duel(db, challenger_id, opponent_id, winner_id):
    if not all(valid_id(x) for x in (challenger_id,opponent_id,winner_id)) or winner_id not in {challenger_id,opponent_id}:
        return None
    cur=await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?",(challenger_id,))
    first=await cur.fetchone()
    cur=await db.execute("SELECT guild_id FROM guild_members WHERE user_id=?",(opponent_id,))
    second=await cur.fetchone()
    if not first or not second or first["guild_id"]==second["guild_id"]: return None
    cur=await db.execute("""SELECT * FROM guild_wars WHERE status='active' AND
      ((challenger_guild=? AND target_guild=?) OR (challenger_guild=? AND target_guild=?))
      ORDER BY war_id DESC LIMIT 1""",
      (first["guild_id"],second["guild_id"],second["guild_id"],first["guild_id"]))
    war=await cur.fetchone()
    if not war: return None
    winner_member=first if winner_id==challenger_id else second
    winner_guild=winner_member["guild_id"]
    if winner_guild==war["challenger_guild"]:
        await db.execute("UPDATE guild_wars SET challenger_score=challenger_score+1 WHERE war_id=?",(war["war_id"],))
    else:
        await db.execute("UPDATE guild_wars SET target_score=target_score+1 WHERE war_id=?",(war["war_id"],))
    cur=await db.execute("SELECT * FROM guild_wars WHERE war_id=?",(war["war_id"],))
    updated=await cur.fetchone()
    completed=max(updated["challenger_score"],updated["target_score"])>=3
    if completed:
        winner=updated["challenger_guild"] if updated["challenger_score"]>updated["target_score"] else updated["target_guild"]
        await db.execute("UPDATE guild_wars SET status='completed',winner_guild=? WHERE war_id=?",(winner,war["war_id"]))
        await db.execute("UPDATE guilds SET guild_xp=guild_xp+150 WHERE guild_id=?",(winner,))
    await db.commit()
    cur=await db.execute("SELECT * FROM guild_wars WHERE war_id=?",(war["war_id"],))
    return await cur.fetchone()


async def get_guild_war(db,war_id):
    cur=await db.execute("SELECT * FROM guild_wars WHERE war_id=?",(war_id,))
    return await cur.fetchone()

async def guild_raid_status(db,guild_id):
    cur=await db.execute("SELECT * FROM guild_raids WHERE guild_id=? ORDER BY raid_id DESC LIMIT 1",(guild_id,))
    return await cur.fetchone()
