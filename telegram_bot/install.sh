#!/bin/bash

#############################################
#  VK Teams Export Bot - Установка
#############################################

set -e  # Остановка при ошибке

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════╗"
echo "║     VK Teams Export Bot - Установка               ║"
echo "╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# Определяем директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${YELLOW}📁 Рабочая директория: $SCRIPT_DIR${NC}\n"

# Функция для проверки sudo
check_sudo() {
    if command -v sudo &> /dev/null; then
        echo "sudo"
    else
        echo ""
    fi
}

SUDO=$(check_sudo)

# Определяем пакетный менеджер
detect_package_manager() {
    if command -v apt-get &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v yum &> /dev/null; then
        echo "yum"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v brew &> /dev/null; then
        echo "brew"
    else
        echo ""
    fi
}

PKG_MANAGER=$(detect_package_manager)

# Функция установки пакета
install_package() {
    local package=$1
    echo -e "${YELLOW}📦 Устанавливаю $package...${NC}"

    case $PKG_MANAGER in
        apt)
            # Игнорируем ошибки от сторонних репозиториев (например GitLab)
            $SUDO apt-get update -qq 2>/dev/null || true
            $SUDO apt-get install -y -qq $package 2>/dev/null
            ;;
        dnf)
            $SUDO dnf install -y -q $package
            ;;
        yum)
            $SUDO yum install -y -q $package
            ;;
        pacman)
            $SUDO pacman -S --noconfirm $package
            ;;
        brew)
            brew install $package
            ;;
        *)
            echo -e "${RED}Не удалось определить пакетный менеджер${NC}"
            echo "Установи вручную: $package"
            return 1
            ;;
    esac
}

# Установка pip через get-pip.py (fallback)
install_pip_fallback() {
    echo -e "${YELLOW}📦 Устанавливаю pip через get-pip.py...${NC}"
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    python3 /tmp/get-pip.py --user --quiet
    rm -f /tmp/get-pip.py
    # Добавляем локальный pip в PATH
    export PATH="$HOME/.local/bin:$PATH"
}

# Установка Docker
install_docker() {
    echo -e "${YELLOW}🐳 Устанавливаю Docker...${NC}"

    case $PKG_MANAGER in
        apt)
            # Удаляем старые версии
            $SUDO apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

            # Устанавливаем зависимости
            $SUDO apt-get update -qq
            $SUDO apt-get install -y -qq ca-certificates curl gnupg

            # Добавляем GPG ключ Docker
            $SUDO install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null || true
            $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

            # Добавляем репозиторий
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

            # Устанавливаем Docker
            $SUDO apt-get update -qq
            $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        dnf)
            $SUDO dnf install -y dnf-plugins-core
            $SUDO dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
            $SUDO dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        yum)
            $SUDO yum install -y yum-utils
            $SUDO yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            $SUDO yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        *)
            echo -e "${RED}Автоустановка Docker не поддерживается для этой системы${NC}"
            echo "Установите Docker вручную: https://docs.docker.com/engine/install/"
            return 1
            ;;
    esac

    # Запускаем Docker
    $SUDO systemctl start docker
    $SUDO systemctl enable docker

    # Добавляем пользователя в группу docker
    $SUDO usermod -aG docker $USER

    echo -e "${GREEN}✓ Docker установлен${NC}"
    echo -e "${YELLOW}⚠ Для работы без sudo перезайдите в сессию или выполните: newgrp docker${NC}"
}

#############################################
# 1. Проверка и установка Python
#############################################
echo -e "${BLUE}[1/5] Проверяю Python...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python3 не найден, устанавливаю...${NC}"
    case $PKG_MANAGER in
        apt) install_package "python3" ;;
        dnf|yum) install_package "python3" ;;
        pacman) install_package "python" ;;
        brew) install_package "python3" ;;
    esac
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
echo -e "${GREEN}✓ Python $PYTHON_VERSION найден${NC}"

#############################################
# 2. Проверка и установка pip
#############################################
echo -e "\n${BLUE}[2/5] Проверяю pip...${NC}"

if ! python3 -m pip --version &> /dev/null; then
    echo -e "${YELLOW}pip не найден, устанавливаю...${NC}"

    # Пробуем через пакетный менеджер
    case $PKG_MANAGER in
        apt) install_package "python3-pip" ;;
        dnf|yum) install_package "python3-pip" ;;
        pacman) install_package "python-pip" ;;
        brew) python3 -m ensurepip --upgrade 2>/dev/null || true ;;
    esac

    # Если всё ещё нет pip - используем fallback
    if ! python3 -m pip --version &> /dev/null; then
        echo -e "${YELLOW}Пакетный менеджер не смог установить pip, пробую альтернативный способ...${NC}"
        install_pip_fallback
    fi
fi

# Финальная проверка pip
if python3 -m pip --version &> /dev/null; then
    echo -e "${GREEN}✓ pip установлен${NC}"
else
    echo -e "${RED}✗ Не удалось установить pip${NC}"
    echo "Попробуй установить вручную: curl https://bootstrap.pypa.io/get-pip.py | python3"
    exit 1
fi

#############################################
# 3. Проверка и установка venv
#############################################
echo -e "\n${BLUE}[3/5] Проверяю venv и создаю окружение...${NC}"

# Проверяем, работает ли venv
if ! python3 -m venv --help &> /dev/null 2>&1; then
    echo -e "${YELLOW}venv не найден, устанавливаю...${NC}"
    case $PKG_MANAGER in
        apt)
            # Определяем версию Python для правильного пакета
            install_package "python${PYTHON_MAJOR}.${PYTHON_MINOR}-venv"
            ;;
        dnf|yum)
            install_package "python3-venv"
            ;;
        pacman)
            echo "venv включён в python на Arch"
            ;;
        brew)
            echo "venv включён в python на macOS"
            ;;
    esac
fi

# Проверяем существующий venv — если сломан, удаляем
if [ -d "venv" ]; then
    if [ ! -f "venv/bin/activate" ]; then
        echo -e "${YELLOW}⚠ Виртуальное окружение повреждено, пересоздаю...${NC}"
        rm -rf venv
    fi
fi

# Создаём виртуальное окружение
if [ ! -d "venv" ]; then
    # Пробуем создать venv
    if python3 -m venv venv 2>/dev/null; then
        echo -e "${GREEN}✓ Виртуальное окружение создано${NC}"
    else
        # Fallback: создаём venv без pip (установим pip позже)
        echo -e "${YELLOW}Пробую создать venv без ensurepip...${NC}"
        python3 -m venv venv --without-pip
        echo -e "${GREEN}✓ Виртуальное окружение создано (без pip)${NC}"
    fi
else
    echo -e "${GREEN}✓ Виртуальное окружение уже существует${NC}"
fi

# Активируем venv
source venv/bin/activate

# Используем python из venv явно
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

# Если pip нет в venv - устанавливаем через get-pip.py
if ! "$VENV_PYTHON" -m pip --version &> /dev/null 2>&1; then
    echo -e "${YELLOW}Устанавливаю pip в виртуальное окружение...${NC}"
    curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Не удалось скачать get-pip.py${NC}"
        exit 1
    fi
    "$VENV_PYTHON" /tmp/get-pip.py
    rm -f /tmp/get-pip.py
fi

# Проверяем что pip работает в venv
if ! "$VENV_PYTHON" -m pip --version &> /dev/null 2>&1; then
    echo -e "${RED}✗ pip не установлен в виртуальное окружение${NC}"
    exit 1
fi
echo -e "${GREEN}✓ pip в venv работает${NC}"

#############################################
# 4. Установка зависимостей Python
#############################################
echo -e "\n${BLUE}[4/5] Устанавливаю зависимости Python...${NC}"

echo "Обновляю pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "Устанавливаю зависимости из requirements.txt..."
"$VENV_PYTHON" -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Ошибка установки зависимостей${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Зависимости установлены${NC}"

#############################################
# 5. Настройка токена
#############################################
echo -e "\n${BLUE}[5/5] Настройка токена Telegram бота...${NC}"

if [ -f ".env" ]; then
    echo -e "${YELLOW}• Файл .env уже существует${NC}"
    read -p "Перезаписать? (y/N): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        echo "Пропускаю настройку токена"
    else
        rm .env
    fi
fi

if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}Как получить токен:${NC}"
    echo "1. Открой @BotFather в Telegram"
    echo "2. Отправь /newbot"
    echo "3. Введи имя и username бота"
    echo "4. Скопируй токен"
    echo ""
    read -p "Вставь токен бота: " BOT_TOKEN

    if [ -z "$BOT_TOKEN" ]; then
        echo -e "${RED}✗ Токен не указан!${NC}"
        echo "Создай файл .env вручную:"
        echo "  echo 'TG_BOT_TOKEN=твой_токен' > .env"
        exit 1
    fi

    echo "TG_BOT_TOKEN=$BOT_TOKEN" > .env
    echo -e "${GREEN}✓ Токен сохранён в .env${NC}"
fi

#############################################
# 5.1. Настройка ресурсов машины
#############################################
echo -e "\n${BLUE}Настройка ресурсов машины...${NC}"
echo -e "${YELLOW}Укажите ресурсы ВАШЕЙ МАШИНЫ (не контейнера)${NC}"
echo ""

# Определяем ресурсы автоматически
AUTO_CPU=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "2")
AUTO_RAM=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo "4")

echo "Автоопределение: CPU=$AUTO_CPU ядер, RAM=${AUTO_RAM}GB"
echo ""

read -p "CPU ядер на машине [$AUTO_CPU]: " MACHINE_CPU
MACHINE_CPU=${MACHINE_CPU:-$AUTO_CPU}

read -p "RAM в GB на машине [$AUTO_RAM]: " MACHINE_RAM
MACHINE_RAM=${MACHINE_RAM:-$AUTO_RAM}

# Рассчитываем лимиты для контейнера (90% от машины)
# CPU: 90% от ядер
BOT_CPU=$(echo "$MACHINE_CPU * 0.9" | bc -l 2>/dev/null || echo "1.8")
BOT_CPU=$(printf "%.1f" $BOT_CPU)

# RAM: 90% от машины, в мегабайтах
BOT_RAM_GB=$(echo "$MACHINE_RAM * 0.9" | bc -l 2>/dev/null || echo "3.6")
BOT_RAM_MB=$(printf "%.0f" $(echo "$BOT_RAM_GB * 1024" | bc -l 2>/dev/null || echo "3686"))

# Минимальные значения
if [ "$BOT_RAM_MB" -lt 1024 ]; then BOT_RAM_MB=1024; fi

echo ""
echo -e "${GREEN}Лимиты для контейнера бота:${NC}"
echo -e "  CPU: ${BOT_CPU} ядер"
echo -e "  RAM: ${BOT_RAM_MB}MB"
echo ""

# Обновляем docker-compose.yml
echo -e "${YELLOW}Обновляю docker-compose.yml с лимитами...${NC}"
cat > docker-compose.yml << COMPOSE_EOF
version: '3.8'

services:
  bot:
    build: .
    container_name: vkteams_export_bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      resources:
        limits:
          cpus: '${BOT_CPU}'
          memory: ${BOT_RAM_MB}M
        reservations:
          cpus: '0.25'
          memory: 256M

  # Lightweight stats dashboard (optional)
  stats:
    build: .
    container_name: vkteams_stats
    restart: unless-stopped
    command: ["python", "stats_server.py"]
    env_file:
      - .env
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 64M
    depends_on:
      - bot
COMPOSE_EOF

echo -e "${GREEN}✓ docker-compose.yml обновлён${NC}"

#############################################
# Создание скрипта запуска
#############################################
cat > run.sh << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source venv/bin/activate
python bot.py
EOF

chmod +x run.sh

#############################################
# 6. Проверяем и устанавливаем Docker
#############################################
echo -e "\n${BLUE}[6/6] Проверяю Docker...${NC}"

# Устанавливаем Docker если нет
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker не найден, устанавливаю...${NC}"
    install_docker
fi

# Запускаем Docker если не запущен
if ! docker info &> /dev/null 2>&1; then
    echo -e "${YELLOW}Запускаю Docker...${NC}"
    $SUDO systemctl start docker 2>/dev/null || true
    sleep 2
fi

# Проверяем ещё раз
if command -v docker &> /dev/null && docker info &> /dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker работает${NC}"
    echo -e "${BLUE}Создаю контейнер...${NC}"

    # Останавливаем старый контейнер если есть
    docker compose down 2>/dev/null || true

    # Собираем и запускаем
    docker compose up -d --build

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Контейнер запущен${NC}"
        echo ""
        echo -e "${GREEN}"
        echo "╔═══════════════════════════════════════════════════╗"
        echo "║            ✅ Установка завершена!                ║"
        echo "╚═══════════════════════════════════════════════════╝"
        echo -e "${NC}"
        echo ""
        echo -e "Бот запущен в Docker контейнере!"
        echo ""
        echo -e "Команды:"
        echo -e "  ${YELLOW}docker logs -f vkteams_export_bot${NC}  — логи бота"
        echo -e "  ${YELLOW}docker compose down${NC}                — остановить"
        echo -e "  ${YELLOW}docker compose up -d${NC}               — запустить"
        echo -e "  ${YELLOW}docker compose restart${NC}             — перезапустить"
        echo ""
        echo -e "Дашборд статистики: ${YELLOW}http://localhost:8080${NC}"
        echo ""

        # Показываем логи
        read -p "Показать логи бота? (Y/n): " show_logs
        if [ "$show_logs" != "n" ] && [ "$show_logs" != "N" ]; then
            echo ""
            echo -e "${BLUE}Логи (Ctrl+C для выхода):${NC}"
            docker logs -f vkteams_export_bot
        fi
        exit 0
    else
        echo -e "${RED}✗ Ошибка запуска контейнера${NC}"
        echo "Попробуйте вручную: docker compose up -d"
    fi
else
    echo -e "${YELLOW}⚠ Docker не удалось запустить${NC}"
    echo -e "${YELLOW}Возможно нужно перезайти в сессию (для группы docker)${NC}"
    echo ""
    echo "Попробуйте:"
    echo "  1. Выйти и зайти заново (или: newgrp docker)"
    echo "  2. Запустить: docker compose up -d"
fi

#############################################
# Готово (без Docker)
#############################################
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════╗"
echo "║            ✅ Установка завершена!                ║"
echo "╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "Запуск бота:"
echo -e "  ${YELLOW}./run.sh${NC}"
echo ""
echo -e "Или вручную:"
echo -e "  ${YELLOW}source venv/bin/activate${NC}"
echo -e "  ${YELLOW}python bot.py${NC}"
echo ""
echo -e "Остановка: ${YELLOW}Ctrl+C${NC}"
echo ""

#############################################
# Спрашиваем про запуск (только без Docker)
#############################################
read -p "Запустить бота сейчас? (Y/n): " run_now

if [ "$run_now" != "n" ] && [ "$run_now" != "N" ]; then
    echo ""
    echo -e "${BLUE}🚀 Запускаю бота...${NC}"
    echo -e "${YELLOW}Остановка: Ctrl+C${NC}"
    echo ""
    python bot.py
fi
