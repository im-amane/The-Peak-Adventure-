"""Player privacy settings and explicit account deletion."""
from guild_system import disband_guild

class AccountError(ValueError):
    pass

DEFAULT_SETTINGS={"notifications_enabled":1,"profile_visibility":"public","sound_enabled":1}

async def _atomic_start(db, name):
    nested = db.in_transaction
    await db.execute("SAVEPOINT " + name if nested else "BEGIN IMMEDIATE")
    return nested

async def _atomic_finish(db, name, nested):
    await db.execute("RELEASE SAVEPOINT " + name) if nested else await db.commit()

async def _atomic_rollback(db, name, nested):
    if nested:
        await db.execute("ROLLBACK TO SAVEPOINT " + name)
        await db.execute("RELEASE SAVEPOINT " + name)
    else:
        await db.rollback()


def _is_postgres(db):
    return getattr(db, "dialect", "sqlite") == "postgres"


async def _table_exists(db, table):
    if _is_postgres(db):
        cur = await db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=current_schema() AND table_name=? AND table_type='BASE TABLE'",
            (table,),
        )
    else:
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
    return await cur.fetchone() is not None


async def _column_exists(db, table, column):
    if _is_postgres(db):
        cur = await db.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=? AND column_name=?",
            (table, column),
        )
        return await cur.fetchone() is not None
    cur = await db.execute(f"PRAGMA table_info({table})")
    return column in {row["name"] for row in await cur.fetchall()}


async def init_account_tables(db):
    name = "init_account_tables"
    nested = await _atomic_start(db, name)
    user_id_type = "BIGINT" if _is_postgres(db) else "INTEGER"
    try:
        await db.execute(f"""CREATE TABLE IF NOT EXISTS player_settings(
          user_id {user_id_type} PRIMARY KEY,
          notifications_enabled INTEGER NOT NULL DEFAULT 1 CHECK(notifications_enabled IN (0,1)),
          profile_visibility TEXT NOT NULL DEFAULT 'public' CHECK(profile_visibility IN ('public','friends')),
          sound_enabled INTEGER NOT NULL DEFAULT 1 CHECK(sound_enabled IN (0,1)),
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        if _is_postgres(db):
            await db.execute(
                "ALTER TABLE player_settings ALTER COLUMN user_id TYPE BIGINT"
            )
        if not await _column_exists(db, "player_settings", "sound_enabled"):
            await db.execute("ALTER TABLE player_settings ADD COLUMN sound_enabled INTEGER NOT NULL DEFAULT 1 CHECK(sound_enabled IN (0,1))")
        await _atomic_finish(db, name, nested)
    except Exception:
        await _atomic_rollback(db, name, nested)
        raise

async def get_settings(db,user_id):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0: raise AccountError("Invalid player account.")
    cur=await db.execute("SELECT notifications_enabled,profile_visibility,sound_enabled FROM player_settings WHERE user_id=?",(user_id,))
    row=await cur.fetchone()
    return dict(row) if row else dict(DEFAULT_SETTINGS)

async def update_settings(db,user_id,notifications_enabled=None,profile_visibility=None,sound_enabled=None):
    if not isinstance(user_id,int) or isinstance(user_id,bool) or user_id<=0: raise AccountError("Invalid player account.")
    current=await get_settings(db,user_id)
    if notifications_enabled is not None:
        if not isinstance(notifications_enabled,bool): raise AccountError("Notification setting must be on or off.")
        current["notifications_enabled"]=int(notifications_enabled)
    if profile_visibility is not None:
        if not isinstance(profile_visibility,str) or profile_visibility not in {"public","friends"}: raise AccountError("Profile visibility must be public or friends.")
        current["profile_visibility"]=profile_visibility
    if sound_enabled is not None:
        if not isinstance(sound_enabled,bool): raise AccountError("Sound setting must be on or off.")
        current["sound_enabled"]=int(sound_enabled)
    name = "update_player_settings"
    nested = await _atomic_start(db, name)
    try:
        await db.execute("""INSERT INTO player_settings(user_id,notifications_enabled,profile_visibility,sound_enabled) VALUES(?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET notifications_enabled=excluded.notifications_enabled,
          profile_visibility=excluded.profile_visibility,sound_enabled=excluded.sound_enabled,updated_at=CURRENT_TIMESTAMP""",
          (user_id,current["notifications_enabled"],current["profile_visibility"],current["sound_enabled"]))
        await _atomic_finish(db, name, nested)
    except Exception:
        await _atomic_rollback(db, name, nested)
        raise
    return current

async def _delete_player_account_unlocked(db,user_id):
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
                # Demote only the departing leader. Existing officers must keep
                # their permissions when leadership is transferred.
                cur=await db.execute(
                    "UPDATE guild_members SET role='member' WHERE guild_id=? AND user_id=? AND role='leader'",
                    (guild_id,user_id),
                )
                if cur.rowcount!=1:
                    raise AccountError("Guild leadership changed during account deletion.")
                cur=await db.execute(
                    "UPDATE guild_members SET role='leader' WHERE guild_id=? AND user_id=?",
                    (guild_id,successor["user_id"]),
                )
                if cur.rowcount!=1:
                    raise AccountError("Guild successor membership could not be updated.")
                cur=await db.execute(
                    "UPDATE guilds SET leader_id=? WHERE guild_id=? AND leader_id=?",
                    (successor["user_id"],guild_id,user_id),
                )
                if cur.rowcount!=1:
                    raise AccountError("Guild ownership changed during account deletion.")
            else:
                await disband_guild(db,guild_id,user_id)
        await db.execute("DELETE FROM guild_members WHERE user_id=?",(user_id,))
    cur=await db.execute("SELECT chat_id FROM group_profiles WHERE owner_id=?",(user_id,))
    for group in await cur.fetchall():
        chat_id=group["chat_id"]
        cur=await db.execute("SELECT user_id FROM group_admins WHERE chat_id=? AND user_id!=? ORDER BY role DESC,user_id LIMIT 1",(chat_id,user_id))
        successor=await cur.fetchone()
        if successor:
            cur=await db.execute(
                "UPDATE group_admins SET role='admin' WHERE chat_id=? AND user_id=? AND role='owner'",
                (chat_id,user_id),
            )
            if cur.rowcount!=1:
                raise AccountError("Group ownership changed during account deletion.")
            cur=await db.execute(
                "UPDATE group_admins SET role='owner' WHERE chat_id=? AND user_id=? AND role='admin'",
                (chat_id,successor["user_id"]),
            )
            if cur.rowcount!=1:
                raise AccountError("Group owner successor could not be promoted.")
            cur=await db.execute(
                "UPDATE group_profiles SET owner_id=? WHERE chat_id=? AND owner_id=?",
                (successor["user_id"],chat_id,user_id),
            )
            if cur.rowcount!=1:
                raise AccountError("Group ownership record could not be updated.")
        else:
            await db.execute("DELETE FROM group_raid_contributions WHERE raid_id IN (SELECT raid_id FROM group_raids WHERE chat_id=?)",(chat_id,))
            await db.execute("DELETE FROM group_raid_cooldowns WHERE raid_id IN (SELECT raid_id FROM group_raids WHERE chat_id=?)",(chat_id,))
            for table in ("group_profiles","group_admins","group_players","group_missions","group_raids","group_bans"):
                await db.execute(f"DELETE FROM {table} WHERE chat_id=?",(chat_id,))
    await db.execute("DELETE FROM guild_invites WHERE inviter_id=? OR target_id=?",(user_id,user_id))
    await db.execute("DELETE FROM guild_announcements WHERE author_id=?",(user_id,))
    if await _table_exists(db, "guild_chat_messages"):
        await db.execute("DELETE FROM guild_chat_messages WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM guild_raid_contributions WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM guild_raid_cooldowns WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM friend_requests WHERE user_low=? OR user_high=?",(user_id,user_id))
    await db.execute("DELETE FROM party_invites WHERE inviter_id=? OR target_id=?",(user_id,user_id))
    await db.execute("DELETE FROM party_battle_contributions WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM party_battle_cooldowns WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM party_battle_rewards WHERE user_id=?",(user_id,))
    cur=await db.execute("SELECT party_id FROM party_members WHERE user_id=?",(user_id,))
    party=await cur.fetchone()
    if party:
        party_id=party["party_id"]
        cur=await db.execute("SELECT leader_id FROM parties WHERE party_id=?",(party_id,))
        party_row=await cur.fetchone()
        if party_row and party_row["leader_id"]==user_id:
            cur=await db.execute("SELECT user_id FROM party_members WHERE party_id=? AND user_id!=? ORDER BY joined_at,user_id LIMIT 1",(party_id,user_id))
            successor=await cur.fetchone()
            if successor:
                cur=await db.execute(
                    "UPDATE parties SET leader_id=? WHERE party_id=? AND leader_id=?",
                    (successor["user_id"],party_id,user_id),
                )
                if cur.rowcount!=1:
                    raise AccountError("Party leadership changed during account deletion.")
            else:
                await db.execute("DELETE FROM party_battle_contributions WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)",(party_id,))
                await db.execute("DELETE FROM party_battle_cooldowns WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)",(party_id,))
                await db.execute("DELETE FROM party_battle_rewards WHERE battle_id IN (SELECT battle_id FROM party_battles WHERE party_id=?)",(party_id,))
                await db.execute("DELETE FROM party_battles WHERE party_id=?",(party_id,))
                await db.execute("DELETE FROM parties WHERE party_id=?",(party_id,))
        await db.execute("DELETE FROM party_members WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_players WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_admins WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_bans WHERE user_id=? OR actor_id=?",(user_id,user_id))
    await db.execute("DELETE FROM group_raid_contributions WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM group_raid_cooldowns WHERE user_id=?",(user_id,))
    if await _table_exists(db, "guild_war_duel_events"):
        await db.execute(
            """DELETE FROM guild_war_duel_events
               WHERE winner_id=? OR duel_id IN (
                 SELECT duel_id FROM duels WHERE challenger_id=? OR opponent_id=?
               )""",
            (user_id,user_id,user_id),
        )
    await db.execute("DELETE FROM duels WHERE challenger_id=? OR opponent_id=?",(user_id,user_id))
    # Return escrow and close/reopen auctions before deleting the player's account.
    if await _table_exists(db, "auction_listings"):
        cur=await db.execute("SELECT listing_id,current_bid,highest_bidder FROM auction_listings WHERE seller_id=? AND status='active'",(user_id,))
        for listing in await cur.fetchall():
            if listing["highest_bidder"] is not None:
                cur=await db.execute(
                    "UPDATE players SET coins=coins+? WHERE user_id=?",
                    (listing["current_bid"],listing["highest_bidder"]),
                )
                if cur.rowcount!=1:
                    raise AccountError("Auction escrow could not be refunded; account deletion was rolled back.")
            cur=await db.execute(
                "UPDATE auction_listings SET status='cancelled' WHERE listing_id=? AND status='active'",
                (listing["listing_id"],),
            )
            if cur.rowcount!=1:
                raise AccountError("Auction changed during account deletion; the operation was rolled back.")
        await db.execute("UPDATE auction_listings SET highest_bidder=NULL,current_bid=0 WHERE highest_bidder=? AND status='active'",(user_id,))
        await db.execute("DELETE FROM auction_stash WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM trades WHERE initiator_id=? OR partner_id=?",(user_id,user_id))
    # Remove records added by optional gameplay services when those services are installed.
    for table, where, params in (
        ("player_reports","reporter_id=? OR target_id=?",(user_id,user_id)),
        ("security_events","user_id=?",(user_id,)),
        ("premium_wallets","user_id=?",(user_id,)),
        ("premium_transactions","user_id=?",(user_id,)),
        ("premium_shop_purchases","user_id=?",(user_id,)),
        ("player_xp_boosts","user_id=?",(user_id,)),
        ("player_bans","user_id=?",(user_id,)),
        ("player_weekly_quests","user_id=?",(user_id,)),
        ("player_daily_missions","user_id=?",(user_id,)),
        ("player_monster_mastery","user_id=?",(user_id,)),
        ("player_secret_areas","user_id=?",(user_id,)),
        ("roaming_event_participants","user_id=?",(user_id,)),
        ("player_stamina","user_id=?",(user_id,)),
        ("player_mana","user_id=?",(user_id,)),
    ):
        if await _table_exists(db, table):
            await db.execute(f"DELETE FROM {table} WHERE {where}",params)
    for table in ("battles","daily_claims","boss_defeats","monster_discoveries","quest_progress","achievement_progress","character_appearance","player_settings","dungeon_runs","dungeon_rewards","player_materials","crafted_items","player_worlds","player_presence","world_discoveries","player_story","story_flags","story_reward_claims"):
        await db.execute(f"DELETE FROM {table} WHERE user_id=?",(user_id,))
    await db.execute("DELETE FROM players WHERE user_id=?",(user_id,))
    return True

async def delete_player_account(db,user_id):
    """Delete a player and linked records atomically, including inside an outer transaction."""
    savepoint = db.in_transaction
    try:
        if savepoint:
            await db.execute("SAVEPOINT delete_player_account")
        else:
            await db.execute("BEGIN IMMEDIATE")
        result = await _delete_player_account_unlocked(db,user_id)
        if savepoint:
            await db.execute("RELEASE SAVEPOINT delete_player_account")
        else:
            await db.commit()
        return result
    except Exception:
        if savepoint:
            await db.execute("ROLLBACK TO SAVEPOINT delete_player_account")
            await db.execute("RELEASE SAVEPOINT delete_player_account")
        else:
            await db.rollback()
        raise