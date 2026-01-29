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
    exporting = State()


# Хранилище сессий пользователей (в продакшене использовать Redis/DB)
user_sessions: dict[int, VKTeamsSession] = {}
user_selected_chats: dict[int, list[str]] = {}


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

        # Сохраняем для выбора
        await state.update_data(contacts=contacts)

        # Разделяем на группы и личные чаты
        groups = [c for c in contacts if "@chat.agent" in c.get("sn", "")]
        private = [c for c in contacts if "@chat.agent" not in c.get("sn", "")]

        # Формируем клавиатуру (первые 50 чатов)
        builder = InlineKeyboardBuilder()

        for i, chat in enumerate(contacts[:50]):
            sn = chat.get("sn", "")
            name = chat.get("friendly") or chat.get("nick") or sn
            name = name[:30] + "..." if len(name) > 30 else name

            # Эмодзи для типа чата
            emoji = "👥" if "@chat.agent" in sn else "👤"

            builder.button(
                text=f"{emoji} {name}",
                callback_data=f"select:{sn}"
            )

        builder.adjust(1)  # По одной кнопке в ряд

        # Добавляем кнопки управления
        builder.row(
            InlineKeyboardButton(text="✅ Выбрать все группы", callback_data="select_all_groups"),
            InlineKeyboardButton(text="✅ Выбрать все", callback_data="select_all"),
        )
        builder.row(
            InlineKeyboardButton(text="📥 Экспортировать выбранные", callback_data="do_export"),
        )

        # Инициализируем выбранные чаты
        user_selected_chats[message.from_user.id] = []

        await status_msg.edit_text(
            f"💬 <b>Твои чаты</b> ({len(contacts)} шт.)\n\n"
            f"👥 Групп: {len(groups)}\n"
            f"👤 Личных: {len(private)}\n\n"
            f"Нажми на чаты для выбора, затем «Экспортировать»",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

        await state.set_state(ExportStates.selecting_chats)

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")


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
        await callback.answer(f"❌ Убран из выбора")
    else:
        selected.append(sn)
        await callback.answer(f"✅ Выбран для экспорта")


@router.callback_query(F.data == "select_all_groups")
async def select_all_groups(callback: CallbackQuery, state: FSMContext):
    """Выбрать все групповые чаты"""
    data = await state.get_data()
    contacts = data.get("contacts", [])

    groups = [c.get("sn") for c in contacts if "@chat.agent" in c.get("sn", "")]
    user_selected_chats[callback.from_user.id] = groups

    await callback.answer(f"✅ Выбрано {len(groups)} групп")


@router.callback_query(F.data == "select_all")
async def select_all_chats(callback: CallbackQuery, state: FSMContext):
    """Выбрать все чаты"""
    data = await state.get_data()
    contacts = data.get("contacts", [])

    all_sns = [c.get("sn") for c in contacts]
    user_selected_chats[callback.from_user.id] = all_sns

    await callback.answer(f"✅ Выбрано {len(all_sns)} чатов")


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

    await callback.answer()

    status_msg = await callback.message.edit_text(
        f"⏳ <b>Экспортирую {len(selected)} чатов...</b>\n\n"
        f"Это может занять несколько минут.",
        parse_mode="HTML"
    )

    client = VKTeamsClient(session)
    all_exports = []
    errors = []

    for i, sn in enumerate(selected):
        try:
            # Обновляем статус
            await status_msg.edit_text(
                f"⏳ <b>Экспорт [{i + 1}/{len(selected)}]</b>\n\n"
                f"📥 {sn}\n"
                f"Загружено чатов: {len(all_exports)}",
                parse_mode="HTML"
            )

            # Экспортируем чат
            export_data = await client.export_chat(sn)
            all_exports.append(export_data)

            # Пауза между чатами
            await asyncio.sleep(1)

        except Exception as e:
            errors.append(f"{sn}: {str(e)}")

    # Формируем итоговый экспорт
    final_export = {
        "export_date": datetime.now().isoformat(),
        "total_chats": len(all_exports),
        "chats": all_exports
    }

    # Создаём файлы
    files_to_send = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with tempfile.TemporaryDirectory() as tmpdir:
        if format_type in ("json", "both"):
            json_path = os.path.join(tmpdir, f"vkteams_export_{timestamp}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(final_export, f, ensure_ascii=False, indent=2)
            files_to_send.append(("json", json_path))

        if format_type in ("html", "both"):
            html_path = os.path.join(tmpdir, f"vkteams_export_{timestamp}.html")
            html_content = format_as_html(final_export)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            files_to_send.append(("html", html_path))

        # Отправляем файлы
        await status_msg.edit_text(
            f"✅ <b>Экспорт завершён!</b>\n\n"
            f"📊 Чатов: {len(all_exports)}\n"
            f"📨 Отправляю файлы...",
            parse_mode="HTML"
        )

        for file_type, file_path in files_to_send:
            await callback.message.answer_document(
                FSInputFile(file_path),
                caption=f"📦 VK Teams Export ({file_type.upper()})"
            )

    # Итоговое сообщение
    error_text = ""
    if errors:
        error_text = f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:5])

    await callback.message.answer(
        f"✅ <b>Готово!</b>\n\n"
        f"📊 Экспортировано чатов: {len(all_exports)}\n"
        f"📝 Всего сообщений: {sum(e['total_messages'] for e in all_exports)}"
        f"{error_text}",
        parse_mode="HTML"
    )

    # Очищаем состояние
    await state.clear()
    user_selected_chats.pop(user_id, None)


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
