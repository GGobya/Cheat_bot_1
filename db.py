import aiosqlite
from datetime import date
from config import DB_PATH, DEFAULT_SEND_HOUR

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    started_at TEXT,
    current_day INTEGER DEFAULT 0,      -- последний ОТПРАВЛЕННЫЙ день (0 = ещё ничего не отправляли)
    last_sent_date TEXT,                -- дата последней отправки (YYYY-MM-DD)
    send_hour INTEGER DEFAULT {default_hour},
    streak INTEGER DEFAULT 0,           -- подряд выполненных дней
    total_done INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    last_status TEXT,                   -- 'done' | 'failed' | NULL — статус последнего дня
    procrastination_type TEXT,          -- телефон / усталость / избегание (для будущей персонализации)
    active INTEGER DEFAULT 1
);
""".format(default_hour=DEFAULT_SEND_HOUR)

CREATE_RESPONSES = """
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day INTEGER,
    cheat_id TEXT,
    status TEXT,           -- 'done' | 'failed' | 'simplified_offered'
    responded_at TEXT
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_RESPONSES)
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, started_at, current_day) VALUES (?, ?, ?, 0)",
            (user_id, username, date.today().isoformat()),
        )
        await db.commit()


async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE active = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def advance_day(user_id: int, new_day: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET current_day = ?, last_sent_date = ?, last_status = NULL WHERE user_id = ?",
            (new_day, date.today().isoformat(), user_id),
        )
        await db.commit()


async def set_send_hour(user_id: int, hour: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET send_hour = ? WHERE user_id = ?", (hour, user_id))
        await db.commit()


async def set_active(user_id: int, active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET active = ? WHERE user_id = ?", (1 if active else 0, user_id))
        await db.commit()


async def record_response(user_id: int, day: int, cheat_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO responses (user_id, day, cheat_id, status, responded_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, day, cheat_id, status, date.today().isoformat()),
        )
        if status == "done":
            await db.execute(
                "UPDATE users SET streak = streak + 1, total_done = total_done + 1, last_status = 'done' WHERE user_id = ?",
                (user_id,),
            )
        elif status == "failed":
            await db.execute(
                "UPDATE users SET streak = 0, total_failed = total_failed + 1, last_status = 'failed' WHERE user_id = ?",
                (user_id,),
            )
        await db.commit()


async def set_procrastination_type(user_id: int, p_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET procrastination_type = ? WHERE user_id = ?", (p_type, user_id))
        await db.commit()
