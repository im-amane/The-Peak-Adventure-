import aiosqlite
import pytest

from stamina_system import (
    EXPLORE_COST, MAX_STAMINA, REGEN_SECONDS, StaminaError,
    consume_stamina, get_stamina, init_stamina_tables, restore_stamina,
)


@pytest.fixture
async def db():
    connection = await aiosqlite.connect(":memory:")
    connection.row_factory = aiosqlite.Row
    await init_stamina_tables(connection)
    yield connection
    await connection.close()


@pytest.mark.asyncio
async def test_new_player_starts_full(db):
    assert (await get_stamina(db, 101, now=1000))["stamina"] == MAX_STAMINA


@pytest.mark.asyncio
async def test_consumption_is_persistent(db):
    state = await consume_stamina(db, 101, EXPLORE_COST, now=1000)
    assert state["stamina"] == 90
    assert (await get_stamina(db, 101, now=1000))["stamina"] == 90


@pytest.mark.asyncio
async def test_regeneration_uses_elapsed_intervals(db):
    await consume_stamina(db, 101, 30, now=1000)
    assert (await get_stamina(db, 101, now=1000 + 2 * REGEN_SECONDS))["stamina"] == 76


@pytest.mark.asyncio
async def test_cannot_go_below_zero(db):
    await consume_stamina(db, 101, MAX_STAMINA, now=1000)
    with pytest.raises(StaminaError):
        await consume_stamina(db, 101, 1, now=1000)


@pytest.mark.asyncio
async def test_restore_is_capped(db):
    await consume_stamina(db, 101, 20, now=1000)
    assert (await restore_stamina(db, 101, 50, now=1000))["stamina"] == MAX_STAMINA


@pytest.mark.asyncio
async def test_invalid_inputs_rejected(db):
    with pytest.raises(StaminaError):
        await get_stamina(db, 0, now=1000)
    with pytest.raises(StaminaError):
        await consume_stamina(db, 101, -1, now=1000)
