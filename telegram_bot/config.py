import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token (получить у @BotFather)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# VK Teams API
VKTEAMS_API_BASE = os.getenv("VKTEAMS_API_BASE", "https://u.myteam.vmailru.net/api/v139/rapi")
VKTEAMS_AUTH_BASE = os.getenv("VKTEAMS_AUTH_BASE", "https://u.myteam.vmailru.net/auth")

# Настройки экспорта
MESSAGES_PER_REQUEST = 900  # Максимум ~1000, используем 900 для надёжности
DELAY_BETWEEN_REQUESTS = 0.3  # Уменьшено с 0.5 благодаря connection pooling
MAX_FILE_SIZE_MB = 50  # Лимит Telegram для файлов
