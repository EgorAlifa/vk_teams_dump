"""
VK Teams Export Bot для Telegram

Бот для экспорта чатов из VK Teams.
"""

import asyncio
import json
import os
import signal
import tempfile
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
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

import config
from vkteams_client import VKTeamsClient, VKTeamsAuth, VKTeamsSession
from export_formatter import format_as_html, format_as_json

# Stats tracking (lightweight)
try:
    from stats import log_event, update_active_user, get_active_user_ids
    STATS_ENABLED = True
except ImportError:
    STATS_ENABLED = False
    def log_event(*args, **kwargs): pass
    def update_active_user(*args, **kwargs): pass
    def get_active_user_ids(): return []

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
    text = """
🔐 <b>Авторизация в VK Teams</b>

Введите вашу корпоративную почту:
"""
    await message.answer(text, parse_mode="HTML")
    await state.set_state(AuthStates.waiting_email)


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
        deleted_text = f"\n👤❌ С удалёнными аккаунтами: {deleted_count}" if deleted_count else ""

        await safe_edit_text(
            status_msg,
            f"👥 <b>Групповые чаты</b> ({len(groups)} шт.)\n"
            f"👤 Личных: {len(private)} (💬 с перепиской: {with_messages_count}){deleted_text}{hidden_text}\n\n"
            f"<i>👤❌ — удалённые аккаунты (историю можно выгрузить)</i>\n\n"
            f"Выберите чаты (⬜→☑️) и нажмите «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

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

    hidden_text = f"\n🎂 Скрытых: {len(hidden)}" if hidden else ""
    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""

    try:
        await callback.message.edit_text(
            f"👤 <b>Личные чаты</b> ({len(private)} шт.){hidden_text}{search_text}\n\n"
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
                errors.append(f"{sn}: {str(e)}")

    except Exception as e:
        critical_error = str(e)

    # Формируем итоговый экспорт (даже при ошибках — отдаём что собрали)
    final_export = {
        "export_date": datetime.now().isoformat(),
        "total_chats": len(all_exports),
        "chats": all_exports
    }

    # Создаём файлы
    files_to_send = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            if format_type in ("json", "both"):
                json_path = os.path.join(tmpdir, f"vkteams_export_{timestamp}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(final_export, f, ensure_ascii=False, indent=2)
                files_to_send.append(("json", json_path))

            if format_type in ("html", "both"):
                html_path = os.path.join(tmpdir, f"vkteams_export_{timestamp}.html")
                try:
                    html_content = format_as_html(final_export)
                except Exception as html_err:
                    errors.append(f"HTML форматирование: {html_err}")
                    html_content = f"<html><body><h1>Ошибка форматирования</h1><pre>{html_err}</pre></body></html>"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                files_to_send.append(("html", html_path))

            # Отправляем файлы
            status_text = "✅ <b>Экспорт завершён!</b>" if not critical_error else "⚠️ <b>Экспорт завершён с ошибками</b>"
            await safe_edit_text(
                status_msg,
                f"{status_text}\n\n"
                f"📊 Чатов: {len(all_exports)}\n"
                f"📨 Отправляю файлы...",
                parse_mode="HTML"
            )

            for file_type, file_path in files_to_send:
                try:
                    # Use longer timeout for large files (5 minutes)
                    await asyncio.wait_for(
                        callback.message.answer_document(
                            FSInputFile(file_path),
                            caption=f"📦 VK Teams Export ({file_type.upper()})"
                        ),
                        timeout=300  # 5 minutes for large files
                    )
                except asyncio.TimeoutError:
                    await callback.message.answer(
                        f"⚠️ Таймаут при отправке {file_type.upper()} файла. "
                        f"Файл слишком большой.\n\n"
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

    total_msgs = sum(e.get('total_messages', 0) for e in all_exports)

    support_text = ""
    if critical_error or errors:
        support_text = f"\n\nПри проблемах обратитесь: <code>{SUPPORT_CONTACT}</code>"

    log_event("export_complete", user_id, f"chats={len(all_exports)},messages={total_msgs},errors={len(errors)}")

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

    bot = Bot(token=config.TG_BOT_TOKEN)
    _bot = bot
    dp = Dispatcher()
    dp.include_router(router)

    # Устанавливаем команды бота (меню)
    commands = [
        BotCommand(command="start", description="Начало работы"),
        BotCommand(command="auth", description="Авторизация"),
        BotCommand(command="chats", description="Список чатов"),
        BotCommand(command="help", description="Справка"),
    ]
    await bot.set_my_commands(commands)

    # Setup shutdown handler
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        print(f"\n📢 Получен сигнал {sig}, начинаем остановку...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log_event("bot_start", data="Bot started")
    print("🚀 Бот запущен!")
    print("   Остановка: Ctrl+C")

    try:
        # Start polling in background
        polling_task = asyncio.create_task(dp.start_polling(bot))

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Notify users before stopping
        await notify_users_shutdown()

        # Stop polling
        await dp.stop_polling()
        polling_task.cancel()

    except asyncio.CancelledError:
        pass
    finally:
        log_event("bot_stop", data="Bot stopped")
        await bot.session.close()
        print("👋 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
