from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from cheats import get_cheat

WELCOME_TEXT = (
    "Окей. Ты внутри эксперимента.\n\n"
    "Состояние действия не запущено. Рабочая гипотеза: запуск поведения происходит "
    "не через решение, а через факт входа в процесс.\n\n"
    "Каждый день — один чит. Один эксперимент. Без теории и мотивационных речей.\n\n"
    "30 дней. Погнали."
)


def day_message(day: int) -> str:
    cheat = get_cheat(day)
    steps_block = "\n".join(f"→ {step}" for step in cheat["steps"])
    return (
        f"ЧИТ #{cheat['num']} — {cheat['title']}\n\n"
        f"{cheat['hypothesis']}\n\n"
        f"Эксперимент:\n"
        f"{steps_block}\n\n"
        f"Зафиксировать: {cheat['fixate']}.\n\n"
        f"{cheat['question']}"
    )


def day_keyboard(day: int, cheat_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"done:{day}:{cheat_id}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"failed:{day}:{cheat_id}"),
            ]
        ]
    )


def simplified_message(day: int) -> str:
    cheat = get_cheat(day)
    return (
        "Барьер оказался слишком высоким. Снижаем до минимальной версии.\n\n"
        f"→ {cheat['simplified']}"
    )


def simplified_keyboard(day: int, cheat_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сделал", callback_data=f"simpdone:{day}:{cheat_id}"),
                InlineKeyboardButton(text="Всё равно нет", callback_data=f"simpfail:{day}:{cheat_id}"),
            ]
        ]
    )


DONE_REPLIES = [
    "Зафиксировано. Вход состоялся.",
    "Ок. Состояние действия запущено.",
    "Зафиксировано. Сопротивление сегодня проиграло.",
]

FAIL_REPLIES_AFTER_SIMPLIFIED_DONE = "Зафиксировано. Минимальная версия тоже считается."

FAIL_FINAL_REPLY = (
    "Ок, зафиксировано. Завтра — другой угол захода."
)
