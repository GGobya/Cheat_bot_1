import aiosqlite
import csv
import io
from datetime import date, datetime, timedelta
from config import DB_PATH, DEFAULT_SEND_HOUR

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    started_at  TEXT,
    current_day INTEGER DEFAULT 0,
    last_sent_date TEXT,
    send_hour   INTEGER DEFAULT {default_hour},
    streak      INTEGER DEFAULT 0,
    total_done  INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,
    last_status TEXT,
    procrastination_type TEXT,
    active      INTEGER DEFAULT 1
);
""".format(default_hour=DEFAULT_SEND_HOUR)

CREATE_RESPONSES = """
CREATE TABLE IF NOT EXISTS responses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    day         INTEGER,
    cheat_id    TEXT,
    status      TEXT,
    responded_at TEXT
);
"""

CREATE_MESSAGE_LOG = """
CREATE TABLE IF NOT EXISTS message_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    username     TEXT,
    first_name   TEXT,
    direction    TEXT,        -- 'in' | 'out'
    message_type TEXT,        -- 'text' | 'cheat' | 'broadcast' | 'callback' | 'command'
    content      TEXT,
    created_at   TEXT         -- ISO datetime, UTC
);
"""

# Индекс для быстрых запросов по дате активности
CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_msglog_user_date
ON message_log(user_id, created_at);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_RESPONSES)
        await db.execute(CREATE_MESSAGE_LOG)
        await db.execute(CREATE_INDEX)
        # Безопасно добавляем колонки в users, если их не было в старой БД
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
            (username.lstrip("@"),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_user(user_id: int, username: str, first_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users "
            "(user_id, username, first_name, started_at, current_day) VALUES (?, ?, ?, ?, 0)",
            (user_id, username, first_name, date.today().isoformat()),
        )
        await db.execute(
            "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
            (username, first_name, user_id),
        )
        await db.commit()


async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE active = 1")
        return [dict(r) for r in await cur.fetchall()]


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY started_at DESC")
        return [dict(r) for r in await cur.fetchall()]


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
        await db.execute(
            "UPDATE users SET active = ? WHERE user_id = ?",
            (1 if active else 0, user_id)
        )
        await db.commit()


async def record_response(user_id: int, day: int, cheat_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO responses (user_id, day, cheat_id, status, responded_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, day, cheat_id, status, date.today().isoformat()),
        )
        if status == "done":
            await db.execute(
                "UPDATE users SET streak = streak + 1, total_done = total_done + 1, "
                "last_status = 'done' WHERE user_id = ?", (user_id,)
            )
        elif status == "failed":
            await db.execute(
                "UPDATE users SET streak = 0, total_failed = total_failed + 1, "
                "last_status = 'failed' WHERE user_id = ?", (user_id,)
            )
        await db.commit()


# ───────── message_log ─────────

async def log_message(user_id: int, username: str, first_name: str,
                      direction: str, message_type: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO message_log "
            "(user_id, username, first_name, direction, message_type, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (user_id, username, first_name, direction, message_type, content[:2000]),
        )
        await db.commit()


# ───────── статистика ─────────

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        def val(row): return row[0] if row else 0

        total_users  = val(await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())
        active_users = val(await (await db.execute("SELECT COUNT(*) FROM users WHERE active=1")).fetchone())
        total_sent   = val(await (await db.execute("SELECT COUNT(*) FROM message_log WHERE direction='out'")).fetchone())
        total_recv   = val(await (await db.execute("SELECT COUNT(*) FROM message_log WHERE direction='in'")).fetchone())
        total_done   = val(await (await db.execute("SELECT COALESCE(SUM(total_done),0) FROM users")).fetchone())
        total_failed = val(await (await db.execute("SELECT COALESCE(SUM(total_failed),0) FROM users")).fetchone())

        # Активность за последние 7 дней
        since = (datetime.utcnow() - timedelta(days=7)).isoformat(sep=" ")

        active_7d = val(await (await db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM message_log WHERE direction='in' AND created_at >= ?",
            (since,)
        )).fetchone())

        # По каждому пользователю: последняя активность за 7 дней
        cur = await db.execute("""
            SELECT u.user_id, u.username, u.first_name,
                   u.current_day, u.total_done, u.total_failed, u.streak, u.active,
                   COUNT(m.id) as msg_in,
                   MAX(m.created_at) as last_active
            FROM users u
            LEFT JOIN message_log m
                   ON m.user_id = u.user_id AND m.direction = 'in' AND m.created_at >= ?
            GROUP BY u.user_id
            ORDER BY u.started_at DESC
        """, (since,))
        per_user = [dict(r) for r in await cur.fetchall()]

        # Активность по дням за последние 7 дней (сколько уникальных юзеров тыкали каждый день)
        daily_rows = await (await db.execute("""
            SELECT DATE(created_at) as day, COUNT(DISTINCT user_id) as cnt
            FROM message_log
            WHERE direction='in' AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY day
        """, (since,))).fetchall()
        daily_activity = {r[0]: r[1] for r in daily_rows}

        return {
            "total_users":    total_users,
            "active_users":   active_users,
            "total_sent":     total_sent,
            "total_received": total_recv,
            "total_done":     total_done,
            "total_failed":   total_failed,
            "active_7d":      active_7d,
            "daily_activity": daily_activity,
            "per_user":       per_user,
        }


async def export_csv() -> bytes:
    stats = await get_stats()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "user_id", "username", "first_name",
        "current_day", "total_done", "total_failed",
        "streak", "active", "msg_in_7d", "last_active_7d"
    ])
    for u in stats["per_user"]:
        writer.writerow([
            u["user_id"],
            f"@{u['username']}" if u.get("username") else "",
            u.get("first_name") or "",
            u["current_day"],
            u["total_done"],
            u["total_failed"],
            u["streak"],
            "да" if u["active"] else "нет",
            u["msg_in"],
            u.get("last_active") or "—",
        ])
    return output.getvalue().encode("utf-8-sig")
