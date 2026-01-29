"""
VK Teams API Client
Работа с API VK Teams для получения чатов и сообщений
"""

import asyncio
import aiohttp
import random
import time
import logging
from dataclasses import dataclass
from typing import Optional
import config

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =========================
# Models
# =========================

@dataclass
class VKTeamsSession:
    """Сессия пользователя VK Teams"""
    aimsid: str
    email: str
    fetch_base_url: str = ""  # URL для fetchEvents


# =========================
# API Client
# =========================

class VKTeamsClient:
    """Клиент для работы с VK Teams API (RAPI)"""

    def __init__(self, session: VKTeamsSession):
        self.session = session
        # Используем rapi вместо wim - проверено что работает
        self.api_base = "https://u.myteam.vmailru.net/api/v139/rapi"

    def _generate_req_id(self) -> str:
        return f"{random.randint(1000, 9999)}-{int(time.time() * 1000)}"

    async def _request(self, method: str, params: dict) -> dict:
        """Выполнить запрос к RAPI"""

        body = {
            "reqId": self._generate_req_id(),
            "aimsid": self.session.aimsid,
            "params": params
        }

        url = f"{self.api_base}/{method}"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-teams-aimsid": self.session.aimsid,
            "Origin": "https://myteam.mail.ru",
            "Referer": "https://myteam.mail.ru/",
        }

        logger.debug(f"API request: {method} -> {url}")

        async with aiohttp.ClientSession() as http:
            async with http.post(url, json=body, headers=headers) as response:
                logger.debug(f"Response status: {response.status}, content-type: {response.content_type}")

                if response.content_type != "application/json":
                    text = await response.text()
                    logger.error(f"Non-JSON response: {text[:500]}")
                    raise Exception(f"API returned {response.content_type}: {text[:200]}")

                data = await response.json()

        # единая проверка статуса
        status = data.get("status", {})
        if status.get("code") != 20000:
            logger.error(f"API error: {status}")
            raise Exception(f"API Error: {status}")

        return data.get("results", {})

    # ---------------------

    async def get_contact_list(self) -> list[dict]:
        """Получить список всех чатов/контактов через fetchEvents"""

        if not self.session.fetch_base_url:
            logger.warning("No fetchBaseURL available")
            return []

        logger.debug(f"Fetching contacts via: {self.session.fetch_base_url[:80]}...")

        headers = {
            "Accept": "application/json",
            "Origin": "https://myteam.mail.ru",
            "Referer": "https://myteam.mail.ru/",
        }

        async with aiohttp.ClientSession() as http:
            async with http.get(self.session.fetch_base_url, headers=headers) as response:
                logger.debug(f"fetchEvents status: {response.status}")

                if response.content_type != "application/json":
                    text = await response.text()
                    logger.error(f"fetchEvents non-JSON: {text[:200]}")
                    return []

                data = await response.json()

        # Логируем полный ответ для отладки
        import json
        logger.debug(f"fetchEvents full response: {json.dumps(data, ensure_ascii=False)[:2000]}")

        # Извлекаем контакты из событий buddylist
        contacts = []
        events = data.get("response", {}).get("data", {}).get("events", [])
        logger.debug(f"Found {len(events)} events, types: {[e.get('type') for e in events]}")

        for event in events:
            if event.get("type") == "buddylist":
                groups = event.get("data", {}).get("groups", [])
                for group in groups:
                    buddies = group.get("buddies", [])
                    for buddy in buddies:
                        contacts.append({
                            "sn": buddy.get("aimId", ""),
                            "name": buddy.get("friendly", buddy.get("aimId", "")),
                            "type": buddy.get("userType", ""),
                        })

        logger.info(f"Found {len(contacts)} contacts via fetchEvents")
        return contacts

    async def get_chat_info(self, sn: str) -> dict:
        """Получить информацию о чате"""
        results = await self._request("getChatInfo", {"sn": sn, "lang": "ru"})
        return results

    async def get_history(
        self,
        sn: str,
        from_msg_id: Optional[str] = None,
        count: int = -50
    ) -> dict:
        """
        Получить историю сообщений чата

        sn: ID чата (например '687589145@chat.agent')
        from_msg_id: ID сообщения для пагинации
        count: отрицательное = получать более старые
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

        return await self._request("getHistory", params)

    # ---------------------

    async def export_chat(
        self,
        sn: str,
        max_messages: int = 10000,
        progress_callback=None
    ) -> dict:
        """Экспорт всей истории чата"""

        all_messages = []
        pinned_messages = []
        from_msg_id = None
        chat_info = None
        request_count = 0

        while len(all_messages) < max_messages:
            request_count += 1

            results = await self.get_history(sn, from_msg_id)

            if request_count == 1:
                pinned_messages = results.get("pinned", [])
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

            if progress_callback:
                await progress_callback(len(all_messages), request_count)

            older_msg_id = results.get("olderMsgId")
            if not older_msg_id:
                break

            from_msg_id = older_msg_id

            if len(messages) < abs(config.MESSAGES_PER_REQUEST):
                break

            await asyncio.sleep(config.DELAY_BETWEEN_REQUESTS)

        all_messages.sort(key=lambda m: m.get("time", 0))

        return {
            "chat_sn": sn,
            "chat_name": chat_info.get("name") if chat_info else sn,
            "total_messages": len(all_messages),
            "pinned_messages": pinned_messages,
            "messages": all_messages
        }


# =========================
# AUTH
# =========================

class VKTeamsAuth:
    """
    Авторизация в VK Teams (undocumented API)
    """

    CLIENT_KEY = "ic1zmlWFTdkiTnkL"
    CLIENT_NAME = "webVKTeams"
    CLIENT_VERSION = "VKTeams Web"

    def __init__(self, api_base: str = None):
        self.api_base = api_base or "https://u.myteam.vmailru.net/api/v139/wim/auth"

    async def send_code(self, email: str) -> dict:
        """Отправить код на email"""

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
        logger.info(f"Sending code request to: {url}")

        async with aiohttp.ClientSession() as http:
            async with http.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
                data="pwd=1"
            ) as response:
                logger.debug(f"Response status: {response.status}")
                logger.debug(f"Response content-type: {response.content_type}")

                text = await response.text()
                logger.debug(f"Response body (first 500 chars): {text[:500]}")

                if response.content_type != "application/json":
                    raise Exception(f"Unexpected response type: {response.content_type}. Body: {text[:200]}")

                import json
                data = json.loads(text)

        if data.get("response", {}).get("statusCode") != 200:
            error_detail = data.get("response", {})
            logger.error(f"API error: {error_detail}")
            raise Exception(f"Auth Error: {error_detail}")

        return data["response"]["data"]

    async def verify_code(self, email: str, code: str) -> VKTeamsSession:
        """Проверить код и получить aimsid"""

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
        logger.info(f"Verifying code, URL: {url}")

        async with aiohttp.ClientSession() as http:
            async with http.post(
                url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
                data=f"pwd={code}"
            ) as response:
                logger.debug(f"Response status: {response.status}")
                text = await response.text()
                logger.debug(f"Response body (first 500 chars): {text[:500]}")

                if response.content_type != "application/json":
                    raise Exception(f"Unexpected response: {text[:200]}")

                import json
                data = json.loads(text)

        if data.get("response", {}).get("statusCode") != 200:
            error_text = data.get("response", {}).get("statusText", "Unknown error")
            logger.error(f"Verify code failed: {data}")
            raise Exception(f"Неверный код или ошибка: {error_text}")

        token_a = data["response"]["data"]["token"]["a"]
        logger.info(f"Got token_a: {token_a[:20] if token_a else 'None'}...")

        aimsid, fetch_base_url = await self._start_session(email, token_a)
        return VKTeamsSession(aimsid=aimsid, email=email, fetch_base_url=fetch_base_url)

    async def _start_session(self, email: str, token_a: str) -> str:
        """POST /wim/aim/startSession"""

        import urllib.parse
        import uuid

        device_id = str(uuid.uuid4())
        ts = int(time.time())

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
            "sessionTimeout": 2592000,
            "assertCaps": ",".join(assert_caps),
            "interestCaps": ",".join(interest_caps),
            "subscriptions": "status",
            "events": ",".join(events),
            "includePresenceFields": ",".join(presence_fields),
        }

        base_url = self.api_base.replace("/wim/auth", "/wim/aim")
        url = f"{base_url}/startSession?" + urllib.parse.urlencode(params)
        logger.info(f"Starting session, URL: {url[:100]}...")

        async with aiohttp.ClientSession() as http:
            async with http.post(
                url,
                headers={
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Accept": "application/json",
                    "Origin": "https://myteam.mail.ru",
                    "Referer": "https://myteam.mail.ru/",
                },
            ) as response:
                logger.debug(f"Response status: {response.status}")
                text = await response.text()
                logger.debug(f"Response body (first 500 chars): {text[:500]}")

                if response.content_type != "application/json":
                    raise Exception(f"Unexpected response: {text[:200]}")

                import json
                data = json.loads(text)

        if data.get("response", {}).get("statusCode") != 200:
            error_text = data.get("response", {}).get("statusText", "Unknown error")
            logger.error(f"Start session failed: {data}")
            raise Exception(f"Ошибка создания сессии: {error_text}")

        response_data = data["response"]["data"]
        aimsid = response_data["aimsid"]
        fetch_base_url = response_data.get("fetchBaseURL", "")
        logger.info(f"Got aimsid: {aimsid[:30] if aimsid else 'None'}...")
        logger.info(f"Got fetchBaseURL: {fetch_base_url[:50] if fetch_base_url else 'None'}...")

        return aimsid, fetch_base_url

    @staticmethod
    def create_session_from_aimsid(aimsid: str) -> VKTeamsSession:
        email = aimsid.split(":")[-1] if ":" in aimsid else ""
        return VKTeamsSession(aimsid=aimsid, email=email)
