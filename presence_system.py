"""Privacy-conscious recent activity presence."""
import aiosqlite

async def init_presence_tables(db: aiosqlite.Connection):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_presence(
      user_id INTEGER PRIMARY KEY,last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_player_presence_seen ON player_presence(last_seen)")
    await db.commit()

async def touch_presence(db: aiosqlite.Connection,user_id: int):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0:return
    await db.execute("""INSERT INTO player_presence(user_id,last_seen) VALUES(?,CURRENT_TIMESTAMP)
      ON CONFLICT(user_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP""",(user_id,))
    await db.commit()

async def count_online_players(db: aiosqlite.Connection,window_minutes: int=5):
    if not isinstance(window_minutes,int) or isinstance(window_minutes,bool) or not 1<=window_minutes<=60:
        raise ValueError("Presence window must be between 1 and 60 minutes.")
    cur=await db.execute("SELECT COUNT(*) AS total FROM player_presence WHERE julianday(CURRENT_TIMESTAMP)-julianday(last_seen)<(?/1440.0)",(window_minutes,))
    return (await cur.fetchone())["total"]

async def list_online_friends(db: aiosqlite.Connection,user_id: int,window_minutes: int=5):
    cur=await db.execute("""SELECT p.user_id,p.username,p.level,pr.last_seen FROM friend_requests f
      JOIN players p ON p.user_id=CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END
      JOIN player_presence pr ON pr.user_id=p.user_id
      LEFT JOIN player_settings s ON s.user_id=p.user_id
      WHERE f.status='accepted' AND (f.user_low=? OR f.user_high=?)
      AND julianday(CURRENT_TIMESTAMP)-julianday(pr.last_seen)<(?/1440.0)
      AND COALESCE(s.profile_visibility,'public')!='private'
      ORDER BY pr.last_seen DESC""",(user_id,user_id,user_id,window_minutes))
    return await cur.fetchall()
