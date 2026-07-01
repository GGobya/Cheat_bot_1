import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Абсолютный путь к БД — чтобы файл всегда создавался в одном месте
# независимо от рабочей директории при запуске
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(_BASE_DIR, "bcheat.db"))

DEFAULT_SEND_HOUR = 6
TOTAL_DAYS = 30

# Твой Telegram user_id. Узнать: написать @userinfobot в Telegram.
# Задать на bothost: переменная окружения ADMIN_ID=123456789
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
