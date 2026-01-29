"""
VK Teams API Client (BOS-based)
Работает через fetchEvents как в браузере
"""

import asyncio
import aiohttp
import time
import uuid
from dataclasses import dataclass
from typing import Optional, List, Dict


# =========================
# Models
# =========================

@dataclass
class VKTeamsSession:
    aimsid: str
    email: str
    fetch_url: str


# =========================
# AUTH
# =========================

class VKTeamsAuth:
    """Авторизация через email (как в браузере)"""

    CLIENT_KEY = "ic1zmlWFTdkiTnkL"
    CLIENT_NAME = "webVKTeams"
    CLIENT_VERSION = "VKTeams Web"

    def __init__(self):
        self.api_base = "https://u.myteam.vmailru.net/api/v139/wim/auth"

    async def send_code(self, email: str):
        import urllib.parse

        params = {
            "tokenType": "otp_via_email",
            "clientName": self.CLIENT_NAME,
            "clientVersion": self.CLIENT_VERSION,
            "idType": "ICQ",
            "s": email,
            "k": self.CLIENT_KEY,
        }

        url = f"{self.api_base}/clientLogin?" + urllib.parse.urlencode(params)

        async with aiohttp.ClientSession() as http:
            async with http.get(url, data="pwd=1") as r:
                data = await r.json()

        if data.get("response", {}).get("statusCode") != 200:
            raise Exception("Не удалось отправить код подтверждения")

    async def verify_code(self, email: str, code: str) -> VKTeamsSession:
        import urllib.parse

        params = {
            "tokenType": "longTerm",
            "clientName": self.CLIENT_NAME,
            "clientVersion": self.CLIENT_VERSION,
            "idType": "ICQ",
            "s": email,
            "k": self.CLIENT_KEY,
        }

        url = f"{self.api_base}/clientLogin?" + urllib.parse.urlencode(params)

        async with aiohttp.ClientSession() as http:
            async with http.post(url, data=f"pwd={code}") as r:
                data = await r.json()

        if data.get("response", {}).get("statusCode") != 200:
            raise Exception("Неверный код подтверждения")

        token_a = data["response"]["data"]["token"]["a"]
        return await self._start_session(email, token_a)

    async def _start_session(self, email: str, token_a: str) -> VKTeamsSession:
        import urllib.parse

        ts = int(time.time())
        device_id = str(uuid.uuid4())

        params = {
            "ts": ts,
            "a": token_a,
            "userSn": email,
            "trigger": "normalLogin",
            "k": self.CLIENT_KEY,
            "view": "online",
            "clientName": self.CLIENT_NAME,
            "language": "ru-RU",
            "deviceId": device_id,
            "sessionTimeout": 2592000,
        }

        url = (
            "https://u.myteam.vmailru.net/api/v139/wim/aim/startSession?"
            + urllib.parse.urlencode(params)
        )

        async with aiohttp.ClientSession() as http:
            async with http.post(url) as r:
                data = await r.json()

        if data.get("response", {}).get("statusCode") != 200:
            raise Exception("Ошибка создания сессии")

        d = data["response"]["data"]

        return VKTeamsSession(
            aimsid=d["aimsid"],
            email=email,
            fetch_url=d["fetchBaseURL"],
        )

    @staticmethod
    def create_session_from_aimsid(aimsid: str) -> VKTeamsSession:
        # ВАЖНО: без fetch_url работать не будет
        raise Exception("Используй авторизацию через код, aimsid без BOS не поддерживается")


# =========================
# BOS CLIENT
# =========================

class VKTeamsClient:
    """Клиент через BOS fetchEvents (как web-клиент)"""

    def __init__(self, session: VKTeamsSession):
        self.session = session

    async def fetch_events(self, timeout=60000) -> dict:
        url = f"{self.session.fetch_url}&timeout={timeout}"

        async with aiohttp.ClientSession() as http:
            async with http.get(url) as r:
                return await r.json()

    # -----------------------

    async def get_contact_list(self) -> List[Dict]:
        """Список чатов из buddylist событий"""

        data = await self.fetch_events()
        chats = []

        for ev in data.get("events", []):
            if ev.get("type") == "buddylist":
                chats.extend(ev.get("contacts", []))

        return chats

    # -----------------------

    async def export_chat(self, sn: str, max_messages: int = 3000, progress_callback=None):
        """
        Экспорт сообщений чата через hist события.
        Ограничение: сервер сам решает сколько истории прислать.
        """

        messages = []
        requests = 0

        while len(messages) < max_messages:
            requests += 1

            data = await self.fetch_events(timeout=30000)

            for ev in data.get("events", []):
                if ev.get("type") == "hist" and ev.get("sn") == sn:
                    msgs = ev.get("messages", [])
                    messages.extend(msgs)

            if progress_callback:
                await progress_callback(len(messages), requests)

            if not data.get("events"):
                break

            await asyncio.sleep(1)

        messages.sort(key=lambda m: m.get("time", 0))

        return {
            "chat_sn": sn,
            "chat_name": sn,
            "total_messages": len(messages),
            "pinned_messages": [],
            "messages": messages,
        }
