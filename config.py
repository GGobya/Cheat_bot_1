import os

# Токен бота берём из переменной окружения.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DB_PATH = os.getenv("DB_PATH", "bcheat.db")

# Время по умолчанию, в которое пользователь получает ежедневный чит (час, 0-23)
DEFAULT_SEND_HOUR = 9

# Сколько дней длится эксперимент
TOTAL_DAYS = 30

# Telegram user_id администратора — только он может делать рассылку и видеть статистику.
# Узнать свой ID: написать @userinfobot в Telegram.
# Задать: export ADMIN_ID=123456789
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
