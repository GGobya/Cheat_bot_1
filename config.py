import os

# Токен бота берём из переменной окружения.
# Запуск: export BOT_TOKEN="123456:ABC..." && python main.py
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DB_PATH = os.getenv("DB_PATH", "bcheat.db")

# Время по умолчанию, в которое пользователь получает ежедневный чит (час, 0-23, по серверному времени)
DEFAULT_SEND_HOUR = 9

# Сколько дней длится эксперимент
TOTAL_DAYS = 30
