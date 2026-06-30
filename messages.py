from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from cheats import get_cheat

WELCOME_TEXT = (
    "Окей. Ты внутри эксперимента.\n\n"
    "Каждый день — один чит. Один конкретный шаг. Без теории, без мотивационных речей.\n\n"
    "Идея простая: ты не ленивый, ты проигрываешь первые 30 секунд сопротивления. "
    "Моя задача — снижать это сопротивление до тех пор, пока старт не станет автоматическим.\n\n"
    "30 дней. По одному читу в день. Погнали."
)


def day_message(day: int) -> str:
    cheat = get_cheat(day)
    return (
        f"День {day}\n\n"
        f"🧪 Чит: {cheat['title']}\n\n"
        f"{cheat['explain']}\n\n"
        f"👉 Сделай сейчас: {cheat['action']}"
    )


def day_keyboard(day: int, cheat_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал", callback_data=f"done:{day}:{cheat_id}"),
                InlineKeyboardButton(text="❌ Не сделал", callback_data=f"failed:{day}:{cheat_id}"),
            ]
        ]
    )


def simplified_message(day: int) -> str:
    cheat = get_cheat(day)
    return (
        "Окей. Значит барьер был слишком высоким. Упростим до 10% версии.\n\n"
        f"👉 {cheat['simplified']}"
    )


def simplified_keyboard(day: int, cheat_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал упрощённую", callback_data=f"simpdone:{day}:{cheat_id}"),
                InlineKeyboardButton(text="Всё равно не вышло", callback_data=f"simpfail:{day}:{cheat_id}"),
            ]
        ]
    )


DONE_REPLIES = [
    "Ок. Это и есть главный механизм — старт важнее результата.",
    "Зафиксировано. Сопротивление сегодня проиграло.",
    "Работает. Это не мотивация, это механика.",
]

FAIL_REPLIES_AFTER_SIMPLIFIED_DONE = "Вот так и работает. Маленький шаг — но шаг."

FAIL_FINAL_REPLY = (
    "Ок, записал. Завтра попробуем другой угол захода — иногда барьер не в действии, а в моменте дня."
)
