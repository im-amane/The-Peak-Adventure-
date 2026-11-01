"""Player privacy settings and explicit account deletion."""
import aiosqlite

class AccountError(ValueError):
    pass

DEFAULT_SETTINGS={"notifications_enabled":1,"profile_visibility":"public"}

async def init_account_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS player_settings(
      user_id INTEGER PRIMARY KEY,
      notifications_enabled INTEGER NOT NULL DEFAULT 1 CHECK(notifications_enabled IN (0,1)),
      profile_visibility TEXT NOT NULL DEFAULT 'public' CHECK(profile_visibility IN ('public','friends')),
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    await db.commit()

async def get_settings(db,user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0: raise AccountError("Invalid player account.")
    cur=await db.execute("SELECT notifications_enabled,profile_visibility FROM player_settings WHERE user_id=?",(user_id,))
    row=await cur.fetchone()
    return dict(row) if row else dict(DEFAULT_SETTINGS)

async def update_settings(db,user_id,notifications_enabled=None,profile_visibility=None):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0: raise AccountError("Invalid player account.")
    current=await get_settings(db,user_id)
    if notifications_enabled is not None:
        if not isinstance(notifications_enabled,bool): raise AccountError("Notification setting must be on or off.")
        current["notifications_enabled"]=int(notifications_enabled)
    if profile_visibility is not None:
        if profile_visibility not in {"public","friends"}: raise AccountError("Profile visibility must be public or friends.")
        current["profile_visibility"]=profile_visibility
    await db.execute("""INSERT INTO player_settings(user_id,notifications_enabled,profile_visibility) VALUES(?,?,?)
      ON CONFLICT(user_id) DO UPDATE SET notifications_enabled=excluded.notifications_enabled,
      profile_visibility=excluded.profile_visibility,updated_at=CURRENT_TIMESTAMP""",
      (user_id,current["notifications_enabled"],current["profile_visibility"]))
    await db.commit()
    return current

async def delete_player_account(db,user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0: raise AccountError("Invalid player account.")
    cur=await db.execute("SELECT 1 FROM players WHERE user_id=?",(user_id,))
    if not await cur.fetchone(): raise AccountError("Player account not found.")
    cur=await db.execute("SELECT guild_id,role FROM guild_members WHERE user_id=?",(user_id,))
    membership=await cur.fetchone()
    if membership:
        guild_id=membership["guild_id"]
        if membership["role"]=="leader":
            cur=await db.execute("""SELECT gm.user_id FROM guild_members gm JOIN players p ON p.user_id=gm.user_id
              WHERE gm.guild_id=? AND gm.user_id!=? ORDER BY p.level DESC,p.xp DESC,gm.joined_at LIMIT 1""",(guild_id,user_id))
            successor=await cur.fetchone()
            if successor:
                await db.execute("UPDATE guild_members SET role='member' WHERE guild_id=?",(guild_id,))
                await db.execute("UPDATE guild_members SET role='leader' WHERE user_id=?",(successor["user_id"],))
                await db.execute("UPDATE guilds SET leader_id=? WHERE guild_id=?",(successor["user_id"],guild_id))
            else: await db.execute("DELETE FROM guilds WHERE guild_id=?",(guild_id,))
        await db.execute("DELETE FROM guild_members WHERE user_id=?",(user_id,))
    cur=await db.execute("SELECT chat_id FROM group_profiles WHERE owner_id=?",(user_id,))
    for group in await cur.fetchall():
        chat_id=group["chat_id"]
        cur=await db.execute("SELECT user_id FROM group_admins WHERE chat_id=? AND user_id!=? ORDER BY role DESC,user_id LIMIT 1",(chat_id,user_id))
        successor=await cur.fetchone()
        if successor:
            await db.execute("UPDATE group_admins SET role='admin' WHERE chat_id=? AND role='owner'",(chat_id,))
            await db.execute("UPDATE group_admins SET role='owner' WHERE chat_id=? AND user_id=?",(chat_id,successor["user_id"]))
            await db.execute("UPDATE group_profiles SET owner_id=? WHERE chat_id=?",(successor["user_id"],chat_id))
        else:
            await db.execute("DELETE FROM group_raid_contributions WHERE raid_id IN (SELECT raid_id FROM group_raids WHERE chat_id=?)",(chat_id,))
            for table in ("group_profiles","group_admins","group_players","group_missions","group_raids","group_bans"):
                await db.execute(f"DELETE FROM {table} WHERE chat_id=?",(chat_id,))
    await db.execute("DELETE FROM friend_requests WHERE user_low=? OR user_high=?",(user_id,user_id))
    await db.execute("DELETE FROM party_invites WHERE inviter_id=? OR target_id=?",(user_id,user_id))
    cur=await db.execute("SELECT party_id FROM party_members WHERE user_id=?",(user_id,))
    party=await cur.fetchone()
    if party:
        party_id=party["party_id"]
        cur=await db.execute("SELECT leader_id FROM parties WHERE party_id=?",(party_id,))
        party_row=await cur.fetchone()
        if party_row and party_row["leader_id"]==user_id:
            cur=await db.execute("SELECT user_id FROM party_members WHERE party_id=? AND user_id!=? ORDER BY joined_at,user_id LIMIT 1",(party_id,user_id))
            successor=await cur.fetchone()
            if successor: await db.execute("UPDATE parties SET leader_id=? WHERE party_id=?",(successor["user_id"],party_id))
            else: await db.execute("DELETE FROM parties WHERE party_id=?",(party_id,))
        await db.execute("DELETE FROM party_members WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_players WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_admins WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_bans WHERE user_id=? OR actor_id=?",(user_id,user_id))
    await db.execute("DELETE FROM group_raid_contributions WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM duels WHERE challenger_id=? OR opponent_id=?",(user_id,user_id))
    await db.execute("DELETE FROM trades WHERE initiator_id=? OR partner_id=?",(user_id,user_id))
    for table in ("battles","daily_claims","boss_defeats","monster_discoveries","quest_progress","achievement_progress","character_appearance","player_settings"):
        await db.execute(f"DELETE FROM {table} WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM players WHERE user_id=?",(user_id,))
    await db.commit()
    return True