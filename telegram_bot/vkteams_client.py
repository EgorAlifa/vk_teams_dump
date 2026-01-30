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

    async def _request(self, method: str, params: dict, retries: int = 3) -> dict:
        """Выполнить запрос к RAPI с retry логикой"""

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

        last_error = None

        for attempt in range(retries):
            try:
                logger.debug(f"API request: {method} -> {url} (attempt {attempt + 1})")

                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
                    async with http.post(url, json=body, headers=headers) as response:
                        logger.debug(f"Response status: {response.status}, content-type: {response.content_type}")

                        if response.content_type != "application/json":
                            text = await response.text()
                            logger.error(f"Non-JSON response: {text[:500]}")
                            raise Exception(f"API returned {response.content_type}: {text[:200]}")

                        data = await response.json()

                # Check for timeout error in response
                status = data.get("status", {})
                if status.get("code") == 50000:  # Request timed out
                    logger.warning(f"API timeout (code 50000), attempt {attempt + 1}/{retries}")
                    last_error = Exception(f"API Error: {status}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1, 2, 4 sec
                        continue
                    raise last_error

                if status.get("code") != 20000:
                    logger.error(f"API error: {status}")
                    raise Exception(f"API Error: {status}")

                return data.get("results", {})

            except aiohttp.ClientError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                last_error = e
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

            except asyncio.TimeoutError:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                last_error = Exception("Request timeout")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise last_error

        raise last_error or Exception("Request failed after retries")

    # ---------------------

    async def get_contact_list(self) -> list[dict]:
        """Получить список всех чатов/контактов - комбинация из нескольких источников"""

        all_contacts = {}  # sn -> contact dict (для дедупликации)

        # 1. Получаем контакты через RAPI getContactList
        try:
            rapi_contacts = await self._get_contact_list_rapi()
            for contact in rapi_contacts:
                sn = contact.get("sn", "")
                if sn:
                    all_contacts[sn] = contact
            logger.info(f"Got {len(rapi_contacts)} contacts from RAPI getContactList")
        except Exception as e:
            logger.warning(f"Failed to get contacts via RAPI: {e}")

        # 2. Получаем диалоги через RAPI getDialogs (может содержать больше чатов)
        try:
            dialogs = await self._get_dialogs_rapi()
            for contact in dialogs:
                sn = contact.get("sn", "")
                if sn:
                    if sn in all_contacts:
                        all_contacts[sn].update(contact)
                    else:
                        all_contacts[sn] = contact
        except Exception as e:
            logger.warning(f"Failed to get dialogs via RAPI: {e}")

        # 3. Получаем контакты через fetchEvents (buddylist + histDlgState)
        if self.session.fetch_base_url:
            try:
                fetch_contacts = await self._get_contact_list_fetch_events()
                for contact in fetch_contacts:
                    sn = contact.get("sn", "")
                    if sn:
                        # Мержим данные, приоритет у fetchEvents (там актуальнее)
                        if sn in all_contacts:
                            all_contacts[sn].update(contact)
                        else:
                            all_contacts[sn] = contact
                logger.info(f"Got {len(fetch_contacts)} contacts from fetchEvents")
            except Exception as e:
                logger.warning(f"Failed to get contacts via fetchEvents: {e}")

        contacts = list(all_contacts.values())
        logger.info(f"Total unique contacts: {len(contacts)}")
        return contacts

    async def _get_contact_list_rapi(self) -> list[dict]:
        """Получить контакты через RAPI getContactList"""
        results = await self._request("getContactList", {"lang": "ru"})

        contacts = []
        for contact in results.get("contacts", []):
            sn = contact.get("sn") or contact.get("aimId", "")
            if not sn:
                continue

            contacts.append({
                "sn": sn,
                "name": contact.get("friendly", contact.get("nick", sn)),
                "friendly": contact.get("friendly", ""),
                "nick": contact.get("nick", ""),
                "type": "chat" if "@chat.agent" in sn else "contact",
                "userType": contact.get("userType", ""),
            })

        return contacts

    async def _get_dialogs_rapi(self) -> list[dict]:
        """Получить диалоги через RAPI getDialogs - может содержать больше чатов"""
        try:
            results = await self._request("getDialogs", {
                "lang": "ru",
                "count": 1000,  # Запрашиваем много
            })

            contacts = []
            for dialog in results.get("dialogs", []):
                sn = dialog.get("sn", "")
                if not sn:
                    continue

                contacts.append({
                    "sn": sn,
                    "name": dialog.get("friendly", dialog.get("name", sn)),
                    "friendly": dialog.get("friendly", ""),
                    "type": "chat" if "@chat.agent" in sn else "contact",
                    "has_messages": True,  # Диалоги это чаты с сообщениями
                    "unread_count": dialog.get("unreadCount", 0),
                    "last_msg_id": dialog.get("lastMsgId", ""),
                })

            logger.info(f"Got {len(contacts)} dialogs from RAPI getDialogs")
            return contacts

        except Exception as e:
            logger.debug(f"getDialogs not available: {e}")
            return []

    async def _get_contact_list_fetch_events(self, max_iterations: int = 15) -> list[dict]:
        """
        Получить контакты через fetchEvents с long-polling.

        VK Teams использует long-polling: каждый ответ содержит новый fetchBaseURL
        с обновлённым seqNum. Нужно делать несколько запросов чтобы получить
        все histDlgState события (диалоги с перепиской).
        """

        if not self.session.fetch_base_url:
            logger.warning("No fetchBaseURL available")
            return []

        headers = {
            "Accept": "application/json",
            "Origin": "https://myteam.mail.ru",
            "Referer": "https://myteam.mail.ru/",
            "x-teams-aimsid": self.session.aimsid,
        }

        contacts = []
        contacts_by_sn = {}  # sn -> contact dict для дедупликации
        contacts_with_messages = set()  # sn чатов с перепиской
        blocked_users = {}  # sn -> user state info

        current_url = self.session.fetch_base_url
        # Добавляем короткий timeout чтобы сервер сразу возвращал ответ
        if "timeout=" not in current_url:
            current_url += "&timeout=1"
        iteration = 0
        total_events = 0
        hist_dlg_count = 0

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as http:
            while iteration < max_iterations:
                iteration += 1
                logger.debug(f"fetchEvents iteration {iteration}, URL: {current_url[:80]}...")

                try:
                    async with http.get(current_url, headers=headers) as response:
                        logger.debug(f"fetchEvents status: {response.status}")

                        if response.content_type != "application/json":
                            text = await response.text()
                            logger.error(f"fetchEvents non-JSON: {text[:200]}")
                            break

                        data = await response.json()
                except asyncio.TimeoutError:
                    logger.warning(f"fetchEvents timeout on iteration {iteration}")
                    break
                except Exception as e:
                    logger.error(f"fetchEvents error: {e}")
                    break

                # Получаем следующий URL для long-polling
                response_data = data.get("response", {}).get("data", {})
                next_url = response_data.get("fetchBaseURL", "")
                events = response_data.get("events", [])

                total_events += len(events)
                event_types = [e.get("type") for e in events]
                logger.debug(f"Iteration {iteration}: {len(events)} events, types: {set(event_types)}")

                # Обрабатываем события
                new_hist_dlg = 0
                for event in events:
                    event_type = event.get("type")
                    event_data = event.get("eventData", event.get("data", {}))

                    if event_type == "buddylist":
                        # Контакты из buddylist
                        groups = event_data.get("groups", [])
                        for group in groups:
                            buddies = group.get("buddies", [])
                            for buddy in buddies:
                                sn = buddy.get("aimId", "")
                                if sn and sn not in contacts_by_sn:
                                    contact = {
                                        "sn": sn,
                                        "name": buddy.get("friendly", sn),
                                        "friendly": buddy.get("friendly", ""),
                                        "type": buddy.get("userType", ""),
                                    }
                                    contacts_by_sn[sn] = contact

                    elif event_type == "histDlgState":
                        # Диалоги/чаты из histDlgState - это чаты с перепиской
                        sn = event_data.get("sn", "")
                        if sn:
                            new_hist_dlg += 1
                            contacts_with_messages.add(sn)

                            # Определяем имя чата
                            name = sn
                            if event_data.get("chat"):
                                name = event_data["chat"].get("name", sn)
                            elif event_data.get("friendly"):
                                name = event_data.get("friendly")

                            # Обновляем или добавляем контакт
                            if sn in contacts_by_sn:
                                contacts_by_sn[sn]["has_messages"] = True
                                if name != sn:
                                    contacts_by_sn[sn]["name"] = name
                            else:
                                contacts_by_sn[sn] = {
                                    "sn": sn,
                                    "name": name,
                                    "friendly": event_data.get("friendly", ""),
                                    "type": "chat" if "@chat.agent" in sn else "contact",
                                    "has_messages": True,
                                }

                    elif event_type == "userState":
                        # Track blocked/deleted users
                        sn = event_data.get("sn", "")
                        user_state = event_data.get("userState", {})
                        if sn and user_state.get("state") == "blocked":
                            blocked_users[sn] = user_state

                hist_dlg_count += new_hist_dlg
                logger.debug(f"Iteration {iteration}: +{new_hist_dlg} histDlgState, total dialogs: {hist_dlg_count}")

                # Условия выхода из цикла
                if not next_url:
                    logger.debug("No more fetchBaseURL, stopping")
                    break

                # Если нет новых событий или только status события - можно остановиться
                if not events:
                    logger.debug("No events in response, stopping")
                    break

                # Если получили только status события несколько раз подряд - диалоги закончились
                if all(e.get("type") == "status" for e in events) and iteration > 3:
                    logger.debug("Only status events, dialogs likely complete")
                    break

                # Обновляем URL для следующей итерации
                current_url = next_url
                # Добавляем короткий timeout
                if "timeout=" not in current_url:
                    current_url += "&timeout=1"

                # Небольшая пауза между запросами
                await asyncio.sleep(0.1)

        logger.info(f"fetchEvents completed: {iteration} iterations, {total_events} total events, {hist_dlg_count} dialogs")

        # Формируем итоговый список
        contacts = list(contacts_by_sn.values())

        # Помечаем контакты у которых есть переписка
        for contact in contacts:
            if contact["sn"] in contacts_with_messages:
                contact["has_messages"] = True

        # Add blocked users with messages that might not be in the list
        existing_sns = {c["sn"] for c in contacts}
        for sn in contacts_with_messages:
            if sn not in existing_sns and "@chat.agent" not in sn:
                # This is a personal chat with messages but user might be blocked/deleted
                is_blocked = sn in blocked_users
                contacts.append({
                    "sn": sn,
                    "name": sn,  # Use email as name
                    "friendly": "",
                    "type": "contact",
                    "has_messages": True,
                    "is_blocked": is_blocked,
                })

        # Mark blocked users in existing contacts
        for contact in contacts:
            sn = contact.get("sn", "")
            if sn in blocked_users:
                contact["is_blocked"] = True

        logger.info(f"Found {len(contacts)} contacts via fetchEvents, {len(contacts_with_messages)} with messages, {len(blocked_users)} blocked")
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
            "fromMsgId": from_msg_id or "-1",  # -1 = с последнего сообщения
            "count": count,
            "lang": "ru",
            "mentions": {"resolve": False},
            "patchVersion": "1"
        }

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
