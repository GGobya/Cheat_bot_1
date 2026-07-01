import asyncio
import logging
import random
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton
)

import db
from config import BOT_TOKEN, TOTAL_DAYS, ADMIN_ID
from cheats import get_cheat
import messages as msg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bcheat")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()


# ───────── утилиты ─────────

def is_admin(uid: int) -> bool:
    return bool(ADMIN_ID) and uid == ADMIN_ID

def uname(u) -> str: return u.username or ""
def fname(u) -> str: return u.first_name or ""

async def log_in(message: Message, mtype: str = "text"):
    await db.log_message(
        message.from_user.id, uname(message.from_user), fname(message.from_user),
        "in", mtype, message.text or ""
    )

async def log_out(uid: int, username: str, first_name: str, mtype: str, content: str):
    await db.log_message(uid, username, first_name, "out", mtype, content)


# ───────── admin-меню ─────────

def admin_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура со всеми командами администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",        callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="adm:users")],
        [InlineKeyboardButton(text="📥 Экспорт CSV",       callback_data="adm:export")],
        [InlineKeyboardButton(text="📡 Рассылка всем",     callback_data="adm:broadcast_prompt")],
        [InlineKeyboardButton(text="✉️ Написать юзеру",    callback_data="adm:send_prompt")],
        [InlineKeyboardButton(text="🧪 Тест: следующий день", callback_data="adm:testday")],
    ])

ADMIN_HELP = (
    "🛠 Панель администратора\n\n"
    "📊 Статистика — число юзеров, сообщений, активность за 7 дней\n"
    "👥 Список — все пользователи с @username и прогрессом\n"
    "📥 Экспорт CSV — скачать таблицу для Excel\n"
    "📡 Рассылка всем — отправить текст всем активным\n"
    "✉️ Написать юзеру — прямое сообщение одному человеку\n"
    "🧪 Тест — получить следующий чит без ожидания 9:00\n\n"
    "Или используй команды напрямую:\n"
    "/stats · /users · /export\n"
    "/broadcast Текст\n"
    "/send @username Текст"
)


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_HELP, reply_markup=admin_keyboard())


# ───────── callback: admin-меню ─────────

@dp.callback_query(F.data == "adm:stats")
async def adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    await send_stats(callback.message)

@dp.callback_query(F.data == "adm:users")
async def adm_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    await send_users(callback.message)

@dp.callback_query(F.data == "adm:export")
async def adm_export(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer("Готовлю CSV...")
    await send_export(callback.message)

@dp.callback_query(F.data == "adm:broadcast_prompt")
async def adm_broadcast_prompt(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    await callback.message.answer(
        "Напиши команду:\n/broadcast Текст рассылки\n\n"
        "Отправится всем активным пользователям."
    )

@dp.callback_query(F.data == "adm:send_prompt")
async def adm_send_prompt(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer()
    await callback.message.answer(
        "Напиши команду:\n/send @username Текст\nили\n/send 123456789 Текст"
    )

@dp.callback_query(F.data == "adm:testday")
async def adm_testday(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.answer("Отправляю следующий день...")
    user = await db.get_user(callback.from_user.id)
    if not user:
        await db.create_user(callback.from_user.id, uname(callback.from_user), fname(callback.from_user))
        user = await db.get_user(callback.from_user.id)
    next_day = user["current_day"] + 1
    if next_day > TOTAL_DAYS:
        next_day = ((next_day - 1) % TOTAL_DAYS) + 1
    await send_day(callback.from_user.id, next_day)


# ───────── внутренние функции статистики ─────────

async def send_stats(target: Message):
    s = await db.get_stats()

    # Строка с активностью по дням за 7 дней
    daily = s["daily_activity"]
    today = date.today()
    day_lines = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        cnt = daily.get(d, 0)
        bar = "▓" * cnt + "░" * max(0, 5 - cnt) if cnt <= 5 else "▓▓▓▓▓+"
        label = "сег" if i == 0 else d[5:]  # MM-DD
        day_lines.append(f"  {label}: {cnt} чел  {bar}")

    per_user_lines = []
    for u in s["per_user"]:
        name = f"@{u['username']}" if u.get("username") else (u.get("first_name") or str(u["user_id"]))
        active_mark = "✅" if u["active"] else "⏸"
        touched = "🟢" if u["msg_in"] else "⚫"
        per_user_lines.append(
            f"{active_mark}{touched} {name} — д.{u['current_day']} "
            f"✓{u['total_done']} ✗{u['total_failed']} 🔥{u['streak']}"
        )

    text = (
        f"📊 Статистика\n\n"
        f"👥 Всего пользователей: {s['total_users']}\n"
        f"✅ Активных (не остановили бот): {s['active_users']}\n"
        f"🟢 Хоть раз тыкали за 7 дней: {s['active_7d']}\n"
        f"📤 Сообщений отправлено ботом: {s['total_sent']}\n"
        f"📥 Сообщений получено от юзеров: {s['total_received']}\n"
        f"✓ Всего выполнений читов: {s['total_done']}\n"
        f"✗ Всего пропусков: {s['total_failed']}\n\n"
        f"📅 Активность по дням (уник. юзеров):\n"
        + "\n".join(day_lines) +
        f"\n\n👤 По пользователям (за 7 дней):\n"
        f"✅=активен ⏸=стоп 🟢=тыкал ⚫=не тыкал\n"
        + "\n".join(per_user_lines)
    )
    await target.answer(text)


async def send_users(target: Message):
    users = await db.get_all_users()
    if not users:
        await target.answer("База пользователей пуста.")
        return
    lines = []
    for u in users:
        name = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "—")
        status = "✅" if u["active"] else "⏸"
        lines.append(f"{status} {name} | id: {u['user_id']} | день {u['current_day']}")
    await target.answer("\n".join(lines))


async def send_export(target: Message):
    csv_bytes = await db.export_csv()
    filename = f"bcheat_users_{date.today().isoformat()}.csv"
    await target.answer_document(
        BufferedInputFile(csv_bytes, filename=filename),
        caption="Таблица пользователей. Открывай в Excel — кодировка UTF-8 BOM."
    )


# ───────── пользовательские команды ─────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await log_in(message, "command")
    user = await db.get_user(message.from_user.id)
    if user is None:
        await db.create_user(message.from_user.id, uname(message.from_user), fname(message.from_user))
    else:
        await db.set_active(message.from_user.id, True)

    await message.answer(msg.WELCOME_TEXT)
    await log_out(message.from_user.id, uname(message.from_user), fname(message.from_user),
                  "text", msg.WELCOME_TEXT)

    user = await db.get_user(message.from_user.id)
    if user["current_day"] == 0:
        await send_day(message.from_user.id, 1)


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    await log_in(message, "command")
    await db.set_active(message.from_user.id, False)
    reply = "Окей, эксперимент на паузе. Напиши /start, когда захочешь вернуться."
    await message.answer(reply)
    await log_out(message.from_user.id, uname(message.from_user), fname(message.from_user), "text", reply)


@dp.message(Command("settime"))
async def cmd_settime(message: Message):
    await log_in(message, "command")
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit() or not (0 <= int(parts[1]) <= 23):
        await message.answer("Формат: /settime 9  (час от 0 до 23, по серверному времени)")
        return
    hour = int(parts[1])
    await db.set_send_hour(message.from_user.id, hour)
    await message.answer(f"Готово. Теперь чит будет приходить около {hour}:00.")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    await log_in(message, "command")
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Ты ещё не начал. Напиши /start.")
        return
    await message.answer(
        f"День: {user['current_day']}\n"
        f"Выполнено: {user['total_done']}\n"
        f"Пропущено: {user['total_failed']}\n"
        f"Серия подряд: {user['streak']}"
    )


@dp.message(Command("testday"))
async def cmd_testday(message: Message):
    await log_in(message, "command")
    user = await db.get_user(message.from_user.id)
    if not user:
        await db.create_user(message.from_user.id, uname(message.from_user), fname(message.from_user))
        user = await db.get_user(message.from_user.id)
    next_day = user["current_day"] + 1
    if next_day > TOTAL_DAYS:
        next_day = ((next_day - 1) % TOTAL_DAYS) + 1
    await send_day(message.from_user.id, next_day)


# ───────── ADMIN: команды текстом ─────────

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id): return
    await send_stats(message)


@dp.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id): return
    await send_users(message)


@dp.message(Command("export"))
async def cmd_export(message: Message):
    if not is_admin(message.from_user.id): return
    await send_export(message)


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id): return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Формат: /broadcast Текст сообщения")
        return
    users = await db.get_active_users()
    sent, failed = 0, 0
    for u in users:
        try:
            await bot.send_message(u["user_id"], text)
            await log_out(u["user_id"], u.get("username",""), u.get("first_name",""), "broadcast", text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Broadcast fail {u['user_id']}: {e}")
            failed += 1
    await message.answer(f"Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")


@dp.message(Command("send"))
async def cmd_send(message: Message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split(None, 2)
    if len(parts) < 3:
        await message.answer("Формат: /send @username Текст\nили /send 123456789 Текст")
        return
    identifier, text = parts[1], parts[2].strip()
    target = None
    if identifier.startswith("@") or not identifier.isdigit():
        target = await db.get_user_by_username(identifier)
    else:
        target = await db.get_user(int(identifier))
    if not target:
        await message.answer(f"Пользователь {identifier} не найден в базе.")
        return
    try:
        await bot.send_message(target["user_id"], text)
        await log_out(target["user_id"], target.get("username",""), target.get("first_name",""), "text", text)
        name = f"@{target['username']}" if target.get("username") else str(target["user_id"])
        await message.answer(f"Отправлено → {name}")
    except Exception as e:
        await message.answer(f"Ошибка при отправке: {e}")


# ───────── отправка чита ─────────

async def send_day(user_id: int, day: int):
    user = await db.get_user(user_id)
    username   = user.get("username","")   if user else ""
    first_name = user.get("first_name","") if user else ""
    cheat = get_cheat(day)
    text  = msg.day_message(day)
    kb    = msg.day_keyboard(day, cheat["id"])
    try:
        await bot.send_message(user_id, text, reply_markup=kb)
        await db.advance_day(user_id, day)
        await log_out(user_id, username, first_name, "cheat", f"День {day}: {cheat['title']}")
    except Exception as e:
        logger.warning(f"send_day fail {user_id}: {e}")


# ───────── колбэки кнопок ─────────

@dp.callback_query(F.data.startswith("done:"))
async def on_done(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "done")
    await db.log_message(callback.from_user.id, uname(callback.from_user), fname(callback.from_user),
                         "in", "callback", f"done день {day}")
    reply = random.choice(msg.DONE_REPLIES)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(reply)
    await log_out(callback.from_user.id, uname(callback.from_user), fname(callback.from_user), "text", reply)
    await callback.answer()


@dp.callback_query(F.data.startswith("failed:"))
async def on_failed(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "failed")
    await db.log_message(callback.from_user.id, uname(callback.from_user), fname(callback.from_user),
                         "in", "callback", f"failed день {day}")
    simp = msg.simplified_message(day)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(simp, reply_markup=msg.simplified_keyboard(day, cheat_id))
    await log_out(callback.from_user.id, uname(callback.from_user), fname(callback.from_user), "text", simp)
    await callback.answer()


@dp.callback_query(F.data.startswith("simpdone:"))
async def on_simplified_done(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "done")
    await db.log_message(callback.from_user.id, uname(callback.from_user), fname(callback.from_user),
                         "in", "callback", f"simpdone день {day}")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.FAIL_REPLIES_AFTER_SIMPLIFIED_DONE)
    await callback.answer()


@dp.callback_query(F.data.startswith("simpfail:"))
async def on_simplified_fail(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "failed")
    await db.log_message(callback.from_user.id, uname(callback.from_user), fname(callback.from_user),
                         "in", "callback", f"simpfail день {day}")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.FAIL_FINAL_REPLY)
    await callback.answer()


# ───────── планировщик ─────────

async def scheduler_loop():
    while True:
        try:
            now      = datetime.now()
            today    = date.today().isoformat()
            users    = await db.get_active_users()
            for user in users:
                if user["send_hour"] != now.hour:     continue
                if user["last_sent_date"] == today:   continue
                if user["current_day"] == 0:          continue
                next_day = user["current_day"] + 1
                if next_day > TOTAL_DAYS:
                    next_day = ((next_day - 1) % TOTAL_DAYS) + 1
                await send_day(user["user_id"], next_day)
        except Exception as e:
            logger.exception(f"scheduler_loop error: {e}")
        await asyncio.sleep(60)


async def main():
    await db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Сделай: export BOT_TOKEN='токен_от_BotFather'")
    asyncio.run(main())
