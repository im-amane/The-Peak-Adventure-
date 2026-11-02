"""Branching narrative chapters, NPC choices and cooperative story gates."""
CHAPTERS=[
 {"id":1,"title":"Ashes of Dawn","world":1,"level":1,"npc":"Mira","scene":"The meadow is quiet where a village should be. A little lantern burns in the grass, still warm. Mira finds you beside it and asks whether you remember the name of the person who carried it.","choices":{"follow_mira":"Trust Mira and follow the lantern trail.","follow_wanderer":"Seek the masked Wanderer at the old bridge."},"reward":80},
 {"id":2,"title":"The Broken Compass","world":1,"level":5,"npc":"The Wanderer","scene":"The compass needle points underground. The Wanderer says it belonged to your missing sibling. Mira insists the compass is bait. Neither looks away from the other.","choices":{"trust_mira":"Give Mira the compass and protect the village memory.","trust_wanderer":"Let the Wanderer read the compass and reveal its secret."},"reward":100},
 {"id":3,"title":"Names in the Roots","world":2,"level":11,"npc":"Whispering Tree","scene":"Roots curl around a name carved into the heartwood. It is the name you have tried not to remember. Beneath it, a second name appears only when you speak the truth.","choices":{"speak_truth":"Speak the name aloud and accept the memory.","keep_silent":"Keep the memory sealed for now."},"reward":130},
 {"id":4,"title":"The Silent Bell","world":3,"level":21,"npc":"Echo","scene":"A bell rings without sound above a ruined town. Echo, a child made of pale light, says every lost voice is trapped inside it. One voice knows why the village vanished.","choices":{"free_echo":"Break the bell and free every voice.","question_echo":"Ask Echo who first rang it."},"reward":160},
 {"id":5,"title":"A Crown of Cinders","world":4,"level":31,"npc":"Ashen King","scene":"The Ashen King kneels beside a throne of soot. He did not burn the village for power. He burned it to keep something worse from finding the children hiding below.","choices":{"show_mercy":"Offer the king a chance to make amends.","seek_revenge":"Demand the truth and challenge his crown."},"reward":200},
 {"id":6,"title":"The Frozen Promise","world":5,"level":41,"npc":"Mira","scene":"Mira finally remembers the winter night. She carried the lantern. You carried the compass. Your sibling stayed behind to hold the gate while both of you escaped.","choices":{"forgive_mira":"Forgive her for hiding the truth.","ask_for_time":"Ask for time before you can forgive."},"reward":240},
 {"id":7,"title":"The Rift Below","world":6,"level":51,"npc":"The Hollow Herald","scene":"The Herald speaks with the voice of the missing sibling. It offers to return every lost person if you surrender the names you have recovered. The offer sounds kind. That is what makes it frightening.","choices":{"reject_bargain":"Refuse to trade the living for an imitation.","pretend_accept":"Pretend to accept and search for a weakness."},"reward":280},
 {"id":8,"title":"The Last Lantern","world":7,"level":61,"npc":"The Wanderer","scene":"The lantern can only be lit by people who choose to stand together. Your companions gather around it. For the first time, the darkness retreats when you are not standing alone.","choices":{"light_together":"Light the lantern with your party.","carry_alone":"Try to carry the light alone."},"requires_party":True,"reward":350},
 {"id":9,"title":"The Hour That Remains","world":8,"level":71,"npc":"The Clockmaker","scene":"Time stops at the instant the village disappeared. The Clockmaker offers one final turn of the hands. Someone must remain behind to keep the world moving.","choices":{"share_the_burden":"Ask your companions to share the cost.","take_the_burden":"Choose to bear the cost yourself."},"reward":420},
 {"id":10,"title":"The Peak","world":10,"level":91,"npc":"The Alpha God","scene":"At the summit, the Alpha God wears the face of everyone you failed to save. It calls love a weakness because love is the one force it cannot command. The lantern is burning again.","choices":{"stand_with_all":"Stand with every ally you have gathered.","stand_alone":"Face the Alpha God alone."},"reward":1000}
]

class StoryError(ValueError):
    pass


def _valid_user_id(user_id):
    return isinstance(user_id,int) and not isinstance(user_id,bool) and user_id>0


async def _begin_atomic(db,savepoint):
    nested=db.in_transaction
    if nested:
        await db.execute(f"SAVEPOINT {savepoint}")
    else:
        await db.execute("BEGIN IMMEDIATE")
    return nested


async def _commit_atomic(db,nested,savepoint):
    if nested:
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.commit()


async def _rollback_atomic(db,nested,savepoint):
    if nested:
        await db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        await db.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        await db.rollback()


def _transactional(function):
    """Keep story mutations atomic and preserve caller-owned transactions."""
    from functools import wraps
    @wraps(function)
    async def wrapped(db,*args,**kwargs):
        savepoint="story_"+function.__name__
        nested=await _begin_atomic(db,savepoint)
        try:
            result=await function(db,*args,**kwargs)
            await _commit_atomic(db,nested,savepoint)
            return result
        except Exception:
            await _rollback_atomic(db,nested,savepoint)
            raise
    return wrapped


@_transactional
async def init_story_tables(db):
    """Create story tables without committing a caller-owned transaction."""
    statements=(
        """CREATE TABLE IF NOT EXISTS player_story(
          user_id BIGINT NOT NULL,chapter_id INTEGER NOT NULL,choice_id TEXT NOT NULL,
          completed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,chapter_id)
        )""",
        """CREATE TABLE IF NOT EXISTS story_flags(
          user_id BIGINT NOT NULL,flag TEXT NOT NULL,value TEXT NOT NULL,
          PRIMARY KEY(user_id,flag)
        )""",
        """CREATE TABLE IF NOT EXISTS story_reward_claims(
          user_id BIGINT NOT NULL,chapter_id INTEGER NOT NULL,claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,chapter_id)
        )""",
    )
    for statement in statements:
        await db.execute(statement)


async def get_story_flags(db,user_id):
    cur=await db.execute("SELECT flag,value FROM story_flags WHERE user_id=?",(user_id,))
    return {row["flag"]:row["value"] for row in await cur.fetchall()}


async def get_story_chapters(db,user_id,player_level):
    cur=await db.execute("SELECT chapter_id,choice_id FROM player_story WHERE user_id=?",(user_id,))
    done={row["chapter_id"]:row["choice_id"] for row in await cur.fetchall()}
    flags=await get_story_flags(db,user_id)
    cur=await db.execute("SELECT chapter_id FROM story_reward_claims WHERE user_id=?",(user_id,))
    claimed={row["chapter_id"] for row in await cur.fetchall()}
    result=[]
    for chapter in CHAPTERS:
        unlocked=player_level>=chapter["level"] and (chapter["id"]==1 or chapter["id"]-1 in done)
        scene=chapter["scene"]
        if chapter["id"]==3 and flags.get("trust_path")=="mira": scene += " Mira stands beside you. She has chosen not to run this time."
        elif chapter["id"]==3 and flags.get("trust_path")=="wanderer": scene += " The Wanderer walks ahead, carrying the compass with both hands."
        result.append({"id":chapter["id"],"title":chapter["title"],"world":chapter["world"],"level":chapter["level"],
          "npc":chapter["npc"],"unlocked":unlocked,"completed":chapter["id"] in done,"reward_claimed":chapter["id"] in claimed,
          "choice":done.get(chapter["id"]),"requires_party":chapter.get("requires_party",False),
          "scene":scene,"choices":chapter["choices"],"reward":chapter["reward"],
          "branch_hint":flags.get("trust_path","")})
    return result


@_transactional
async def choose_story_path(db,user_id,player_level,chapter_id,choice_id):
    if not _valid_user_id(user_id):
        raise StoryError("Invalid player account.")
    if not isinstance(player_level,int) or isinstance(player_level,bool) or not 1<=player_level<=100:
        raise StoryError("Invalid player level.")
    if not isinstance(chapter_id,int) or isinstance(chapter_id,bool) or not 1<=chapter_id<=len(CHAPTERS):
        raise StoryError("Story chapter not found.")
    chapter=CHAPTERS[chapter_id-1]
    if player_level<chapter["level"]:
        raise StoryError("This story chapter unlocks at level "+str(chapter["level"])+".")
    cur=await db.execute("SELECT 1 FROM player_story WHERE user_id=? AND chapter_id=?",(user_id,chapter_id))
    if await cur.fetchone():raise StoryError("You have already completed this chapter.")
    if chapter_id>1:
        cur=await db.execute("SELECT 1 FROM player_story WHERE user_id=? AND chapter_id=?",(user_id,chapter_id-1))
        if not await cur.fetchone():raise StoryError("Complete the previous story chapter first.")
    if not isinstance(choice_id,str) or choice_id not in chapter["choices"]:
        raise StoryError("Choose one of the listed story paths.")
    if chapter.get("requires_party"):
        cur=await db.execute("SELECT COUNT(*) n FROM party_members WHERE user_id=?",(user_id,))
        if (await cur.fetchone())["n"]==0:raise StoryError("This chapter requires you to join a party first.")
    await db.execute("INSERT INTO player_story(user_id,chapter_id,choice_id) VALUES(?,?,?)",(user_id,chapter_id,choice_id))
    if chapter_id==2:
        flag="trust_path"
        value="mira" if choice_id=="trust_mira" else "wanderer"
        await db.execute("INSERT INTO story_flags(user_id,flag,value) VALUES(?,?,?) ON CONFLICT(user_id,flag) DO UPDATE SET value=excluded.value",(user_id,flag,value))
    return {"chapter":chapter,"choice":chapter["choices"][choice_id],"reward":chapter["reward"]}


@_transactional
async def claim_story_reward(db,user_id,chapter_id):
    if not _valid_user_id(user_id):
        raise StoryError("Invalid player account.")
    if not isinstance(chapter_id,int) or isinstance(chapter_id,bool) or not 1<=chapter_id<=len(CHAPTERS):
        raise StoryError("Story chapter not found.")
    cur=await db.execute("SELECT 1 FROM player_story WHERE user_id=? AND chapter_id=?",(user_id,chapter_id))
    if not await cur.fetchone():raise StoryError("Complete this chapter before claiming its reward.")
    cur=await db.execute("SELECT 1 FROM story_reward_claims WHERE user_id=? AND chapter_id=?",(user_id,chapter_id))
    if await cur.fetchone():raise StoryError("Story reward already claimed.")
    await db.execute("INSERT INTO story_reward_claims(user_id,chapter_id) VALUES(?,?)",(user_id,chapter_id))
    reward=CHAPTERS[chapter_id-1]["reward"]
    cur=await db.execute("UPDATE players SET coins=coins+? WHERE user_id=?",(reward,user_id))
    if cur.rowcount != 1:
        raise StoryError("The story reward could not be credited.")
    return reward
