"""
VK Teams Export Bot для Telegram

Бот для экспорта чатов из VK Teams.
"""

import asyncio
import gc
import json
import os
import tempfile
import zipfile
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    BotCommand,
    BotCommandScopeChat,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

import config
from vkteams_client import VKTeamsClient, VKTeamsAuth, VKTeamsSession
from export_formatter import format_as_html, format_as_json

# Stats tracking (lightweight)
try:
    from stats import log_event, update_active_user, get_active_user_ids, update_user_export
    STATS_ENABLED = True
except ImportError:
    STATS_ENABLED = False
    def log_event(*args, **kwargs): pass
    def update_active_user(*args, **kwargs): pass
    def get_active_user_ids(): return []
    def update_user_export(*args, **kwargs): pass

# Роутер для хэндлеров
router = Router()


# Контакт поддержки
SUPPORT_CONTACT = "e.nikonorov@goodt.me"

# FSM States
class AuthStates(StatesGroup):
    waiting_email = State()
    waiting_code = State()


class ExportStates(StatesGroup):
    selecting_chats = State()
    searching = State()
    exporting = State()


# Хранилище сессий пользователей (в продакшене использовать Redis/DB)
user_sessions: dict[int, VKTeamsSession] = {}
user_selected_chats: dict[int, list[str]] = {}
user_exporting: dict[int, bool] = {}  # Блокировка повторных экспортов
user_search_query: dict[int, str] = {}  # Поисковый запрос
user_message_ids: dict[int, dict] = {}  # ID сообщений для удаления (code_msg, chats_msg)


def make_progress_bar(current: int, total: int, width: int = 20) -> str:
    """Создать текстовый прогресс-бар"""
    if total == 0:
        return "░" * width
    percent = current / total
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {current}/{total} ({int(percent * 100)}%)"


async def safe_edit_text(message, text: str, **kwargs):
    """Safely edit message, ignoring 'message not modified' error"""
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def safe_edit_reply_markup(message, **kwargs):
    """Safely edit reply markup, ignoring 'message not modified' error"""
    try:
        await message.edit_reply_markup(**kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int):
    """Safely delete message, ignoring errors"""
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass


async def send_document_with_retry(
    bot: Bot,
    chat_id: int,
    file_path: str,
    caption: str,
    max_retries: int = 4
) -> bool:
    """Отправить документ с retry логикой и exponential backoff"""
    last_error = None

    for attempt in range(max_retries):
        try:
            await bot.send_document(
                chat_id,
                FSInputFile(file_path),
                caption=caption,
                request_timeout=300,  # 5 минут на загрузку
            )
            return True
        except (asyncio.TimeoutError, TelegramNetworkError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)  # 2, 4, 8, 16 seconds
                print(f"📤 Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
        except Exception as e:
            # Non-retryable error
            raise

    # All retries failed
    raise last_error or Exception("Failed to send document after retries")


async def cleanup_user_messages(bot: Bot, user_id: int, chat_id: int, msg_type: str = None):
    """Удалить сохранённые сообщения пользователя"""
    msgs = user_message_ids.get(user_id, {})
    if msg_type:
        # Удаляем конкретный тип
        if msg_type in msgs:
            await safe_delete_message(bot, chat_id, msgs[msg_type])
            del msgs[msg_type]
    else:
        # Удаляем все
        for msg_id in msgs.values():
            await safe_delete_message(bot, chat_id, msg_id)
        user_message_ids[user_id] = {}


def is_hidden_chat(name: str) -> bool:
    """Проверить, является ли чат скрытым (ДР, свадьба, поздравления и т.п.)"""
    import re
    name_lower = name.lower()

    # "день рождения" или "день рождение" (с опечаткой)
    if 'день рождени' in name_lower:
        return True

    # Рождение сына/дочери
    if 'рождени' in name_lower and ('сын' in name_lower or 'дочь' in name_lower or 'дочер' in name_lower):
        return True

    # Поздравление/поздравления
    if 'поздравлен' in name_lower:
        return True

    # Свадьба, женился/женилась
    if 'свадьб' in name_lower:
        return True
    if 'женил' in name_lower:
        return True

    # Стал отцом / стала мамой
    if 'стал отцом' in name_lower or 'стала мамой' in name_lower:
        return True

    # Целое слово "др" - проверяем что перед и после нет кириллических букв
    pattern = r'(?<![а-яёa-z])др(?![а-яёa-z])'
    if re.search(pattern, name_lower):
        return True

    return False


def is_unnamed_chat(chat: dict) -> bool:
    """Проверить, является ли чат безымянным (дубль/удалённый)"""
    name = chat.get("name", "")
    friendly = chat.get("friendly", "")
    sn = chat.get("sn", "")

    # Если есть нормальное имя - не безымянный
    if name and not name.endswith("@chat.agent"):
        return False
    if friendly and not friendly.endswith("@chat.agent"):
        return False

    # Если имя это просто sn - безымянный
    return True


# ============== Handlers ==============

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие и инструкция"""
    log_event("start", message.from_user.id)
    update_active_user(message.from_user.id, message.from_user.username)

    text = f"""
📦 <b>VK Teams Export Bot</b>

Данный бот предназначен для экспорта чатов из VK Teams.

<b>Как это работает:</b>
1. Вы авторизуетесь через корпоративную почту
2. Получаете код подтверждения на email
3. Выбираете нужные чаты для экспорта
4. Получаете файл с историей переписки

<b>Команды:</b>
/auth — авторизоваться
/chats — список чатов
/logout — выход из УЗ
/help — справка

По всем вопросам и при возникновении ошибок обращайтесь: <code>{SUPPORT_CONTACT}</code>
"""
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Подробная инструкция"""
    text = f"""
📖 <b>Справка по использованию</b>

<b>Авторизация:</b>
1. Введите команду /auth
2. Укажите вашу корпоративную почту
3. Введите код, полученный на почту

<b>Экспорт чатов:</b>
1. После авторизации введите /chats
2. Выберите нужные чаты (☑️)
3. Нажмите «Экспорт»
4. Выберите формат (JSON/HTML)

<b>Форматы экспорта:</b>
• <b>HTML</b> — удобен для чтения в браузере
• <b>JSON</b> — для технической обработки данных

⚠️ <b>Важно:</b>
• Сессия действительна ограниченное время
• Данные не сохраняются на сервере после экспорта

По вопросам: <code>{SUPPORT_CONTACT}</code>
"""
    await message.answer(text, parse_mode="HTML")


@router.message(Command("auth"))
async def cmd_auth(message: Message, state: FSMContext):
    """Начать авторизацию через email"""
    session = user_sessions.get(message.from_user.id)

    if session:
        # Уже авторизован
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🚪 Выйти и войти под другой УЗ", callback_data="do_logout")
        keyboard.button(text="📋 Перейти к чатам", callback_data="go_to_chats")
        keyboard.adjust(1)

        await message.answer(
            f"✅ <b>Вы уже авторизованы</b>\n\n"
            f"👤 Email: <code>{session.email}</code>\n\n"
            f"Можете перейти к чатам или выйти для смены учётной записи.",
            parse_mode="HTML",
            reply_markup=keyboard.as_markup()
        )
        return

    text = """
🔐 <b>Авторизация в VK Teams</b>

Введите вашу корпоративную почту:
"""
    await message.answer(text, parse_mode="HTML")
    await state.set_state(AuthStates.waiting_email)


@router.message(Command("logout"))
async def cmd_logout(message: Message, state: FSMContext):
    """Выход из учётной записи"""
    session = user_sessions.get(message.from_user.id)

    if not session:
        await message.answer("ℹ️ Вы не авторизованы.\n\nДля входа используйте /auth")
        return

    email = session.email
    # Очищаем данные
    user_sessions.pop(message.from_user.id, None)
    user_selected_chats.pop(message.from_user.id, None)
    user_search_query.pop(message.from_user.id, None)
    await state.clear()

    # Удаляем старые сообщения со списком чатов
    await cleanup_user_messages(message.bot, message.from_user.id, message.chat.id)

    log_event("logout", message.from_user.id, email)

    await message.answer(
        f"🚪 <b>Вы вышли из учётной записи</b>\n\n"
        f"👤 Был: <code>{email}</code>\n\n"
        f"Для входа под другой УЗ используйте /auth",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "do_logout")
async def handle_logout(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки логаута"""
    session = user_sessions.get(callback.from_user.id)
    email = session.email if session else "?"

    # Очищаем данные
    user_sessions.pop(callback.from_user.id, None)
    user_selected_chats.pop(callback.from_user.id, None)
    user_search_query.pop(callback.from_user.id, None)
    await state.clear()

    # Удаляем старые сообщения
    await cleanup_user_messages(callback.bot, callback.from_user.id, callback.message.chat.id)

    log_event("logout", callback.from_user.id, email)

    await callback.message.edit_text(
        f"🚪 <b>Вы вышли из учётной записи</b>\n\n"
        f"👤 Был: <code>{email}</code>\n\n"
        f"Теперь введите /auth для входа под другой УЗ",
        parse_mode="HTML"
    )
    await callback.answer("Вы вышли")


@router.callback_query(F.data == "go_to_chats")
async def handle_go_to_chats(callback: CallbackQuery, state: FSMContext):
    """Перейти к чатам из меню авторизации"""
    await callback.message.delete()
    # Создаём фейковое сообщение для вызова cmd_chats
    await cmd_chats(callback.message, state)
    await callback.answer()


@router.message(AuthStates.waiting_email)
async def process_email(message: Message, state: FSMContext):
    """Обработка email — отправка кода"""
    email = message.text.strip().lower()

    # Валидация email
    if "@" not in email or "." not in email:
        await message.answer("❌ Неверный формат email. Попробуйте ещё раз:")
        return

    status_msg = await message.answer(f"⏳ Отправляем код на {email}...")

    try:
        auth = VKTeamsAuth()
        result = await auth.send_code(email)

        await state.update_data(auth_email=email)
        await state.set_state(AuthStates.waiting_code)

        await safe_edit_text(
            status_msg,
            f"✅ <b>Код отправлен!</b>\n\n"
            f"Проверьте почту <code>{email}</code>\n"
            f"и введите полученный код:",
            parse_mode="HTML"
        )

        # Сохраняем ID сообщения для удаления после авторизации
        if message.from_user.id not in user_message_ids:
            user_message_ids[message.from_user.id] = {}
        user_message_ids[message.from_user.id]["code_msg"] = status_msg.message_id

    except Exception as e:
        await safe_edit_text(
            status_msg,
            f"❌ Ошибка отправки кода:\n<code>{str(e)}</code>\n\n"
            f"Попробуйте другой email: /auth\n\n"
            f"При повторении ошибки обратитесь: <code>{SUPPORT_CONTACT}</code>",
            parse_mode="HTML"
        )


@router.message(AuthStates.waiting_code)
async def process_code(message: Message, state: FSMContext):
    """Обработка кода — получение сессии"""
    code = message.text.strip()
    data = await state.get_data()
    email = data.get("auth_email")

    # Удаляем сообщение с кодом (безопасность)
    try:
        await message.delete()
    except:
        pass

    status_msg = await message.answer("⏳ Проверяем код...")

    try:
        auth = VKTeamsAuth()
        session = await auth.verify_code(email, code)

        user_sessions[message.from_user.id] = session

        # Проверяем работоспособность
        client = VKTeamsClient(session)
        contacts = await client.get_contact_list()

        log_event("auth_success", message.from_user.id, email)
        update_active_user(message.from_user.id, message.from_user.username, email)

        await safe_edit_text(
            status_msg,
            f"✅ <b>Авторизация успешна!</b>\n\n"
            f"👤 Email: <code>{session.email}</code>\n"
            f"💬 Найдено чатов: {len(contacts)}\n\n"
            f"Введите /chats для просмотра списка.",
            parse_mode="HTML"
        )
        await state.clear()

        # Удаляем сообщение "Код отправлен!" - оно больше не нужно
        await cleanup_user_messages(message.bot, message.from_user.id, message.chat.id, "code_msg")

    except Exception as e:
        log_event("auth_error", message.from_user.id, str(e))
        await safe_edit_text(
            status_msg,
            f"❌ Ошибка авторизации:\n<code>{str(e)}</code>\n\n"
            f"Попробуйте ещё раз: /auth\n\n"
            f"При повторении ошибки обратитесь: <code>{SUPPORT_CONTACT}</code>",
            parse_mode="HTML"
        )


@router.message(Command("chats"))
async def cmd_chats(message: Message, state: FSMContext):
    """Показать список чатов для выбора"""
    session = user_sessions.get(message.from_user.id)

    if not session:
        await message.answer("❌ Сначала авторизуйтесь: /auth")
        return

    log_event("chats_view", message.from_user.id)
    update_active_user(message.from_user.id, message.from_user.username)

    # Удаляем старый список чатов, если есть
    await cleanup_user_messages(message.bot, message.from_user.id, message.chat.id, "chats_msg")

    status_msg = await message.answer("⏳ Загружаем список чатов...")

    try:
        client = VKTeamsClient(session)
        contacts = await client.get_contact_list()

        if not contacts:
            await safe_edit_text(status_msg, "📭 Чаты не найдены")
            return

        # Разделяем на группы и личные чаты (без безымянных дублей)
        all_groups = [c for c in contacts if "@chat.agent" in c.get("sn", "") and not is_unnamed_chat(c)]
        # Личные чаты - все контакты из buddylist (не только с has_messages)
        # Сортируем: сначала с перепиской, потом остальные
        all_private_unsorted = [c for c in contacts if "@chat.agent" not in c.get("sn", "") and not is_unnamed_chat(c)]
        all_private = sorted(all_private_unsorted, key=lambda c: (not c.get("has_messages", False), c.get("name", "").lower()))

        # Фильтруем скрытые (ДР, свадьба и т.п.) из обеих категорий
        hidden_groups = [c for c in all_groups if is_hidden_chat(c.get("name", "") or c.get("friendly", "") or c.get("sn", ""))]
        hidden_private = [c for c in all_private if is_hidden_chat(c.get("name", "") or c.get("friendly", "") or c.get("sn", ""))]
        hidden = hidden_groups + hidden_private

        groups = [c for c in all_groups if not is_hidden_chat(c.get("name", "") or c.get("friendly", "") or c.get("sn", ""))]
        private = [c for c in all_private if not is_hidden_chat(c.get("name", "") or c.get("friendly", "") or c.get("sn", ""))]

        # Count stats
        with_messages_count = len([c for c in private if c.get("has_messages")])
        # Считаем удалённых: is_blocked или имя = email
        deleted_count = len([c for c in private if c.get("is_blocked") or (c.get("name") == c.get("sn") and "@" in c.get("sn", "") and "@chat.agent" not in c.get("sn", ""))])

        # Сохраняем для выбора (сначала группы)
        await state.update_data(contacts=contacts, groups=groups, private=private, hidden=hidden)

        # Инициализируем выбранные чаты и состояние
        user_selected_chats[message.from_user.id] = []
        user_search_query[message.from_user.id] = ""
        await state.update_data(current_page=0, current_mode="groups")

        # Формируем клавиатуру с чекбоксами
        keyboard = build_chats_keyboard(groups, [], page=0, mode="groups", has_hidden=len(hidden) > 0)

        hidden_text = f"\n🎂 Скрытых (ДР/свадьба): {len(hidden)}" if hidden else ""
        deleted_text = f" (👤❌ удалённых: {deleted_count})" if deleted_count else ""

        await safe_edit_text(
            status_msg,
            f"👥 <b>Групповые чаты</b> ({len(groups)} шт.)\n"
            f"👤 Личных: {len(private)} (💬 с перепиской: {with_messages_count}){deleted_text}{hidden_text}\n\n"
            f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # Сохраняем ID сообщения для удаления при следующем вызове /chats
        if message.from_user.id not in user_message_ids:
            user_message_ids[message.from_user.id] = {}
        user_message_ids[message.from_user.id]["chats_msg"] = status_msg.message_id

        await state.set_state(ExportStates.selecting_chats)

    except Exception as e:
        await safe_edit_text(
            status_msg,
            f"❌ Ошибка: {e}\n\n"
            f"При повторении обратитесь: <code>{SUPPORT_CONTACT}</code>",
            parse_mode="HTML"
        )


def build_chats_keyboard(
    chats: list,
    selected: list,
    page: int = 0,
    page_size: int = 30,
    mode: str = "groups",
    has_hidden: bool = False,
    search_query: str = ""
) -> InlineKeyboardMarkup:
    """Построить клавиатуру с чекбоксами и пагинацией"""
    builder = InlineKeyboardBuilder()

    # Фильтрация по поиску
    if search_query:
        search_lower = search_query.lower()
        chats = [c for c in chats if search_lower in (c.get("name", "") or c.get("sn", "")).lower()]

    total = len(chats)
    start = page * page_size
    end = min(start + page_size, total)
    page_chats = chats[start:end]

    for chat in page_chats:
        sn = chat.get("sn", "")
        name = chat.get("name") or chat.get("friendly") or sn

        # Определяем удалённых пользователей: имя = email или есть is_blocked
        is_deleted = chat.get("is_blocked", False) or (name == sn and "@" in sn and "@chat.agent" not in sn)

        if is_deleted:
            # Показываем email с пометкой
            display_name = sn if sn else name
            display_name = display_name[:23] + "…" if len(display_name) > 23 else display_name
            display_name = f"👤❌ {display_name}"
        else:
            display_name = name[:28] + "…" if len(name) > 28 else name

        # Чекбокс
        checkbox = "☑️" if sn in selected else "⬜"
        builder.button(text=f"{checkbox} {display_name}", callback_data=f"select:{sn}")

    builder.adjust(1)

    # Пагинация
    total_pages = max(1, (total + page_size - 1) // page_size)
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{mode}:{page-1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{mode}:{page+1}"))
        builder.row(*nav_buttons)

    # Кнопки управления
    builder.row(
        InlineKeyboardButton(text="✅ Выбрать все", callback_data=f"select_all:{mode}"),
        InlineKeyboardButton(text="❌ Сбросить", callback_data="clear_selection"),
    )

    # Поиск
    search_btn_text = f"🔍 Поиск: {search_query[:15]}..." if search_query else "🔍 Поиск"
    builder.row(
        InlineKeyboardButton(text=search_btn_text, callback_data="start_search"),
        InlineKeyboardButton(text="🚫 Сброс поиска", callback_data="clear_search") if search_query else InlineKeyboardButton(text=" ", callback_data="noop"),
    )

    # Переключение между группами, личными и скрытыми
    nav_row = []
    if mode == "groups":
        nav_row.append(InlineKeyboardButton(text="👤 Личные чаты", callback_data="show_private"))
        if has_hidden:
            nav_row.append(InlineKeyboardButton(text="🎂 Скрытые", callback_data="show_hidden"))
    elif mode == "private":
        nav_row.append(InlineKeyboardButton(text="👥 Группы", callback_data="show_groups"))
        if has_hidden:
            nav_row.append(InlineKeyboardButton(text="🎂 Скрытые", callback_data="show_hidden"))
    elif mode == "hidden":
        nav_row.append(InlineKeyboardButton(text="👥 Группы", callback_data="show_groups"))
        nav_row.append(InlineKeyboardButton(text="👤 Личные", callback_data="show_private"))
    builder.row(*nav_row)

    builder.row(
        InlineKeyboardButton(text=f"📥 Экспорт ({len(selected)} шт.)", callback_data="do_export"),
    )

    return builder.as_markup()


@router.callback_query(F.data.startswith("page:"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Переключение страниц"""
    parts = callback.data.split(":")
    mode = parts[1]  # groups, private или hidden
    page = int(parts[2])

    data = await state.get_data()
    if mode == "groups":
        chats = data.get("groups", [])
    elif mode == "private":
        chats = data.get("private", [])
    else:
        chats = data.get("hidden", [])

    selected = user_selected_chats.get(callback.from_user.id, [])
    search_query = user_search_query.get(callback.from_user.id, "")
    has_hidden = len(data.get("hidden", [])) > 0

    await state.update_data(current_page=page, current_mode=mode)

    keyboard = build_chats_keyboard(chats, selected, page=page, mode=mode, has_hidden=has_hidden, search_query=search_query)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "show_private")
async def show_private_chats(callback: CallbackQuery, state: FSMContext):
    """Показать личные чаты"""
    data = await state.get_data()
    private = data.get("private", [])
    hidden = data.get("hidden", [])
    selected = user_selected_chats.get(callback.from_user.id, [])
    search_query = user_search_query.get(callback.from_user.id, "")

    await state.update_data(current_page=0, current_mode="private")

    keyboard = build_chats_keyboard(private, selected, page=0, mode="private", has_hidden=len(hidden) > 0, search_query=search_query)

    # Считаем удалённых
    deleted_count = len([c for c in private if c.get("is_blocked") or (c.get("name") == c.get("sn") and "@" in c.get("sn", "") and "@chat.agent" not in c.get("sn", ""))])

    hidden_text = f"\n🎂 Скрытых: {len(hidden)}" if hidden else ""
    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""
    deleted_text = f"\n👤❌ С удалёнными: {deleted_count}" if deleted_count else ""

    try:
        await callback.message.edit_text(
            f"👤 <b>Личные чаты</b> ({len(private)} шт.){deleted_text}{hidden_text}{search_text}\n\n"
            f"<i>👤❌ — удалённые аккаунты (историю можно выгрузить)</i>\n\n"
            f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "show_groups")
async def show_group_chats(callback: CallbackQuery, state: FSMContext):
    """Показать групповые чаты"""
    data = await state.get_data()
    groups = data.get("groups", [])
    private = data.get("private", [])
    hidden = data.get("hidden", [])
    selected = user_selected_chats.get(callback.from_user.id, [])
    search_query = user_search_query.get(callback.from_user.id, "")

    await state.update_data(current_page=0, current_mode="groups")

    keyboard = build_chats_keyboard(groups, selected, page=0, mode="groups", has_hidden=len(hidden) > 0, search_query=search_query)

    hidden_text = f"\n🎂 Скрытых: {len(hidden)}" if hidden else ""
    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""

    try:
        await callback.message.edit_text(
            f"👥 <b>Групповые чаты</b> ({len(groups)} шт.)\n"
            f"👤 Личных переписок: {len(private)}{hidden_text}{search_text}\n\n"
            f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "show_hidden")
async def show_hidden_chats(callback: CallbackQuery, state: FSMContext):
    """Показать скрытые чаты (ДР, свадьба, поздравления)"""
    data = await state.get_data()
    hidden = data.get("hidden", [])
    selected = user_selected_chats.get(callback.from_user.id, [])
    search_query = user_search_query.get(callback.from_user.id, "")

    await state.update_data(current_page=0, current_mode="hidden")

    keyboard = build_chats_keyboard(hidden, selected, page=0, mode="hidden", has_hidden=True, search_query=search_query)

    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""

    try:
        await callback.message.edit_text(
            f"🎂 <b>Скрытые чаты</b> ({len(hidden)} шт.)\n"
            f"<i>ДР, свадьбы, поздравления</i>{search_text}\n\n"
            f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    """Пустое действие для кнопки с номером страницы"""
    await callback.answer()


@router.callback_query(F.data.startswith("select:"))
async def toggle_chat_selection(callback: CallbackQuery, state: FSMContext):
    """Выбор/отмена выбора чата"""
    sn = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    if user_id not in user_selected_chats:
        user_selected_chats[user_id] = []

    selected = user_selected_chats[user_id]

    if sn in selected:
        selected.remove(sn)
    else:
        selected.append(sn)

    # Обновляем клавиатуру с новым состоянием чекбоксов
    data = await state.get_data()
    mode = data.get("current_mode", "groups")
    page = data.get("current_page", 0)
    search_query = user_search_query.get(user_id, "")
    has_hidden = len(data.get("hidden", [])) > 0

    if mode == "groups":
        chats = data.get("groups", [])
    elif mode == "private":
        chats = data.get("private", [])
    else:
        chats = data.get("hidden", [])

    keyboard = build_chats_keyboard(chats, selected, page=page, mode=mode, has_hidden=has_hidden, search_query=search_query)

    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("select_all:"))
async def select_all_current(callback: CallbackQuery, state: FSMContext):
    """Выбрать все чаты текущего типа"""
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    user_id = callback.from_user.id

    if mode == "groups":
        chats = data.get("groups", [])
    elif mode == "private":
        chats = data.get("private", [])
    else:
        chats = data.get("hidden", [])

    page = data.get("current_page", 0)
    search_query = user_search_query.get(user_id, "")
    has_hidden = len(data.get("hidden", [])) > 0

    # Фильтруем по поиску при добавлении
    if search_query:
        search_lower = search_query.lower()
        chats_to_add = [c for c in chats if search_lower in (c.get("name", "") or c.get("sn", "")).lower()]
    else:
        chats_to_add = chats

    # Добавляем к уже выбранным
    if user_id not in user_selected_chats:
        user_selected_chats[user_id] = []

    selected = user_selected_chats[user_id]
    for c in chats_to_add:
        sn = c.get("sn")
        if sn and sn not in selected:
            selected.append(sn)

    keyboard = build_chats_keyboard(chats, selected, page=page, mode=mode, has_hidden=has_hidden, search_query=search_query)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer(f"✅ Выбрано {len(selected)} чатов")


@router.callback_query(F.data == "clear_selection")
async def clear_selection(callback: CallbackQuery, state: FSMContext):
    """Сбросить выбор"""
    data = await state.get_data()
    user_id = callback.from_user.id
    mode = data.get("current_mode", "groups")
    page = data.get("current_page", 0)
    search_query = user_search_query.get(user_id, "")
    has_hidden = len(data.get("hidden", [])) > 0

    if mode == "groups":
        chats = data.get("groups", [])
    elif mode == "private":
        chats = data.get("private", [])
    else:
        chats = data.get("hidden", [])

    user_selected_chats[user_id] = []

    keyboard = build_chats_keyboard(chats, [], page=page, mode=mode, has_hidden=has_hidden, search_query=search_query)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("❌ Выбор сброшен")


@router.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск по чатам"""
    await callback.answer()
    await state.set_state(ExportStates.searching)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_search")

    await callback.message.answer(
        "🔍 <b>Поиск по чатам</b>\n\n"
        "Введите текст для поиска:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "cancel_search")
async def cancel_search(callback: CallbackQuery, state: FSMContext):
    """Отменить поиск"""
    await callback.answer()
    await state.set_state(ExportStates.selecting_chats)
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "clear_search")
async def clear_search(callback: CallbackQuery, state: FSMContext):
    """Сбросить поисковый фильтр"""
    user_id = callback.from_user.id
    user_search_query[user_id] = ""

    data = await state.get_data()
    mode = data.get("current_mode", "groups")
    selected = user_selected_chats.get(user_id, [])
    has_hidden = len(data.get("hidden", [])) > 0

    if mode == "groups":
        chats = data.get("groups", [])
    elif mode == "private":
        chats = data.get("private", [])
    else:
        chats = data.get("hidden", [])

    await state.update_data(current_page=0)

    keyboard = build_chats_keyboard(chats, selected, page=0, mode=mode, has_hidden=has_hidden, search_query="")
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
    await callback.answer("🔍 Поиск сброшен")


@router.message(ExportStates.searching)
async def process_search_query(message: Message, state: FSMContext):
    """Обработка поискового запроса"""
    user_id = message.from_user.id
    search_query = message.text.strip()

    if not search_query:
        await message.answer("❌ Введите текст для поиска")
        return

    user_search_query[user_id] = search_query
    await state.set_state(ExportStates.selecting_chats)

    data = await state.get_data()
    mode = data.get("current_mode", "groups")
    selected = user_selected_chats.get(user_id, [])
    has_hidden = len(data.get("hidden", [])) > 0

    if mode == "groups":
        chats = data.get("groups", [])
        title = "👥 Групповые чаты"
    elif mode == "private":
        chats = data.get("private", [])
        title = "👤 Личные чаты"
    else:
        chats = data.get("hidden", [])
        title = "🎂 Скрытые чаты"

    # Считаем отфильтрованные
    search_lower = search_query.lower()
    filtered_count = len([c for c in chats if search_lower in (c.get("name", "") or c.get("sn", "")).lower()])

    await state.update_data(current_page=0)

    keyboard = build_chats_keyboard(chats, selected, page=0, mode=mode, has_hidden=has_hidden, search_query=search_query)

    await message.answer(
        f"{title}\n"
        f"🔍 Найдено: {filtered_count} из {len(chats)}\n"
        f"Фильтр: «{search_query}»\n\n"
        f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "do_export")
async def do_export(callback: CallbackQuery, state: FSMContext):
    """Начать экспорт выбранных чатов"""
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    selected = user_selected_chats.get(user_id, [])

    if not session:
        await callback.answer("❌ Сессия истекла, авторизуйтесь заново: /auth", show_alert=True)
        return

    if not selected:
        await callback.answer("❌ Сначала выберите чаты для экспорта!", show_alert=True)
        return

    # Проверяем, не идёт ли уже экспорт
    if user_exporting.get(user_id):
        await callback.answer("⏳ Экспорт уже выполняется! Дождитесь завершения.", show_alert=True)
        return

    await callback.answer()

    # Спрашиваем формат
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 JSON (данные)", callback_data="format:json")
    builder.button(text="🌐 HTML (для чтения)", callback_data="format:html")
    builder.button(text="📦 Оба формата", callback_data="format:both")
    builder.adjust(1)

    await safe_edit_text(
        callback.message,
        f"📥 <b>Экспорт {len(selected)} чатов</b>\n\n"
        f"Выберите формат:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("format:"))
async def process_export(callback: CallbackQuery, state: FSMContext):
    """Выполнить экспорт в выбранном формате"""
    format_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)
    selected = user_selected_chats.get(user_id, [])

    # Проверяем блокировку ещё раз
    if user_exporting.get(user_id):
        await callback.answer("⏳ Экспорт уже выполняется!", show_alert=True)
        return

    await callback.answer()

    log_event("export_start", user_id, f"chats={len(selected)},format={format_type}")
    update_active_user(user_id, callback.from_user.username)

    # Устанавливаем блокировку
    user_exporting[user_id] = True

    total = len(selected)
    status_msg = await callback.message.edit_text(
        f"⏳ <b>Экспорт чатов</b>\n\n"
        f"{make_progress_bar(0, total)}\n\n"
        f"Подготовка...",
        parse_mode="HTML"
    )

    client = VKTeamsClient(session)
    all_exports = []
    errors = []
    no_dialogs = []  # Контакты без диалога (не ошибка)
    critical_error = None

    # Получаем данные о чатах заранее
    state_data = await state.get_data()
    all_chats = state_data.get("contacts", [])

    try:
        for i, sn in enumerate(selected):
            try:
                # Обновляем статус перед каждым чатом
                chat_info = next((c for c in all_chats if c.get("sn") == sn), {})
                chat_name = chat_info.get("name") or chat_info.get("friendly") or sn
                chat_name = chat_name[:35] + "..." if len(chat_name) > 35 else chat_name

                # Show blocked indicator
                if chat_info.get("is_blocked"):
                    chat_name = f"🚫 {chat_name}"

                await safe_edit_text(
                    status_msg,
                    f"⏳ <b>Экспорт чатов</b>\n\n"
                    f"{make_progress_bar(i + 1, total)}\n\n"
                    f"📥 {chat_name}",
                    parse_mode="HTML"
                )

                # Экспортируем чат
                export_data = await client.export_chat(sn)
                all_exports.append(export_data)

                # Небольшая пауза между чатами
                await asyncio.sleep(0.3)

            except Exception as e:
                err_str = str(e)
                if "No such dialogue" in err_str:
                    # Это не ошибка - просто нет диалога с контактом
                    no_dialogs.append(sn)
                else:
                    errors.append(f"{sn}: {err_str}")

    except Exception as e:
        critical_error = str(e)

    # Считаем общее количество сообщений
    total_msgs = sum(e.get('total_messages', 0) for e in all_exports)

    # Формируем итоговый экспорт (даже при ошибках — отдаём что собрали)
    final_export = {
        "export_date": datetime.now().isoformat(),
        "total_chats": len(all_exports),
        "chats": all_exports
    }

    # Создаём файлы и упаковываем в ZIP
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Создаём файлы внутри архива
            files_for_zip = []

            if format_type in ("json", "both"):
                json_filename = f"vkteams_export_{timestamp}.json"
                json_path = os.path.join(tmpdir, json_filename)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(final_export, f, ensure_ascii=False, indent=2)
                files_for_zip.append((json_path, json_filename))

            if format_type in ("html", "both"):
                html_filename = f"vkteams_export_{timestamp}.html"
                html_path = os.path.join(tmpdir, html_filename)

                # Создаём словарь имён из контактов
                names = {}
                for contact in all_chats:
                    sn = contact.get("sn", "")
                    name = contact.get("name") or contact.get("friendly") or ""
                    # Используем имя только если это не email/sn
                    if sn and name and name != sn and "@" not in name:
                        names[sn] = name
                print(f"👤 Loaded contact names: {len(names)} entries")

                # Скачиваем аватарки
                avatars = {}
                try:
                    await safe_edit_text(
                        status_msg,
                        f"⏳ <b>Загрузка аватарок...</b>\n\n"
                        f"📊 Чатов: {len(all_exports)}\n"
                        f"📝 Сообщений: {total_msgs}",
                        parse_mode="HTML"
                    )
                    chat_sns = [e.get("chat_sn") for e in all_exports if e.get("chat_sn")]
                    if chat_sns:
                        avatars = await client.get_avatars_batch(chat_sns, size="small")
                        print(f"📷 Downloaded {len(avatars)} avatars")
                except Exception as av_err:
                    print(f"⚠️ Avatar download error (non-critical): {av_err}")

                # Статус: генерация HTML
                await safe_edit_text(
                    status_msg,
                    f"⏳ <b>Генерация HTML...</b>\n\n"
                    f"📊 Чатов: {len(all_exports)}\n"
                    f"📝 Сообщений: {total_msgs}\n"
                    f"📷 Аватарок: {len(avatars)}\n"
                    f"👤 Контактов: {len(names)}\n\n"
                    f"Это может занять время для больших экспортов",
                    parse_mode="HTML"
                )

                try:
                    print(f"📝 Generating HTML for {len(all_exports)} chats, {total_msgs} messages...")
                    html_content = format_as_html(final_export, avatars=avatars, names=names)
                    print(f"✅ HTML generated: {len(html_content)} bytes")
                except Exception as html_err:
                    print(f"❌ HTML generation error: {html_err}")
                    errors.append(f"HTML форматирование: {html_err}")
                    html_content = f"<html><body><h1>Ошибка форматирования</h1><pre>{html_err}</pre></body></html>"

                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                files_for_zip.append((html_path, html_filename))

                # Освобождаем память
                del html_content
                gc.collect()

            # Создаём ZIP архив с максимальным сжатием
            zip_filename = f"vkteams_export_{timestamp}.zip"
            zip_path = os.path.join(tmpdir, zip_filename)

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                for file_path, arcname in files_for_zip:
                    zf.write(file_path, arcname)

            # Проверяем размер ZIP
            zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)

            # Отправляем файл
            status_text = "✅ <b>Экспорт завершён!</b>" if not critical_error else "⚠️ <b>Экспорт завершён с ошибками</b>"
            await safe_edit_text(
                status_msg,
                f"{status_text}\n\n"
                f"📊 Чатов: {len(all_exports)}\n"
                f"📦 Размер архива: {zip_size_mb:.1f} MB\n"
                f"📨 Отправляю файл...",
                parse_mode="HTML"
            )

            if zip_size_mb > 50:
                await callback.message.answer(
                    f"⚠️ Архив слишком большой ({zip_size_mb:.1f} MB).\n"
                    f"Лимит Telegram: 50 MB.\n\n"
                    f"Попробуйте экспортировать меньше чатов.",
                    parse_mode="HTML"
                )
            else:
                try:
                    # Отправка с retry логикой и exponential backoff
                    caption = (
                        f"📦 VK Teams Export ({format_type.upper()})\n"
                        f"📊 {len(all_exports)} чатов, {sum(e.get('total_messages', 0) for e in all_exports)} сообщений"
                    )
                    await send_document_with_retry(
                        callback.bot,
                        callback.message.chat.id,
                        zip_path,
                        caption,
                        max_retries=4
                    )
                except (asyncio.TimeoutError, TelegramNetworkError) as e:
                    await callback.message.answer(
                        f"⚠️ Не удалось отправить файл после 4 попыток.\n"
                        f"Ошибка: {e}\n\n"
                        f"Попробуйте экспортировать меньше чатов или повторите позже.\n"
                        f"При проблемах обратитесь: <code>{SUPPORT_CONTACT}</code>",
                        parse_mode="HTML"
                    )

    except Exception as file_err:
        await callback.message.answer(
            f"❌ Ошибка при создании файлов: {file_err}\n\n"
            f"При проблемах обратитесь: <code>{SUPPORT_CONTACT}</code>",
            parse_mode="HTML"
        )

    # Итоговое сообщение
    error_text = ""
    if critical_error:
        error_text = f"\n\n❌ Критическая ошибка: {critical_error}"
    if errors:
        error_text += f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            error_text += f"\n... и ещё {len(errors) - 5}"
    if no_dialogs:
        error_text += f"\n\nℹ️ Нет диалога ({len(no_dialogs)}): " + ", ".join(no_dialogs[:5])
        if len(no_dialogs) > 5:
            error_text += f" и ещё {len(no_dialogs) - 5}"

    support_text = ""
    if critical_error or errors:
        support_text = f"\n\nПри проблемах обратитесь: <code>{SUPPORT_CONTACT}</code>"

    log_event("export_complete", user_id, f"chats={len(all_exports)},messages={total_msgs},errors={len(errors)},no_dialogs={len(no_dialogs)}")

    # Обновляем статус экспорта пользователя для мониторинга
    update_user_export(user_id, success=not critical_error and not errors, errors=errors if errors else None)

    await callback.message.answer(
        f"{'✅' if not critical_error else '⚠️'} <b>Экспорт завершён</b>\n\n"
        f"📊 Экспортировано: {len(all_exports)} из {len(selected)} чатов\n"
        f"📝 Всего сообщений: {total_msgs}"
        f"{error_text}{support_text}",
        parse_mode="HTML"
    )

    # Снимаем блокировку и очищаем состояние
    user_exporting.pop(user_id, None)
    await state.clear()
    user_selected_chats.pop(user_id, None)
    user_search_query.pop(user_id, None)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Быстрый экспорт (переход к выбору чатов)"""
    await cmd_chats(message, FSMContext)


# ============== Admin Commands ==============

async def broadcast_message(bot: Bot, message_text: str, exclude_user_id: int = None) -> tuple[int, int]:
    """Broadcast message to all active users
    Returns: (sent_count, failed_count)
    """
    # Get all users to notify
    active_user_ids = get_active_user_ids()
    all_user_ids = set(active_user_ids) | set(user_sessions.keys())

    if exclude_user_id:
        all_user_ids.discard(exclude_user_id)

    sent = 0
    failed = 0

    for user_id in all_user_ids:
        try:
            await bot.send_message(user_id, message_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.05)  # Rate limit

    return sent, failed


@router.message(Command("maintenance"))
async def cmd_maintenance(message: Message):
    """Admin: Notify all users about technical maintenance"""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("❌ Эта команда доступна только администраторам.")
        return

    status_msg = await message.answer("⏳ Отправляю уведомления...")

    broadcast_text = (
        "⚠️ <b>Технические работы</b>\n\n"
        "Планируются технические работы.\n"
        "Бот может быть временно недоступен.\n\n"
        "Приносим извинения за неудобства.\n\n"
        f"По вопросам: <code>{SUPPORT_CONTACT}</code>"
    )

    sent, failed = await broadcast_message(message.bot, broadcast_text, exclude_user_id=message.from_user.id)

    await safe_edit_text(
        status_msg,
        f"✅ <b>Уведомление отправлено</b>\n\n"
        f"📨 Успешно: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="HTML"
    )


@router.message(Command("announce_update"))
async def cmd_announce_update(message: Message):
    """
    Admin: Notify all users about bot updates
    Usage: /announce_update [custom message]
    If custom message is provided, it will be used instead of default text
    """
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("❌ Эта команда доступна только администраторам.")
        return

    # Извлекаем пользовательский текст после команды
    custom_text = message.text.replace("/announce_update", "").strip() if message.text else ""

    if custom_text:
        # Используем пользовательский текст
        broadcast_text = (
            "🆕 <b>Обновление бота</b>\n\n"
            f"{custom_text}\n\n"
            f"Для новой выгрузки используйте /chats\n\n"
            f"По вопросам: <code>{SUPPORT_CONTACT}</code>"
        )
    else:
        # Дефолтный текст
        broadcast_text = (
            "🆕 <b>Обновление бота</b>\n\n"
            "В боте появились новые функции и улучшения!\n\n"
            "Для просмотра изменений сделайте новую выгрузку через /chats\n\n"
            f"По вопросам: <code>{SUPPORT_CONTACT}</code>"
        )

    status_msg = await message.answer("⏳ Отправляю уведомления...")

    sent, failed = await broadcast_message(message.bot, broadcast_text, exclude_user_id=message.from_user.id)

    await safe_edit_text(
        status_msg,
        f"✅ <b>Уведомление отправлено</b>\n\n"
        f"📨 Успешно: {sent}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="HTML"
    )


# ============== Main ==============

# Global bot reference for shutdown handler
_bot: Optional[Bot] = None


async def notify_users_shutdown():
    """Notify active users that bot is shutting down"""
    if not _bot:
        return

    try:
        # Get recently active users
        active_user_ids = get_active_user_ids()

        # Also notify users with active sessions
        all_user_ids = set(active_user_ids) | set(user_sessions.keys())

        if not all_user_ids:
            return

        print(f"Notifying {len(all_user_ids)} users about shutdown...")

        for user_id in all_user_ids:
            try:
                await _bot.send_message(
                    user_id,
                    "⚠️ <b>Бот временно выключается</b>\n\n"
                    "Проводятся технические работы.\n"
                    "Бот скоро снова будет доступен.\n\n"
                    f"При вопросах: <code>{SUPPORT_CONTACT}</code>",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Failed to notify user {user_id}: {e}")

            await asyncio.sleep(0.1)  # Rate limit

    except Exception as e:
        print(f"Error notifying users: {e}")


async def main():
    global _bot

    if not config.TG_BOT_TOKEN:
        print("❌ Установите TG_BOT_TOKEN в .env файле!")
        print("   Получить токен: @BotFather в Telegram")
        return

    # Создаём бота с увеличенными таймаутами для больших файлов
    bot = Bot(token=config.TG_BOT_TOKEN)
    _bot = bot
    dp = Dispatcher()
    dp.include_router(router)

    # Устанавливаем команды бота (меню)
    commands = [
        BotCommand(command="start", description="Начало работы"),
        BotCommand(command="auth", description="Авторизация"),
        BotCommand(command="chats", description="Список чатов"),
        BotCommand(command="logout", description="Выход из учётной записи"),
        BotCommand(command="help", description="Справка"),
    ]
    await bot.set_my_commands(commands)

    # Устанавливаем расширенное меню для админов
    admin_commands = commands + [
        BotCommand(command="maintenance", description="⚠️ Уведомить о тех. работах"),
        BotCommand(command="announce_update", description="🆕 Уведомить об обновлении"),
    ]
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
            print(f"✅ Админ-меню установлено для {admin_id}")
        except Exception as e:
            print(f"⚠️ Не удалось установить админ-меню для {admin_id}: {e}")

    log_event("bot_start", data="Bot started")
    print("🚀 Бот запущен!")
    print("   Остановка: Ctrl+C")

    try:
        # Простой polling - aiogram сам обрабатывает сигналы
        await dp.start_polling(bot)
    finally:
        log_event("bot_stop", data="Bot stopped")
        await bot.session.close()
        print("👋 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
