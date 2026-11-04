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

def validate_story_campaign() -> None:
    """Fail fast when chapter content can break campaign progression or UI rendering."""
    if not isinstance(CHAPTERS, list) or len(CHAPTERS) != 10:
        raise ValueError("The story campaign must define exactly ten chapters.")
    previous_level = 0
    for expected_id, chapter in enumerate(CHAPTERS, start=1):
        if not isinstance(chapter, dict) or chapter.get("id") != expected_id:
            raise ValueError("Story chapter IDs must be unique and sequential from 1 to 10.")
        level = chapter.get("level")
        reward = chapter.get("reward")
        world = chapter.get("world")
        if type(level) is not int or not previous_level < level <= 100:
            raise ValueError(f"Story chapter {expected_id} has an invalid progression level.")
        if type(world) is not int or not 1 <= world <= 10:
            raise ValueError(f"Story chapter {expected_id} has an invalid world.")
        if type(reward) is not int or reward <= 0:
            raise ValueError(f"Story chapter {expected_id} has an invalid reward.")
        for field in ("title", "npc", "scene"):
            if not isinstance(chapter.get(field), str) or not chapter[field].strip():
                raise ValueError(f"Story chapter {expected_id} is missing {field} content.")
        if len(chapter["scene"].split()) < 20:
            raise ValueError(f"Story chapter {expected_id} scene is too short for cinematic presentation.")
        choices = chapter.get("choices")
        if (not isinstance(choices, dict) or len(choices) < 2
                or any(not isinstance(key, str) or not key.strip()
                       or not isinstance(label, str) or not label.strip()
                       for key, label in choices.items())):
            raise ValueError(f"Story chapter {expected_id} must have at least two valid choices.")
        if "requires_party" in chapter and type(chapter["requires_party"]) is not bool:
            raise ValueError(f"Story chapter {expected_id} has an invalid party gate.")
        previous_level = level


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
    validate_story_campaign()
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
    has_party = False
    if any(chapter.get("requires_party") for chapter in CHAPTERS):
        cur=await db.execute("SELECT 1 FROM party_members WHERE user_id=? LIMIT 1",(user_id,))
        has_party = await cur.fetchone() is not None
    branch_scenes={
        2: {
            "opening_path": {
                "mira": " Mira's lantern trail leads you toward the old bridge; she walks close enough that your shoulders almost touch.",
                "wanderer": " The Wanderer has left a second set of footprints beside yours, as if someone else is following the compass."
            }
        },
        3: {
            "trust_path": {
                "mira": " Mira stands beside you. She has chosen not to run this time.",
                "wanderer": " The Wanderer walks ahead, carrying the compass with both hands."
            }
        },
        4: {
            "memory_path": {
                "truth": " The name you spoke returns as a warm echo, and the roots loosen around the bell's buried chain.",
                "silence": " The sealed name remains beneath the roots; the bell answers with one more silent pulse."
            }
        },
        5: {
            "echo_path": {
                "freed": " Echo's freed voices gather around the Ashen King's throne, each remembering a child he helped protect.",
                "questioned": " Echo's unanswered question follows you to the throne: who gave the king the order to burn the village?"
            }
        },
        6: {
            "crown_path": {
                "mercy": " The Ashen King gives Mira the key he kept from the fire, trusting her to decide when you are ready.",
                "revenge": " The Ashen King's final warning follows Mira into the snow: the fire was never meant to kill you."
            }
        },
        7: {
            "forgiveness_path": {
                "forgiven": " Mira carries the lantern openly now; the light no longer flickers when your eyes meet.",
                "time": " Mira keeps pace without asking for forgiveness, protecting the silence you still need."
            }
        },
        8: {
            "bargain_path": {
                "refused": " The Herald's imitation of your sibling fades, leaving a real voice somewhere beyond the rift.",
                "deception": " The Herald believes your bargain; a thin silver crack appears across the rift's seal."
            }
        },
        9: {
            "lantern_path": {
                "together": " The lantern's shared light reveals several safe paths through the frozen hour.",
                "alone": " The lantern burns in your hands alone, and every shadow turns toward the one carrying it."
            }
        },
        10: {
            "opening_path": {
                "mira": " The lantern Mira first carried still burns at your side.",
                "wanderer": " The masked Wanderer stands at the summit, the compass finally pointing home."
            },
            "trust_path": {
                "mira": " Mira keeps the compass close, honoring the trust you placed in her.",
                "wanderer": " The Wanderer lays the compass at your feet, its needle steady at last."
            },
            "memory_path": {
                "truth": " The names you spoke are carved into the summit stone, no longer hidden.",
                "silence": " The sealed name remains yours to reveal when you are ready."
            },
            "echo_path": {
                "freed": " The freed voices rise together beneath the dawn.",
                "questioned": " Echo's question remains unanswered, waiting beyond the final light."
            },
            "crown_path": {
                "mercy": " The Ashen King's key rests in Mira's hand, a promise that mercy can outlive fire.",
                "revenge": " The Ashen King's warning follows you: the fire was never meant to kill you."
            },
            "forgiveness_path": {
                "forgiven": " Mira stands beside you without fear, the old wound finally allowed to close.",
                "time": " Mira stands beside you without demanding an answer; trust has room to grow."
            },
            "bargain_path": {
                "refused": " The Herald's false promise is gone, but a true voice answers from beyond the rift.",
                "deception": " The silver crack in the rift remains, proof that the bargain may yet demand its price."
            },
            "lantern_path": {
                "together": " The lantern answers every companion's light, brighter than it has ever been.",
                "alone": " The lantern remembers the weight you carried alone, even as your companions gather."
            },
            "burden_path": {
                "shared": " Your companions stand at the summit beside you; the final hour belongs to all of you.",
                "solo": " Your companions refuse to leave you alone at the summit; the cost will not be yours alone."
            }
        }
    }
    result=[]
    for chapter in CHAPTERS:
        requires_party=chapter.get("requires_party",False)
        unlocked=(
            player_level>=chapter["level"]
            and (chapter["id"]==1 or chapter["id"]-1 in done)
            and (not requires_party or has_party)
        )
        scene=chapter["scene"]
        for flag,variants in branch_scenes.get(chapter["id"],{}).items():
            scene += variants.get(flags.get(flag,""),"")
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
    choice_flags={
        1: ("opening_path", {"follow_mira":"mira","follow_wanderer":"wanderer"}),
        2: ("trust_path", {"trust_mira":"mira","trust_wanderer":"wanderer"}),
        3: ("memory_path", {"speak_truth":"truth","keep_silent":"silence"}),
        4: ("echo_path", {"free_echo":"freed","question_echo":"questioned"}),
        5: ("crown_path", {"show_mercy":"mercy","seek_revenge":"revenge"}),
        6: ("forgiveness_path", {"forgive_mira":"forgiven","ask_for_time":"time"}),
        7: ("bargain_path", {"reject_bargain":"refused","pretend_accept":"deception"}),
        8: ("lantern_path", {"light_together":"together","carry_alone":"alone"}),
        9: ("burden_path", {"share_the_burden":"shared","take_the_burden":"solo"})
    }
    if chapter_id in choice_flags:
        flag,values=choice_flags[chapter_id]
        value=values[choice_id]
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
