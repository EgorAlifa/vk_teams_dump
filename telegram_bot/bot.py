# bot.py
# Aiogram v3 bot for VK Teams export via BOS (fetchEvents)

import asyncio
import os
import zipfile
import tempfile
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import config
from vkteams_client import VKTeamsAuth, VKTeamsClient, VKTeamsSession
from export_formatter import format_as_html

router = Router()


# -------- FSM --------

class AuthStates(StatesGroup):
    waiting_email = State()
    waiting_code = State()
    choosing_chats = State()


# -------- /start --------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Введи email для входа в VK Teams:")
    await state.set_state(AuthStates.waiting_email)


# -------- Email --------

@router.message(StateFilter(AuthStates.waiting_email))
async def handle_email(message: Message, state: FSMContext):
    email = message.text.strip()

    auth = VKTeamsAuth()

    try:
        await auth.send_code(email)
    except Exception as e:
        await message.answer(f"Ошибка отправки кода: {e}")
        return

    await state.update_data(email=email)
    await message.answer("Код отправлен на почту. Введи код:")
    await state.set_state(AuthStates.waiting_code)


# -------- Code --------

@router.message(StateFilter(AuthStates.waiting_code))
async def handle_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    email = data.get("email")

    auth = VKTeamsAuth()

    try:
        session: VKTeamsSession = await auth.verify_code(email, code)
    except Exception as e:
        await message.answer(f"Ошибка авторизации: {e}")
        return

    client = VKTeamsClient(session)

    try:
        buddylist = await client.get_buddylist()
    except Exception as e:
        await message.answer(f"Не удалось получить список чатов: {e}")
        return

    chats = []
    for item in buddylist:
        sn = item.get("sn")
        name = item.get("friendly") or item.get("displayId") or sn
        chats.append({"sn": sn, "name": name})

    if not chats:
        await message.answer("Чаты не найдены.")
        return

    text = "Выбери чаты для экспорта (номера через запятую):\n\n"
    for i, c in enumerate(chats, 1):
        text += f"{i}. {c['name']}\n"

    await state.update_data(session=session, chats=chats)
    await message.answer(text)
    await state.set_state(AuthStates.choosing_chats)


# -------- Choose chats --------

@router.message(StateFilter(AuthStates.choosing_chats))
async def handle_choose_chats(message: Message, state: FSMContext):
    data = await state.get_data()
    session: VKTeamsSession = data.get("session")
    chats = data.get("chats", [])

    try:
        nums = [int(x.strip()) for x in message.text.split(",")]
    except Exception:
        await message.answer("Неверный формат. Пример: 1,3,5")
        return

    selected = []
    for n in nums:
        if 1 <= n <= len(chats):
            selected.append(chats[n - 1])

    if not selected:
        await message.answer("Не выбрано ни одного чата.")
        return

    await message.answer("Начинаю экспорт, это может занять некоторое время...")

    client = VKTeamsClient(session)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_entries = []

        for idx, chat in enumerate(selected, 1):
            sn = chat["sn"]
            name = chat["name"]

            await message.answer(f"Экспорт: {name}")

            messages = await client.collect_history(sn, max_events=5000, timeout=25)

            chat_dir = os.path.join(tmpdir, f"chat_{idx}")
            os.makedirs(chat_dir, exist_ok=True)

            html = format_as_html(messages, {"name": name, "sn": sn})

            html_path = os.path.join(chat_dir, "index.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            index_entries.append((idx, name))

        # root index
        root_index = os.path.join(tmpdir, "index.html")
        with open(root_index, "w", encoding="utf-8") as f:
            f.write("<html><body><h1>Экспорт VK Teams</h1><ul>")
            for idx, name in index_entries:
                f.write(f'<li><a href="chat_{idx}/index.html">{name}</a></li>')
            f.write("</ul></body></html>")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = os.path.join(tmpdir, f"vk_teams_export_{ts}.zip")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    if file.endswith(".zip"):
                        continue
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, tmpdir)
                    zipf.write(full, arc)

        await message.answer_document(
            document=open(zip_path, "rb"),
            caption="Готово ✅"
        )

    await state.clear()


# -------- Main --------

async def main():
    bot = Bot(token=config.TG_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
