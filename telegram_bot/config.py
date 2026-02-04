import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token (получить у @BotFather)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# Admin user IDs (comma-separated Telegram user IDs)
# Example: ADMIN_IDS=123456789,987654321
_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids_str.split(",") if x.strip().isdigit()]

# VK Teams API
VKTEAMS_API_BASE = os.getenv("VKTEAMS_API_BASE", "https://u.myteam.vmailru.net/api/v139/rapi")
VKTEAMS_AUTH_BASE = os.getenv("VKTEAMS_AUTH_BASE", "https://u.myteam.vmailru.net/auth")

# Настройки экспорта
MESSAGES_PER_REQUEST = 900  # Максимум ~1000, используем 900 для надёжности
DELAY_BETWEEN_REQUESTS = 0.3  # Уменьшено с 0.5 благодаря connection pooling
MAX_FILE_SIZE_MB = 50  # Лимит Telegram для файлов

# URL для раздачи файлов экспорта (без trailing slash)
# Пример: http://89.208.231.122:8080
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8080")
