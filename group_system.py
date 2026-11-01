"""Persistent Telegram group progression, missions, raids and moderation."""
from datetime import datetime, timezone
import aiosqlite

MISSIONS = {
    "battles": ("Battle Together", 5, 120, 40),
    "boss": ("Boss Breakers", 1, 250, 80),
    "trades": ("Fair Exchange", 2, 100, 30),
}
ACTIVITY = {"battle":"battles", "boss":"boss", "trade":"trades"}

class GroupError(ValueError):
    pass

def valid_chat(value):
    return isinstance(value,int) and not isinstance(value,bool) and value < 0

def valid_user(value):
    return isinstance(value,int) and not isinstance(value,bool) and value > 0

async def init_group_tables(db):
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS group_profiles(
      chat_id INTEGER PRIMARY KEY,title TEXT NOT NULL,owner_id INTEGER NOT NULL,
      group_level INTEGER NOT NULL DEFAULT 1,group_xp INTEGER NOT NULL DEFAULT 0,
      announcement TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS group_admins(
      chat_id INTEGER NOT NULL,user_id INTEGER NOT NULL,role TEXT NOT NULL CHECK(role IN ('owner','admin')),
      PRIMARY KEY(chat_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS group_players(
      chat_id INTEGER NOT NULL,user_id INTEGER NOT NULL,username TEXT,player_level INTEGER NOT NULL DEFAULT 1,
      joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(chat_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS group_missions(
      chat_id INTEGER NOT NULL,mission_date TEXT NOT NULL,mission_id TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0,claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(chat_id,mission_date,mission_id)
    );
    CREATE TABLE IF NOT EXISTS group_raids(
      raid_id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,boss_level INTEGER NOT NULL,
      boss_name TEXT NOT NULL,max_hp INTEGER NOT NULL,hp INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS group_raid_contributions(
      raid_id INTEGER NOT NULL,user_id INTEGER NOT NULL,damage INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY(raid_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS group_bans(
      chat_id INTEGER NOT NULL,user_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,reason TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(chat_id,user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_group_rank ON group_profiles(group_level DESC,group_xp DESC);
    """)
    await db.commit()

async def register_group(db,chat_id,title,owner_id):
    if not valid_chat(chat_id) or not valid_user(owner_id):
        raise GroupError("Only Telegram groups and supergroups can be registered.")
    title=" ".join(str(title or "").split())[:100]
    if not title: raise GroupError("Group title cannot be empty.")
    await db.execute("""INSERT INTO group_profiles(chat_id,title,owner_id) VALUES(?,?,?)
      ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,owner_id=excluded.owner_id""",
      (chat_id,title,owner_id))
    await db.execute("""INSERT INTO group_admins(chat_id,user_id,role) VALUES(?,?,'owner')
      ON CONFLICT(chat_id,user_id) DO UPDATE SET role='owner'""",(chat_id,owner_id))
    await db.commit()

async def set_group_admin(db,chat_id,user_id,role):
    if not valid_chat(chat_id) or not valid_user(user_id) or role not in {"owner","admin"}:
        raise GroupError("Invalid group administrator.")
    cur=await db.execute("SELECT 1 FROM group_profiles WHERE chat_id=?",(chat_id,))
    if not await cur.fetchone(): raise GroupError("Register this group first.")
    if role=="owner":
        await db.execute("UPDATE group_admins SET role='admin' WHERE chat_id=? AND role='owner'",(chat_id,))
        await db.execute("UPDATE group_profiles SET owner_id=? WHERE chat_id=?",(user_id,chat_id))
    await db.execute("""INSERT INTO group_admins(chat_id,user_id,role) VALUES(?,?,?)
      ON CONFLICT(chat_id,user_id) DO UPDATE SET role=excluded.role""",(chat_id,user_id,role))
    await db.commit()

async def is_group_admin(db,chat_id,user_id):
    cur=await db.execute("SELECT role FROM group_admins WHERE chat_id=? AND user_id=?",(chat_id,user_id))
    return await cur.fetchone()

async def record_group_player(db,chat_id,user_id,username,level):
    if not valid_chat(chat_id) or not valid_user(user_id) or not isinstance(level,int) or isinstance(level,bool) or not 1<=level<=100:
        raise GroupError("Invalid group player.")
    cur=await db.execute("SELECT 1 FROM group_profiles WHERE chat_id=?",(chat_id,))
    if not await cur.fetchone(): raise GroupError("Register this group first.")
    name=" ".join(str(username or "Adventurer").split())[:64]
    await db.execute("""INSERT INTO group_players(chat_id,user_id,username,player_level) VALUES(?,?,?,?)
      ON CONFLICT(chat_id,user_id) DO UPDATE SET username=excluded.username,player_level=excluded.player_level,last_seen=CURRENT_TIMESTAMP""",
      (chat_id,user_id,name,level))
    await db.commit()

async def list_group_players(db,chat_id):
    cur=await db.execute("SELECT user_id,username,player_level FROM group_players WHERE chat_id=? ORDER BY player_level DESC,username COLLATE NOCASE",(chat_id,))
    return await cur.fetchall()

async def get_group_profile(db,chat_id):
    if not valid_chat(chat_id): raise GroupError("This command only works inside a Telegram group.")
    cur=await db.execute("""SELECT g.*,COUNT(DISTINCT p.user_id) player_count,COUNT(DISTINCT a.user_id) admin_count
      FROM group_profiles g LEFT JOIN group_players p ON p.chat_id=g.chat_id
      LEFT JOIN group_admins a ON a.chat_id=g.chat_id WHERE g.chat_id=? GROUP BY g.chat_id""",(chat_id,))
    row=await cur.fetchone()
    if not row: raise GroupError("This group is not registered. Use /group register.")
    return row

async def award_group_xp(db,chat_id,amount):
    if not valid_chat(chat_id) or not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=5000:
        raise GroupError("Invalid group XP award.")
    cur=await db.execute("SELECT group_level,group_xp FROM group_profiles WHERE chat_id=?",(chat_id,))
    row=await cur.fetchone()
    if not row: raise GroupError("Register this group first.")
    level,xp=row["group_level"],row["group_xp"]+amount
    while level<100 and xp>=level*500:
        xp-=level*500; level+=1
    await db.execute("UPDATE group_profiles SET group_level=?,group_xp=? WHERE chat_id=?",(level,xp,chat_id))
    await db.commit()
    return level,xp

def today():
    return datetime.now(timezone.utc).date().isoformat()

async def get_group_missions(db,chat_id,mission_date=None):
    date=mission_date or today()
    for key in MISSIONS:
        await db.execute("INSERT OR IGNORE INTO group_missions(chat_id,mission_date,mission_id) VALUES(?,?,?)",(chat_id,date,key))
    await db.commit()
    cur=await db.execute("SELECT mission_id,progress,claimed FROM group_missions WHERE chat_id=? AND mission_date=?",(chat_id,date))
    rows=await cur.fetchall()
    return [{"id":r["mission_id"],"title":MISSIONS[r["mission_id"]][0],"target":MISSIONS[r["mission_id"]][1],
      "reward":MISSIONS[r["mission_id"]][2],"xp":MISSIONS[r["mission_id"]][3],"progress":r["progress"],
      "claimed":bool(r["claimed"]),"completed":r["progress"]>=MISSIONS[r["mission_id"]][1]} for r in rows]

async def record_group_activity(db,chat_id,kind,amount=1):
    key=ACTIVITY.get(kind)
    if not valid_chat(chat_id) or key is None or not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=20:
        raise GroupError("Invalid group activity.")
    missions=await get_group_missions(db,chat_id)
    target=MISSIONS[key][1]
    await db.execute("UPDATE group_missions SET progress=MIN(?,progress+?) WHERE chat_id=? AND mission_date=? AND mission_id=?",
      (target,amount,chat_id,today(),key))
    await db.commit()
    return await get_group_missions(db,chat_id)

async def claim_group_mission(db,chat_id,user_id,mission_id):
    if mission_id not in MISSIONS or not await is_group_admin(db,chat_id,user_id):
        raise GroupError("Only verified group admins can claim a valid group mission.")
    missions=await get_group_missions(db,chat_id)
    mission=next(x for x in missions if x["id"]==mission_id)
    if not mission["completed"]: raise GroupError("This group mission is not complete.")
    if mission["claimed"]: raise GroupError("This group mission reward was already claimed.")
    await db.execute("UPDATE group_missions SET claimed=1 WHERE chat_id=? AND mission_date=? AND mission_id=? AND claimed=0",
      (chat_id,today(),mission_id))
    await db.commit()
    await award_group_xp(db,chat_id,mission["xp"])
    return mission["reward"],mission["xp"]

async def start_group_raid(db,chat_id,user_id,boss_level,boss_name,boss_hp):
    if not valid_chat(chat_id) or not await is_group_admin(db,chat_id,user_id):
        raise GroupError("Only verified group admins can start a raid.")
    if not isinstance(boss_level,int) or isinstance(boss_level,bool) or not 10<=boss_level<=100 or boss_level%10:
        raise GroupError("Raid boss level must be a milestone from 10 to 100.")
    if not isinstance(boss_hp,int) or isinstance(boss_hp,bool) or not 1<=boss_hp<=10_000_000:
        raise GroupError("Invalid raid boss health.")
    cur=await db.execute("SELECT 1 FROM group_raids WHERE chat_id=? AND status='active'",(chat_id,))
    if await cur.fetchone(): raise GroupError("This group already has an active raid.")
    cur=await db.execute("INSERT INTO group_raids(chat_id,boss_level,boss_name,max_hp,hp) VALUES(?,?,?,?,?)",
      (chat_id,boss_level,str(boss_name)[:80],boss_hp,boss_hp))
    await db.commit()
    return cur.lastrowid

async def attack_group_raid(db,chat_id,user_id,damage):
    if not isinstance(damage,int) or isinstance(damage,bool) or not 1<=damage<=10000:
        raise GroupError("Invalid raid damage.")
    cur=await db.execute("SELECT 1 FROM group_players WHERE chat_id=? AND user_id=?",(chat_id,user_id))
    if not await cur.fetchone(): raise GroupError("Join this group's player roster before attacking.")
    cur=await db.execute("SELECT * FROM group_raids WHERE chat_id=? AND status='active' ORDER BY raid_id DESC LIMIT 1",(chat_id,))
    raid=await cur.fetchone()
    if not raid: raise GroupError("There is no active group raid.")
    damage=min(damage,raid["hp"]); hp=raid["hp"]-damage; status="won" if hp==0 else "active"
    await db.execute("UPDATE group_raids SET hp=?,status=? WHERE raid_id=? AND status='active'",(hp,status,raid["raid_id"]))
    await db.execute("""INSERT INTO group_raid_contributions(raid_id,user_id,damage) VALUES(?,?,?)
      ON CONFLICT(raid_id,user_id) DO UPDATE SET damage=damage+excluded.damage""",(raid["raid_id"],user_id,damage))
    await db.commit()
    return {"boss_name":raid["boss_name"],"hp":hp,"max_hp":raid["max_hp"],"damage":damage,"status":status}

async def group_raid_status(db,chat_id):
    cur=await db.execute("SELECT * FROM group_raids WHERE chat_id=? ORDER BY raid_id DESC LIMIT 1",(chat_id,))
    return await cur.fetchone()

async def set_group_ban(db,chat_id,actor_id,target_id,banned,reason=""):
    if not valid_chat(chat_id) or not valid_user(actor_id) or not valid_user(target_id) or actor_id==target_id:
        raise GroupError("Invalid moderation target.")
    if not await is_group_admin(db,chat_id,actor_id): raise GroupError("Only verified group admins can moderate.")
    cur=await db.execute("SELECT owner_id FROM group_profiles WHERE chat_id=?",(chat_id,))
    owner=await cur.fetchone()
    if not owner: raise GroupError("Register this group first.")
    if owner["owner_id"]==target_id: raise GroupError("The group owner cannot be blocked.")
    if banned:
        await db.execute("INSERT OR REPLACE INTO group_bans(chat_id,user_id,actor_id,reason) VALUES(?,?,?,?)",
          (chat_id,target_id,actor_id," ".join(str(reason or "").split())[:200]))
    else:
        await db.execute("DELETE FROM group_bans WHERE chat_id=? AND user_id=?",(chat_id,target_id))
    await db.commit()

async def is_group_banned(db,chat_id,user_id):
    cur=await db.execute("SELECT 1 FROM group_bans WHERE chat_id=? AND user_id=?",(chat_id,user_id))
    return await cur.fetchone() is not None

async def top_groups(db,limit=10):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=50: raise GroupError("Invalid leaderboard limit.")
    cur=await db.execute("SELECT chat_id,title,group_level,group_xp FROM group_profiles ORDER BY group_level DESC,group_xp DESC LIMIT ?",(limit,))
    return await cur.fetchall()
