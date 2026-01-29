"""
VK Teams API Client
Работа с API VK Teams для получения чатов и сообщений
"""

import asyncio
import aiohttp
import random
from dataclasses import dataclass
from typing import Optional
import config


@dataclass
class VKTeamsSession:
    """Сессия пользователя VK Teams"""
    aimsid: str
    email: str


class VKTeamsClient:
    """Клиент для работы с VK Teams API"""

    def __init__(self, session: VKTeamsSession):
        self.session = session
        self.api_base = config.VKTEAMS_API_BASE

    def _generate_req_id(self) -> str:
        return f"{random.randint(1000, 9999)}-{int(asyncio.get_event_loop().time() * 1000)}"

    async def _request(self, method: str, params: dict) -> dict:
        """Выполнить запрос к API"""
        body = {
            "reqId": self._generate_req_id(),
            "aimsid": self.session.aimsid,
            "params": params
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-teams-aimsid": self.session.aimsid
        }

        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{self.api_base}/{method}",
                json=body,
                headers=headers
            ) as response:
                return await response.json()

    async def get_contact_list(self) -> list[dict]:
        """Получить список всех чатов/контактов"""
        data = await self._request("getContactList", {"lang": "ru"})

        if data.get("status", {}).get("code") != 20000:
            raise Exception(f"API Error: {data.get('status')}")

        contacts = data.get("results", {}).get("contacts", [])
        return contacts

    async def get_chat_info(self, sn: str) -> dict:
        """Получить информацию о чате"""
        data = await self._request("getChatInfo", {"sn": sn, "lang": "ru"})
        return data.get("results", {})

    async def get_history(
        self,
        sn: str,
        from_msg_id: Optional[str] = None,
        count: int = -50
    ) -> dict:
        """
        Получить историю сообщений чата

        Args:
            sn: ID чата (например '687589145@chat.agent')
            from_msg_id: ID сообщения для пагинации (получить более старые)
            count: Количество сообщений (отрицательное = старые)
        """
        params = {
            "sn": sn,
            "count": count,
            "lang": "ru",
            "mentions": {"resolve": True},
            "patchVersion": "1"
        }

        if from_msg_id:
            params["fromMsgId"] = from_msg_id

        data = await self._request("getHistory", params)

        if data.get("status", {}).get("code") != 20000:
            raise Exception(f"API Error: {data.get('status')}")

        return data.get("results", {})

    async def export_chat(
        self,
        sn: str,
        max_messages: int = 10000,
        progress_callback=None
    ) -> dict:
        """
        Экспортировать всю историю чата

        Args:
            sn: ID чата
            max_messages: Максимальное количество сообщений
            progress_callback: async функция для отчёта о прогрессе

        Returns:
            dict с messages, pinned, chat_info
        """
        all_messages = []
        pinned_messages = []
        from_msg_id = None
        chat_info = None
        request_count = 0

        while len(all_messages) < max_messages:
            request_count += 1

            try:
                results = await self.get_history(sn, from_msg_id)

                # Сохраняем закреплённые (только из первого запроса)
                if request_count == 1:
                    pinned_messages = results.get("pinned", [])
                    # Пробуем получить название чата
                    if results.get("messages"):
                        first_msg = results["messages"][0]
                        chat_info = {
                            "sn": sn,
                            "name": first_msg.get("chat", {}).get("name", sn)
                        }

                messages = results.get("messages", [])

                if not messages:
                    break

                all_messages.extend(messages)

                # Прогресс
                if progress_callback:
                    await progress_callback(len(all_messages), request_count)

                # Следующая страница
                older_msg_id = results.get("olderMsgId")
                if not older_msg_id:
                    break

                from_msg_id = older_msg_id

                # Если пришло меньше чем запрашивали — конец
                if len(messages) < config.MESSAGES_PER_REQUEST:
                    break

                # Пауза между запросами
                await asyncio.sleep(config.DELAY_BETWEEN_REQUESTS)

            except Exception as e:
                # При ошибке пробуем продолжить
                if request_count > 3 and len(all_messages) == 0:
                    raise e
                await asyncio.sleep(2)

        # Сортируем по времени (старые первые)
        all_messages.sort(key=lambda m: m.get("time", 0))

        return {
            "chat_sn": sn,
            "chat_name": chat_info.get("name") if chat_info else sn,
            "total_messages": len(all_messages),
            "pinned_messages": pinned_messages,
            "messages": all_messages
        }


class VKTeamsAuth:
    """
    Авторизация в VK Teams

    ВНИМАНИЕ: Это недокументированный API!
    Эндпоинты могут измениться в любой момент.
    """

    # Ключ клиента (из веб-версии)
    CLIENT_KEY = "ic1zmlWFTdkiTnkL"
    CLIENT_NAME = "webVKTeams"
    CLIENT_VERSION = "VKTeams Web"

    def __init__(self, api_base: str = None):
        self.api_base = api_base or "https://u.myteam.vmailru.net/api/v139/wim/auth"

    async def send_code(self, email: str) -> dict:
        """
        Отправить код подтверждения на email

        Endpoint: GET /clientLogin?tokenType=otp_via_email&s=email
        После вызова на почту приходит одноразовый пароль.

        Returns:
            dict с loginId и другими данными
        """
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
            async with http.get(
                url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
                data="pwd=1"
            ) as response:
                data = await response.json()

        if data.get("response", {}).get("statusCode") != 200:
            raise Exception(f"Auth Error: {data}")

        return data.get("response", {}).get("data", {})

    async def verify_code(self, email: str, code: str) -> VKTeamsSession:
        """
        Проверить код и получить сессию (aimsid)

        Шаг 2: POST /clientLogin?tokenType=longTerm + pwd=КОД → token.a
        Шаг 3: POST /aim/startSession?a=TOKEN → aimsid
        """
        import urllib.parse
        import uuid

        # Шаг 2: Получаем token
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
            async with http.post(
                url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
                data=f"pwd={code}"
            ) as response:
                data = await response.json()

        if data.get("response", {}).get("statusCode") != 200:
            error_text = data.get("response", {}).get("statusText", "Unknown error")
            raise Exception(f"Неверный код или ошибка: {error_text}")

        token_data = data.get("response", {}).get("data", {})
        token_a = token_data.get("token", {}).get("a")
        session_secret = token_data.get("sessionSecret")

        if not token_a:
            raise Exception("Не удалось получить токен авторизации")

        # Шаг 3: Получаем aimsid через startSession
        aimsid = await self._start_session(email, token_a)

        return VKTeamsSession(aimsid=aimsid, email=email)

    async def _start_session(self, email: str, token_a: str) -> str:
        """
        Шаг 3: Создание сессии и получение aimsid

        POST /aim/startSession?a=TOKEN&userSn=email&...
        """
        import urllib.parse
        import uuid
        import time

        device_id = str(uuid.uuid4())
        ts = int(time.time())

        # Capabilities (из оригинального запроса)
        assert_caps = [
            "094613584C7F11D18222444553540000",
            "0946135C4C7F11D18222444553540000",
            "0946135b4c7f11d18222444553540000",
            "0946135E4C7F11D18222444553540000",
            "AABC2A1AF270424598B36993C6231952",
            "1f99494e76cbc880215d6aeab8e42268",
            "A20C362CD4944B6EA3D1E77642201FD8",
            "B5ED3E51C7AC4137B5926BC686E7A60D",
            "094613504c7f11d18222444553540000",
            "094613514c7f11d18222444553540000",
            "094613564c7f11d18222444553540000",
            "094613503c7f11d18222444553540000",
        ]

        interest_caps = [
            "8eec67ce70d041009409a7c1602a5c84",
            "094613504c7f11d18222444553540000",
            "094613514c7f11d18222444553540000",
            "094613564c7f11d18222444553540000",
        ]

        events = [
            "myInfo", "presence", "buddylist", "typing", "hiddenChat",
            "hist", "mchat", "sentIM", "imState", "dataIM", "offlineIM",
            "userAddedToBuddyList", "service", "lifestream", "apps",
            "permitDeny", "diff", "webrtcMsg"
        ]

        presence_fields = [
            "aimId", "displayId", "friendly", "friendlyName", "state",
            "userType", "statusMsg", "statusTime", "ssl", "mute",
            "counterEnabled", "abContactName", "abPhoneNumber", "abPhones",
            "official", "quiet", "autoAddition", "largeIconId", "nick", "userState"
        ]

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
            "sessionTimeout": 2592000,  # 30 дней
            "assertCaps": ",".join(assert_caps),
            "interestCaps": ",".join(interest_caps),
            "subscriptions": "status",
            "events": ",".join(events),
            "includePresenceFields": ",".join(presence_fields),
        }

        # Используем базовый URL без /auth
        base_url = self.api_base.replace("/wim/auth", "/wim/aim")
        url = f"{base_url}/startSession?" + urllib.parse.urlencode(params)

        async with aiohttp.ClientSession() as http:
            async with http.post(
                url,
                headers={
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
            ) as response:
                data = await response.json()

        if data.get("response", {}).get("statusCode") != 200:
            error_text = data.get("response", {}).get("statusText", "Unknown error")
            raise Exception(f"Ошибка создания сессии: {error_text}")

        aimsid = data.get("response", {}).get("data", {}).get("aimsid")

        if not aimsid:
            raise Exception("Не удалось получить aimsid")

        return aimsid

    @staticmethod
    def create_session_from_aimsid(aimsid: str) -> VKTeamsSession:
        """
        Создать сессию из готового aimsid

        aimsid формат: "010.XXXXXXXXX.XXXXXXXXX:email@domain.com"
        """
        # Извлекаем email из aimsid
        email = ""
        if ":" in aimsid:
            email = aimsid.split(":")[-1]

        return VKTeamsSession(aimsid=aimsid, email=email)
