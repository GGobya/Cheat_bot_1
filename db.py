import aiosqlite
import csv
import io
from datetime import date
from config import DB_PATH, DEFAULT_SEND_HOUR

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    started_at TEXT,
    current_day INTEGER DEFAULT 0,
    last_sent_date TEXT,
    send_hour INTEGER DEFAULT {default_hour},
    streak INTEGER DEFAULT 0,
    total_done INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    last_status TEXT,
    procrastination_type TEXT,
    active INTEGER DEFAULT 1
);
""".format(default_hour=DEFAULT_SEND_HOUR)

CREATE_RESPONSES = """
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    day INTEGER,
    cheat_id TEXT,
    status TEXT,
    responded_at TEXT
);
"""

# Лог всех входящих и исходящих сообщений
CREATE_MESSAGE_LOG = """
CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    first_name TEXT,
    direction TEXT,      -- 'in' (от пользователя) | 'out' (от бота)
    message_type TEXT,   -- 'text' | 'cheat' | 'broadcast' | 'callback' | 'command'
    content TEXT,        -- текст сообщения или описание действия
    created_at TEXT      -- ISO datetime
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_RESPONSES)
        await db.execute(CREATE_MESSAGE_LOG)
        # Добавляем колонки, которых могло не быть в старой БД
        for col, typedef in [("first_name", "TEXT"), ("username", "TEXT")]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
            except Exception:
                pass
        await db.commit()


# ───────── users ─────────

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str):
    """Поиск пользователя по @username (без символа @)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.lstrip("@"),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user(user_id: int, username: str, first_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, started_at, current_day) VALUES (?, ?, ?, ?, 0)",
            (user_id, username, first_name, date.today().isoformat()),
        )
        # обновляем username/first_name при повторном /start
        await db.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
            (username, first_name, user_id),
        )
        await db.commit()


async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE active = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY started_at DESC")
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


# ───────── message_log ─────────

async def log_message(user_id: int, username: str, first_name: str,
                      direction: str, message_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO message_log (user_id, username, first_name, direction, message_type, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (user_id, username, first_name, direction, message_type, content[:2000]),
        )
        await db.commit()


# ───────── статистика ─────────

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        total_users = (await (await db.execute("SELECT COUNT(*) as c FROM users")).fetchone())["c"]
        active_users = (await (await db.execute("SELECT COUNT(*) as c FROM users WHERE active = 1")).fetchone())["c"]
        total_sent = (await (await db.execute("SELECT COUNT(*) as c FROM message_log WHERE direction='out'")).fetchone())["c"]
        total_received = (await (await db.execute("SELECT COUNT(*) as c FROM message_log WHERE direction='in'")).fetchone())["c"]
        total_done = (await (await db.execute("SELECT COALESCE(SUM(total_done),0) as c FROM users")).fetchone())["c"]
        total_failed = (await (await db.execute("SELECT COALESCE(SUM(total_failed),0) as c FROM users")).fetchone())["c"]

        cur = await db.execute("""
            SELECT u.username, u.first_name, u.user_id,
                   u.current_day, u.total_done, u.total_failed, u.streak, u.active,
                   COUNT(m.id) as msg_in
            FROM users u
            LEFT JOIN message_log m ON m.user_id = u.user_id AND m.direction = 'in'
            GROUP BY u.user_id
            ORDER BY u.started_at DESC
        """)
        per_user = [dict(r) for r in await cur.fetchall()]

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_sent": total_sent,
            "total_received": total_received,
            "total_done": total_done,
            "total_failed": total_failed,
            "per_user": per_user,
        }


async def export_csv() -> bytes:
    """Возвращает CSV с полной таблицей пользователей + агрегаты."""
    stats = await get_stats()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "user_id", "username", "first_name",
        "current_day", "total_done", "total_failed",
        "streak", "active", "msg_in"
    ])
    for u in stats["per_user"]:
        writer.writerow([
            u["user_id"],
            f"@{u['username']}" if u["username"] else "",
            u["first_name"] or "",
            u["current_day"],
            u["total_done"],
            u["total_failed"],
            u["streak"],
            "да" if u["active"] else "нет",
            u["msg_in"],
        ])
    return output.getvalue().encode("utf-8-sig")  # utf-8-sig — корректно открывается в Excel
