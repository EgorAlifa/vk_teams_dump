"""
VK Teams Export Bot для Telegram

Бот для экспорта чатов из VK Teams.
"""

import asyncio
import json
import os
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
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from vkteams_client import VKTeamsClient, VKTeamsAuth, VKTeamsSession
from export_formatter import format_as_html, format_as_json

# Роутер для хэндлеров
router = Router()


# FSM States
class AuthStates(StatesGroup):
    waiting_auth_method = State()
    waiting_email = State()
    waiting_code = State()
    waiting_aimsid = State()


class ExportStates(StatesGroup):
    selecting_chats = State()
    searching = State()
    exporting = State()


# Хранилище сессий пользователей (в продакшене использовать Redis/DB)
user_sessions: dict[int, VKTeamsSession] = {}
user_selected_chats: dict[int, list[str]] = {}
user_exporting: dict[int, bool] = {}  # Блокировка повторных экспортов
user_search_query: dict[int, str] = {}  # Поисковый запрос


def is_birthday_chat(name: str) -> bool:
    """Проверить, является ли чат 'днём рождения' (ДР или день рождения)"""
    import re
    name_lower = name.lower()
    # Целое слово "др" (не часть слова)
    if re.search(r'\bдр\b', name_lower):
        return True
    if 'день рождения' in name_lower:
        return True
    return False


# ============== Handlers ==============

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Приветствие и инструкция"""
    text = """
👋 <b>Привет! Я помогу экспортировать чаты из VK Teams.</b>

<b>Как это работает:</b>
1. Ты даёшь мне токен сессии (aimsid) из VK Teams
2. Я показываю список твоих чатов
3. Ты выбираешь нужные
4. Я экспортирую их в удобном формате

<b>Команды:</b>
/auth — авторизоваться (ввести aimsid)
/chats — показать список чатов
/export — экспортировать выбранные чаты
/help — подробная инструкция

<b>Начни с /auth</b>
"""
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Подробная инструкция"""
    text = """
📖 <b>Инструкция по получению aimsid:</b>

1. Открой VK Teams в браузере: https://myteam.mail.ru
2. Залогинься в свой аккаунт
3. Открой DevTools (F12)
4. Перейди во вкладку <b>Network</b>
5. Обнови страницу или открой любой чат
6. Найди любой запрос к <code>rapi/</code>
7. В Headers найди <code>x-teams-aimsid</code>
8. Скопируй значение целиком

<b>Формат aimsid:</b>
<code>010.XXXXXXXXX.XXXXXXXXX:your.email@domain.com</code>

⚠️ <b>Важно:</b>
• aimsid — это твоя сессия, храни её в секрете
• Сессия истекает через некоторое время
• Бот не хранит твои данные после экспорта
"""
    await message.answer(text, parse_mode="HTML")


@router.message(Command("auth"))
async def cmd_auth(message: Message, state: FSMContext):
    """Начать авторизацию — выбор метода"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📧 Войти по Email (код на почту)", callback_data="auth:email")
    builder.button(text="🔑 Ввести aimsid вручную", callback_data="auth:manual")
    builder.adjust(1)

    text = """
🔐 <b>Авторизация в VK Teams</b>

Выбери способ входа:

<b>📧 По Email</b> — введёшь почту, получишь код
<b>🔑 Вручную</b> — скопируешь aimsid из браузера
"""
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "auth:email")
async def auth_via_email(callback: CallbackQuery, state: FSMContext):
    """Авторизация через email"""
    await callback.answer()
    await callback.message.edit_text(
        "📧 <b>Вход по Email</b>\n\n"
        "Введи свой email от VK Teams:",
        parse_mode="HTML"
    )
    await state.set_state(AuthStates.waiting_email)


@router.callback_query(F.data == "auth:manual")
async def auth_manual(callback: CallbackQuery, state: FSMContext):
    """Авторизация через ручной ввод aimsid"""
    await callback.answer()
    text = """
🔑 <b>Ручной ввод aimsid</b>

Отправь мне <code>aimsid</code> из VK Teams.

<b>Как получить:</b>
1. Открой https://myteam.mail.ru в браузере
2. F12 → Network → любой запрос к rapi/
3. Скопируй заголовок <code>x-teams-aimsid</code>

Или напиши /help для подробной инструкции.
"""
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(AuthStates.waiting_aimsid)


@router.message(AuthStates.waiting_email)
async def process_email(message: Message, state: FSMContext):
    """Обработка email — отправка кода"""
    email = message.text.strip().lower()

    # Валидация email
    if "@" not in email or "." not in email:
        await message.answer("❌ Неверный формат email. Попробуй ещё раз:")
        return

    status_msg = await message.answer(f"⏳ Отправляю код на {email}...")

    try:
        auth = VKTeamsAuth()
        result = await auth.send_code(email)

        await state.update_data(auth_email=email)
        await state.set_state(AuthStates.waiting_code)

        await status_msg.edit_text(
            f"✅ <b>Код отправлен!</b>\n\n"
            f"Проверь почту <code>{email}</code>\n"
            f"и отправь мне полученный код:",
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка отправки кода:\n<code>{str(e)}</code>\n\n"
            f"Попробуй другой email или используй ручной ввод aimsid: /auth",
            parse_mode="HTML"
        )


@router.message(AuthStates.waiting_code)
async def process_code(message: Message, state: FSMContext):
    """Обработка кода — получение aimsid"""
    code = message.text.strip()
    data = await state.get_data()
    email = data.get("auth_email")

    # Удаляем сообщение с кодом (безопасность)
    try:
        await message.delete()
    except:
        pass

    status_msg = await message.answer("⏳ Проверяю код...")

    try:
        auth = VKTeamsAuth()
        session = await auth.verify_code(email, code)

        user_sessions[message.from_user.id] = session

        # Проверяем работоспособность
        client = VKTeamsClient(session)
        contacts = await client.get_contact_list()

        await status_msg.edit_text(
            f"✅ <b>Авторизация успешна!</b>\n\n"
            f"👤 Email: <code>{session.email}</code>\n"
            f"💬 Найдено чатов: {len(contacts)}\n\n"
            f"Используй /chats чтобы увидеть список.",
            parse_mode="HTML"
        )
        await state.clear()

    except NotImplementedError as e:
        # Временное решение — просим aimsid вручную
        await status_msg.edit_text(
            f"⚠️ <b>Автоматическая авторизация пока в разработке</b>\n\n"
            f"Пожалуйста, скопируй aimsid из браузера:\n"
            f"1. Открой https://myteam.mail.ru\n"
            f"2. Войди с кодом {code}\n"
            f"3. F12 → Network → любой запрос\n"
            f"4. Скопируй <code>x-teams-aimsid</code>\n\n"
            f"И отправь его мне:",
            parse_mode="HTML"
        )
        await state.set_state(AuthStates.waiting_aimsid)

    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка авторизации:\n<code>{str(e)}</code>\n\n"
            f"Попробуй ещё раз: /auth",
            parse_mode="HTML"
        )


@router.message(AuthStates.waiting_aimsid)
async def process_aimsid(message: Message, state: FSMContext):
    """Обработка введённого aimsid"""
    aimsid = message.text.strip()

    # Базовая валидация
    if not aimsid or ":" not in aimsid:
        await message.answer(
            "❌ Неверный формат aimsid.\n"
            "Должен быть вида: <code>010.XXX.XXX:email@domain.com</code>",
            parse_mode="HTML"
        )
        return

    # Удаляем сообщение с токеном (безопасность)
    try:
        await message.delete()
    except:
        pass

    # Создаём сессию
    session = VKTeamsAuth.create_session_from_aimsid(aimsid)
    user_sessions[message.from_user.id] = session

    # Проверяем работоспособность
    status_msg = await message.answer("⏳ Проверяю подключение...")

    try:
        client = VKTeamsClient(session)
        contacts = await client.get_contact_list()

        await status_msg.edit_text(
            f"✅ <b>Авторизация успешна!</b>\n\n"
            f"👤 Email: <code>{session.email}</code>\n"
            f"💬 Найдено чатов: {len(contacts)}\n\n"
            f"Используй /chats чтобы увидеть список.",
            parse_mode="HTML"
        )
        await state.clear()

    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка подключения:\n<code>{str(e)}</code>\n\n"
            f"Проверь aimsid и попробуй снова: /auth",
            parse_mode="HTML"
        )


@router.message(Command("chats"))
async def cmd_chats(message: Message, state: FSMContext):
    """Показать список чатов для выбора"""
    session = user_sessions.get(message.from_user.id)

    if not session:
        await message.answer("❌ Сначала авторизуйся: /auth")
        return

    status_msg = await message.answer("⏳ Загружаю список чатов...")

    try:
        client = VKTeamsClient(session)
        contacts = await client.get_contact_list()

        if not contacts:
            await status_msg.edit_text("📭 У тебя нет чатов")
            return

        # Разделяем на группы и личные чаты
        groups = [c for c in contacts if "@chat.agent" in c.get("sn", "")]
        all_private = [c for c in contacts if "@chat.agent" not in c.get("sn", "")]

        # Разделяем личные на обычные и скрытые (ДР, день рождения)
        hidden = [c for c in all_private if is_birthday_chat(c.get("name", "") or c.get("sn", ""))]
        private = [c for c in all_private if not is_birthday_chat(c.get("name", "") or c.get("sn", ""))]

        # Сохраняем для выбора (сначала группы)
        await state.update_data(contacts=contacts, groups=groups, private=private, hidden=hidden)

        # Инициализируем выбранные чаты и состояние
        user_selected_chats[message.from_user.id] = []
        user_search_query[message.from_user.id] = ""
        await state.update_data(current_page=0, current_mode="groups")

        # Формируем клавиатуру с чекбоксами
        keyboard = build_chats_keyboard(groups, [], page=0, mode="groups", has_hidden=len(hidden) > 0)

        hidden_text = f"\n🎂 Скрытых (ДР): {len(hidden)}" if hidden else ""
        shown_text = f"(показано {min(50, len(groups))} из {len(groups)})" if len(groups) > 50 else ""

        await status_msg.edit_text(
            f"👥 <b>Групповые чаты</b> ({len(groups)} шт.) {shown_text}\n"
            f"👤 Личных переписок: {len(private)}{hidden_text}\n\n"
            f"Выбери чаты (⬜→☑️) и нажми «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        await state.set_state(ExportStates.selecting_chats)

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


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
        name = name[:28] + "…" if len(name) > 28 else name

        # Чекбокс
        checkbox = "☑️" if sn in selected else "⬜"
        builder.button(text=f"{checkbox} {name}", callback_data=f"select:{sn}")

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
    elif mode == "private":
        nav_row.append(InlineKeyboardButton(text="👥 Группы", callback_data="show_groups"))
        if has_hidden:
            nav_row.append(InlineKeyboardButton(text="🎂 Скрытые (ДР)", callback_data="show_hidden"))
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

    hidden_text = f"\n🎂 Скрытых (ДР): {len(hidden)}" if hidden else ""
    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""

    try:
        await callback.message.edit_text(
            f"👤 <b>Личные чаты</b> ({len(private)} шт.){hidden_text}{search_text}\n\n"
            f"Выбери чаты (⬜→☑️) и нажми «Экспорт»",
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

    hidden_text = f"\n🎂 Скрытых (ДР): {len(hidden)}" if hidden else ""
    search_text = f"\n🔍 Фильтр: «{search_query}»" if search_query else ""

    try:
        await callback.message.edit_text(
            f"👥 <b>Групповые чаты</b> ({len(groups)} шт.)\n"
            f"👤 Личных переписок: {len(private)}{hidden_text}{search_text}\n\n"
            f"Выбери чаты (⬜→☑️) и нажми «Экспорт»",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "show_hidden")
async def show_hidden_chats(callback: CallbackQuery, state: FSMContext):
    """Показать скрытые чаты (ДР, день рождения)"""
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
            f"<i>Чаты с «ДР» или «день рождения» в названии</i>{search_text}\n\n"
            f"Выбери чаты (⬜→☑️) и нажми «Экспорт»",
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
        "Введи текст для поиска:",
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
        await message.answer("❌ Введи текст для поиска")
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
        f"Выбери чаты (⬜→☑️) и нажми «Экспорт»",
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
        await callback.answer("❌ Сессия истекла, авторизуйся заново: /auth", show_alert=True)
        return

    if not selected:
        await callback.answer("❌ Сначала выбери чаты для экспорта!", show_alert=True)
        return

    # Проверяем, не идёт ли уже экспорт
    if user_exporting.get(user_id):
        await callback.answer("⏳ Экспорт уже выполняется! Дождись завершения.", show_alert=True)
        return

    await callback.answer()

    # Спрашиваем формат
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 JSON (данные)", callback_data="format:json")
    builder.button(text="🌐 HTML (для чтения)", callback_data="format:html")
    builder.button(text="📦 Оба формата", callback_data="format:both")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📥 <b>Экспорт {len(selected)} чатов</b>\n\n"
        f"Выбери формат:",
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

    # Устанавливаем блокировку
    user_exporting[user_id] = True

    status_msg = await callback.message.edit_text(
        f"⏳ <b>Экспортирую {len(selected)} чатов...</b>\n\n"
        f"Это может занять несколько минут.",
        parse_mode="HTML"
    )

    client = VKTeamsClient(session)
    all_exports = []
    errors = []
    critical_error = None

    try:
        for i, sn in enumerate(selected):
            try:
                # Обновляем статус
                try:
                    await status_msg.edit_text(
                        f"⏳ <b>Экспорт [{i + 1}/{len(selected)}]</b>\n\n"
                        f"📥 {sn}\n"
                        f"Загружено чатов: {len(all_exports)}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

                # Экспортируем чат
                export_data = await client.export_chat(sn)
                all_exports.append(export_data)

                # Пауза между чатами
                await asyncio.sleep(1)

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
            await status_msg.edit_text(
                f"{status_text}\n\n"
                f"📊 Чатов: {len(all_exports)}\n"
                f"📨 Отправляю файлы...",
                parse_mode="HTML"
            )

            for file_type, file_path in files_to_send:
                await callback.message.answer_document(
                    FSInputFile(file_path),
                    caption=f"📦 VK Teams Export ({file_type.upper()})"
                )
    except Exception as file_err:
        await callback.message.answer(f"❌ Ошибка при создании файлов: {file_err}")

    # Итоговое сообщение
    error_text = ""
    if critical_error:
        error_text = f"\n\n❌ Критическая ошибка: {critical_error}"
    if errors:
        error_text += f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:10])

    total_msgs = sum(e.get('total_messages', 0) for e in all_exports)
    await callback.message.answer(
        f"{'✅' if not critical_error else '⚠️'} <b>Готово!</b>\n\n"
        f"📊 Экспортировано чатов: {len(all_exports)} из {len(selected)}\n"
        f"📝 Всего сообщений: {total_msgs}"
        f"{error_text}",
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

async def main():
    if not config.TG_BOT_TOKEN:
        print("❌ Установи TG_BOT_TOKEN в .env файле!")
        print("   Получить токен: @BotFather в Telegram")
        return

    bot = Bot(token=config.TG_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("🚀 Бот запущен!")
    print("   Остановка: Ctrl+C")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
