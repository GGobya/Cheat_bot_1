import asyncio
import io
import logging
import random
from datetime import date, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile

import db
from config import BOT_TOKEN, TOTAL_DAYS, ADMIN_ID
from cheats import get_cheat
import messages as msg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bcheat")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ───────── вспомогательные функции ─────────

def is_admin(user_id: int) -> bool:
    return ADMIN_ID and user_id == ADMIN_ID


def uname(from_user) -> str:
    return from_user.username or ""


def fname(from_user) -> str:
    return from_user.first_name or ""


async def log_in(message: Message, mtype: str = "text"):
    await db.log_message(
        message.from_user.id, uname(message.from_user), fname(message.from_user),
        "in", mtype, message.text or ""
    )


async def log_out(user_id: int, username: str, first_name: str, mtype: str, content: str):
    await db.log_message(user_id, username, first_name, "out", mtype, content)


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
    await log_out(message.from_user.id, uname(message.from_user), fname(message.from_user), "text", msg.WELCOME_TEXT)

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


# ───────── ADMIN: статистика ─────────

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = await db.get_stats()
    lines = [
        f"👥 Всего пользователей: {s['total_users']}",
        f"✅ Активных: {s['active_users']}",
        f"📤 Сообщений отправлено: {s['total_sent']}",
        f"📥 Сообщений получено: {s['total_received']}",
        f"🟢 Всего выполнений: {s['total_done']}",
        f"🔴 Всего пропусков: {s['total_failed']}",
        "",
        "По пользователям:",
    ]
    for u in s["per_user"]:
        name = f"@{u['username']}" if u["username"] else (u["first_name"] or str(u["user_id"]))
        active_mark = "✅" if u["active"] else "⏸"
        lines.append(
            f"{active_mark} {name} — день {u['current_day']}, "
            f"сделал {u['total_done']}, пропустил {u['total_failed']}, "
            f"серия {u['streak']}, сообщений {u['msg_in']}"
        )
    await message.answer("\n".join(lines))


@dp.message(Command("export"))
async def cmd_export(message: Message):
    """Выгружает CSV со всеми пользователями — открывается в Excel."""
    if not is_admin(message.from_user.id):
        return
    csv_bytes = await db.export_csv()
    filename = f"bcheat_users_{date.today().isoformat()}.csv"
    await message.answer_document(
        BufferedInputFile(csv_bytes, filename=filename),
        caption="Таблица пользователей. Открывай в Excel — кодировка UTF-8 BOM."
    )


# ───────── ADMIN: рассылка ─────────

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """
    /broadcast Текст сообщения

    Отправляет текст всем активным пользователям.
    Поддерживает многострочный текст.
    """
    if not is_admin(message.from_user.id):
        return

    # Убираем команду из текста
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Формат: /broadcast Текст сообщения")
        return

    users = await db.get_active_users()
    sent, failed = 0, 0
    for u in users:
        try:
            await bot.send_message(u["user_id"], text)
            await log_out(u["user_id"], u.get("username", ""), u.get("first_name", ""), "broadcast", text)
            sent += 1
            await asyncio.sleep(0.05)  # небольшая задержка, чтобы не словить flood limit
        except Exception as e:
            logger.warning(f"Broadcast: не удалось отправить {u['user_id']}: {e}")
            failed += 1

    await message.answer(f"Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")


@dp.message(Command("send"))
async def cmd_send(message: Message):
    """
    /send @username Текст сообщения
    /send 123456789 Текст сообщения

    Отправляет сообщение конкретному пользователю по @username или user_id.
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(None, 2)  # ["/send", "идентификатор", "текст"]
    if len(parts) < 3:
        await message.answer("Формат: /send @username Текст\nили /send 123456789 Текст")
        return

    identifier, text = parts[1], parts[2].strip()
    if not text:
        await message.answer("Текст сообщения не может быть пустым.")
        return

    # Ищем пользователя
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
        await log_out(target["user_id"], target.get("username", ""), target.get("first_name", ""), "text", text)
        name = f"@{target['username']}" if target.get("username") else str(target["user_id"])
        await message.answer(f"Отправлено → {name}")
    except Exception as e:
        await message.answer(f"Ошибка при отправке: {e}")


@dp.message(Command("users"))
async def cmd_users(message: Message):
    """Быстрый список всех пользователей с user_id и username."""
    if not is_admin(message.from_user.id):
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("База пользователей пуста.")
        return
    lines = []
    for u in users:
        name = f"@{u['username']}" if u.get("username") else (u.get("first_name") or "—")
        status = "✅" if u["active"] else "⏸"
        lines.append(f"{status} {name} | id: {u['user_id']} | день {u['current_day']}")
    await message.answer("\n".join(lines))


# ───────── отправка чита ─────────

async def send_day(user_id: int, day: int):
    user = await db.get_user(user_id)
    username = user.get("username", "") if user else ""
    first_name = user.get("first_name", "") if user else ""
    cheat = get_cheat(day)
    text = msg.day_message(day)
    kb = msg.day_keyboard(day, cheat["id"])
    try:
        await bot.send_message(user_id, text, reply_markup=kb)
        await db.advance_day(user_id, day)
        await log_out(user_id, username, first_name, "cheat", f"День {day}: {cheat['title']}")
    except Exception as e:
        logger.warning(f"Не удалось отправить пользователю {user_id}: {e}")


# ───────── колбэки на кнопки ─────────

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
    simp_text = msg.simplified_message(day)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(simp_text, reply_markup=msg.simplified_keyboard(day, cheat_id))
    await log_out(callback.from_user.id, uname(callback.from_user), fname(callback.from_user), "text", simp_text)
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
            now = datetime.now()
            today_str = date.today().isoformat()
            users = await db.get_active_users()
            for user in users:
                if user["send_hour"] != now.hour:
                    continue
                if user["last_sent_date"] == today_str:
                    continue
                if user["current_day"] == 0:
                    continue
                next_day = user["current_day"] + 1
                if next_day > TOTAL_DAYS:
                    next_day = ((next_day - 1) % TOTAL_DAYS) + 1
                await send_day(user["user_id"], next_day)
        except Exception as e:
            logger.exception(f"Ошибка в scheduler_loop: {e}")
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
