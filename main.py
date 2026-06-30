import asyncio
import logging
from datetime import date, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

import db
from config import BOT_TOKEN, TOTAL_DAYS
from cheats import get_cheat
import messages as msg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bcheat")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------- команды ----------

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = await db.get_user(message.from_user.id)
    if user is None:
        await db.create_user(message.from_user.id, message.from_user.username or "")
    else:
        await db.set_active(message.from_user.id, True)

    await message.answer(msg.WELCOME_TEXT)

    # сразу выдаём день 1, если пользователь ещё не начинал
    user = await db.get_user(message.from_user.id)
    if user["current_day"] == 0:
        await send_day(message.from_user.id, 1)


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    await db.set_active(message.from_user.id, False)
    await message.answer("Окей, эксперимент на паузе. Напиши /start, когда захочешь вернуться.")


@dp.message(Command("settime"))
async def cmd_settime(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit() or not (0 <= int(parts[1]) <= 23):
        await message.answer("Формат: /settime 9  (час от 0 до 23, по серверному времени)")
        return
    hour = int(parts[1])
    await db.set_send_hour(message.from_user.id, hour)
    await message.answer(f"Готово. Теперь чит будет приходить около {hour}:00.")


@dp.message(Command("testday"))
async def cmd_testday(message: Message):
    """Тестовая команда: шлёт следующий чит сразу, не дожидаясь 9:00."""
    user = await db.get_user(message.from_user.id)
    if not user:
        await db.create_user(message.from_user.id, message.from_user.username or "")
        user = await db.get_user(message.from_user.id)

    next_day = user["current_day"] + 1
    if next_day > TOTAL_DAYS:
        next_day = ((next_day - 1) % TOTAL_DAYS) + 1
    await send_day(message.from_user.id, next_day)


@dp.message(Command("status"))
async def cmd_status(message: Message):
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


# ---------- отправка дня ----------

async def send_day(user_id: int, day: int):
    cheat = get_cheat(day)
    text = msg.day_message(day)
    kb = msg.day_keyboard(day, cheat["id"])
    try:
        await bot.send_message(user_id, text, reply_markup=kb)
        await db.advance_day(user_id, day)
    except Exception as e:
        logger.warning(f"Не удалось отправить пользователю {user_id}: {e}")


# ---------- колбэки на кнопки ----------

@dp.callback_query(F.data.startswith("done:"))
async def on_done(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "done")
    import random
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(random.choice(msg.DONE_REPLIES))
    await callback.answer()


@dp.callback_query(F.data.startswith("failed:"))
async def on_failed(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "failed")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        msg.simplified_message(day),
        reply_markup=msg.simplified_keyboard(day, cheat_id),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("simpdone:"))
async def on_simplified_done(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "done")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.FAIL_REPLIES_AFTER_SIMPLIFIED_DONE)
    await callback.answer()


@dp.callback_query(F.data.startswith("simpfail:"))
async def on_simplified_fail(callback: CallbackQuery):
    _, day, cheat_id = callback.data.split(":")
    day = int(day)
    await db.record_response(callback.from_user.id, day, cheat_id, "failed")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(msg.FAIL_FINAL_REPLY)
    await callback.answer()


# ---------- планировщик ежедневной рассылки ----------

async def scheduler_loop():
    """Каждую минуту проверяет, кому пора отправить чит дня."""
    while True:
        try:
            now = datetime.now()
            today_str = date.today().isoformat()
            users = await db.get_active_users()
            for user in users:
                if user["send_hour"] != now.hour:
                    continue
                if user["last_sent_date"] == today_str:
                    continue  # уже отправляли сегодня
                if user["current_day"] == 0:
                    continue  # ещё не нажал /start по-настоящему (защита от гонки)
                next_day = user["current_day"] + 1
                if next_day > TOTAL_DAYS:
                    next_day = ((next_day - 1) % TOTAL_DAYS) + 1  # зацикливаем эксперимент
                await send_day(user["user_id"], next_day)
        except Exception as e:
            logger.exception(f"Ошибка в scheduler_loop: {e}")
        await asyncio.sleep(60)


async def main():
    await db.init_db()
    # на случай, если ранее был включён webhook — снимаем его,
    # иначе getUpdates (polling) будет конфликтовать с Telegram
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Сделай: export BOT_TOKEN='токен_от_BotFather'")
    asyncio.run(main())
