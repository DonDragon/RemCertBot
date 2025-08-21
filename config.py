import os
from dotenv import load_dotenv

load_dotenv()

# Токен Telegram-бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    # Явно предупреждаем при пустом токене, чтобы не было тихого фейла
    raise RuntimeError("BOT_TOKEN не задан. Установите переменную окружения BOT_TOKEN.")

# ID администраторов (список int) через запятую: ADMIN_IDS=123,456
admins_raw = os.getenv("ADMIN_IDS", "").strip()
if admins_raw:
    try:
        ADMINS = [int(x) for x in admins_raw.split(",") if x.strip()]
    except ValueError:
        raise RuntimeError("ADMIN_IDS в .env должен содержать числа, разделённые запятыми.")
else:
    ADMINS = []
