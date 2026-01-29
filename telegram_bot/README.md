# VK Teams Export Telegram Bot

Telegram бот для экспорта чатов из VK Teams.

## Возможности

- Авторизация через aimsid (токен сессии)
- Просмотр списка всех чатов
- Выбор чатов для экспорта (по одному или все сразу)
- Экспорт в JSON и/или HTML формат
- HTML с поиском по сообщениям и тёмной темой

## Быстрый старт

### 1. Создай Telegram бота

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Введи имя и username бота
4. Скопируй токен

### 2. Установи зависимости

```bash
cd telegram_bot
pip install -r requirements.txt
```

### 3. Настрой конфиг

```bash
cp .env.example .env
# Отредактируй .env и вставь свой TG_BOT_TOKEN
```

### 4. Запусти бота

```bash
python bot.py
```

## Использование

1. Открой бота в Telegram
2. Отправь `/start` для приветствия
3. Отправь `/auth` и следуй инструкции для получения aimsid
4. Отправь `/chats` для просмотра списка чатов
5. Выбери нужные чаты
6. Нажми "Экспортировать" и выбери формат

## Как получить aimsid

1. Открой [VK Teams](https://myteam.mail.ru) в браузере
2. Залогинься в аккаунт
3. Открой DevTools (F12)
4. Перейди во вкладку **Network**
5. Обнови страницу или открой любой чат
6. Найди запрос к `rapi/` (например `getHistory`)
7. В Headers найди `x-teams-aimsid`
8. Скопируй значение целиком

Формат: `010.XXXXXXXXX.XXXXXXXXX:your.email@domain.com`

## Структура проекта

```
telegram_bot/
├── bot.py              # Основной файл бота
├── config.py           # Конфигурация
├── vkteams_client.py   # Клиент VK Teams API
├── export_formatter.py # Форматирование в JSON/HTML
├── requirements.txt    # Зависимости
├── .env.example        # Пример конфига
└── README.md           # Этот файл
```

## Деплой

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t vkteams-export-bot .
docker run -d --env-file .env vkteams-export-bot
```

### Systemd (Linux)

```ini
[Unit]
Description=VK Teams Export Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/telegram_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
EnvironmentFile=/path/to/telegram_bot/.env

[Install]
WantedBy=multi-user.target
```

## Безопасность

⚠️ **Важно:**

- aimsid — это токен сессии пользователя
- Бот не хранит aimsid после завершения сессии
- Для продакшена рекомендуется использовать шифрование
- Не делитесь своим aimsid с непроверенными ботами

## TODO

- [ ] Автоматическая авторизация (отправка кода на email)
- [ ] Скачивание файлов из сообщений
- [ ] Экспорт в PDF
- [ ] Планирование регулярного экспорта
- [ ] Хранение сессий в Redis

## Лицензия

MIT
