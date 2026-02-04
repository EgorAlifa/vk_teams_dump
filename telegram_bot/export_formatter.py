"""
Форматирование экспорта VK Teams в различные форматы
Современный дизайн 2025 - тёмная/светлая тема с тёплыми акцентами
"""

import json
import base64
from datetime import datetime
from html import escape


def format_as_json(data: dict) -> str:
    """Форматирование в JSON"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_as_html(data: dict, avatars: dict = None, names: dict = None, mobile: bool = False, files_url_map: dict = None) -> str:
    """
    Форматирование в HTML - современный дизайн 2025
    Светлая/тёмная тема, CSS-переключение чатов, аватарки

    Args:
        data: Данные экспорта
        avatars: Словарь {sn: bytes} с аватарками (опционально)
        names: Словарь {sn: display_name} для отображения имён (опционально)
        mobile: Если True, генерировать мобильную версию
        files_url_map: Словарь {original_url: local_url} для замены ссылок на файлы (опционально)
    """
    avatars = avatars or {}
    names = names or {}
    files_url_map = files_url_map or {}

    # Фильтруем чаты без сообщений
    chats = [c for c in data.get("chats", []) if c.get("messages")]
    total_messages = sum(len(c.get("messages", [])) for c in chats)
    export_date = data.get("export_date", datetime.now().isoformat())[:10]

    # Генерируем список чатов (sidebar) и контент
    sidebar_items = ""
    content_panels = ""

    for idx, chat in enumerate(chats):
        chat_sn = chat.get("chat_sn", "")
        raw_chat_name = chat.get("chat_name", chat_sn or "Чат")
        messages = chat.get("messages", [])
        is_personal = "@chat.agent" not in chat_sn
        msg_count = len(messages)

        # Определяем отображаемое имя чата
        # 1. Сначала проверяем словарь имён
        if chat_sn in names and names[chat_sn]:
            friendly_name = names[chat_sn]
            if is_personal and "@" in chat_sn:
                chat_name = escape(f"{friendly_name} ({chat_sn})")
            else:
                chat_name = escape(friendly_name)
        elif is_personal and chat_sn and "@" in chat_sn:
            # Личный чат - ищем имя собеседника
            friendly_name = None

            # 2. Проверяем chat_name - API мог уже дать имя
            if raw_chat_name and raw_chat_name != chat_sn and "@" not in raw_chat_name:
                friendly_name = raw_chat_name

            # 3. Ищем в сообщениях от этого человека
            if not friendly_name:
                for msg in messages:
                    sender_sn = msg.get("chat", {}).get("sender") or msg.get("senderSn") or ""
                    if sender_sn == chat_sn:
                        fn = msg.get("senderNick") or msg.get("friendly") or ""
                        if fn and fn.strip() not in ("", "- -", "--", chat_sn) and "@" not in fn:
                            friendly_name = fn.strip()
                            break

            # 4. Ищем в любых сообщениях где упоминается этот sn
            if not friendly_name:
                for msg in messages:
                    # Может быть в outgoing сообщениях как получатель
                    msg_friendly = msg.get("friendly") or ""
                    if msg_friendly and msg_friendly.strip() not in ("", "- -", "--") and "@" not in msg_friendly:
                        friendly_name = msg_friendly.strip()
                        break

            if friendly_name:
                chat_name = escape(f"{friendly_name} ({chat_sn})")
            else:
                chat_name = escape(chat_sn)
        else:
            # Групповой чат - используем имя как есть
            chat_name = escape(raw_chat_name)

        # Последнее сообщение для превью
        last_msg = messages[-1] if messages else {}
        last_text = ""
        last_sender = ""
        if last_msg:
            parts = last_msg.get("parts", [])
            for p in parts:
                if p.get("mediaType") == "text":
                    last_text = p.get("text", "")[:50]
                    break
            if not last_text:
                last_text = last_msg.get("text", "")[:50]
            last_sender = last_msg.get("senderNick") or last_msg.get("friendly") or ""
        last_text = escape(last_text) if last_text else "..."
        last_sender = escape(last_sender[:15]) if last_sender else ""

        # Время последнего сообщения
        last_time = ""
        if last_msg.get("time"):
            last_time = datetime.fromtimestamp(last_msg["time"]).strftime("%d.%m")

        avatar_letter = chat_name[0].upper() if chat_name else "?"

        # Avatar: base64 image or letter
        avatar_html = ""
        if chat_sn in avatars:
            avatar_b64 = base64.b64encode(avatars[chat_sn]).decode('ascii')
            avatar_html = f'<img src="data:image/jpeg;base64,{avatar_b64}" alt="">'
        else:
            avatar_html = avatar_letter

        # Собираем участников (с приоритетом словаря имён)
        chat_members = {}
        for msg in messages:
            sender_sn = (
                msg.get("chat", {}).get("sender") or
                msg.get("senderSn") or
                msg.get("sn") or
                msg.get("sender") or
                ""
            )
            if sender_sn and sender_sn not in chat_members:
                # Приоритет: словарь имён > senderNick > friendly > sn
                friendly = names.get(sender_sn) or msg.get("senderNick") or msg.get("friendly") or ""
                chat_members[sender_sn] = {
                    "friendly": friendly,
                    "sn": sender_sn
                }

        # Сообщения чата
        messages_html = ""
        current_date = ""
        for msg in messages:
            msg_time = msg.get("time", 0)
            if msg_time:
                msg_date = datetime.fromtimestamp(msg_time).strftime("%d.%m.%Y")
                if msg_date != current_date:
                    current_date = msg_date
                    messages_html += f'<div class="date-sep"><span>{msg_date}</span></div>'

            messages_html += render_message(msg, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal, names=names, files_url_map=files_url_map)

        # Закреплённые
        pinned = chat.get("pinned_messages", [])
        pinned_html = ""
        if pinned:
            pinned_html = f'''
            <details class="pinned">
                <summary>📌 Закреплённых: {len(pinned)}</summary>
                <div class="pinned-list">
                    {"".join(render_message(m, pinned=True, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal, names=names, files_url_map=files_url_map) for m in pinned)}
                </div>
            </details>
            '''

        # Превью текста
        preview = f'<span class="preview-sender">{last_sender}:</span> {last_text}' if last_sender and not is_personal else last_text

        # Radio для CSS-переключения
        checked = 'checked' if idx == 0 else ''

        sidebar_items += f'''
<input type="radio" name="chat" id="c{idx}" class="chat-radio" {checked}>
<label for="c{idx}" class="chat-item" data-idx="{idx}">
    <div class="avatar">{avatar_html}</div>
    <div class="chat-info">
        <div class="chat-name">{chat_name[:30]}{"…" if len(chat_name) > 30 else ""}</div>
        <div class="chat-preview">{preview}</div>
    </div>
    <div class="chat-meta">
        <span class="chat-time">{last_time}</span>
        <span class="chat-badge">{msg_count}</span>
    </div>
</label>
'''

        content_panels += f'''
<div class="chat-panel" id="p{idx}">
    <div class="panel-header">
        <label for="closeChat" class="back-btn">‹</label>
        <div class="avatar sm">{avatar_html}</div>
        <div class="header-info">
            <div class="header-name">{chat_name}</div>
            <div class="header-sub">{msg_count} сообщений</div>
        </div>
        <button class="search-toggle" onclick="toggleSearch(this)">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
            </svg>
        </button>
    </div>
    <div class="panel-search">
        <input type="text" placeholder="Поиск в чате..." oninput="searchInChat(this)" onkeydown="searchInChat(this,event)">
        <span class="search-info"></span>
        <button onclick="navSearch(this,-1)">↑</button>
        <button onclick="navSearch(this,1)">↓</button>
        <button onclick="closeSearch(this)">✕</button>
    </div>
    {pinned_html}
    <div class="messages">{messages_html}</div>
</div>
'''

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VK Teams Export</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
/* Dark theme (default) */
:root{{
    --bg:#0f0f12;
    --bg2:#16161b;
    --card:#1c1c24;
    --card2:#242430;
    --accent:#10b981;
    --accent2:#34d399;
    --accent-bg:rgba(16,185,129,0.1);
    --purple:#8b5cf6;
    --orange:#f59e0b;
    --pink:#ec4899;
    --blue:#3b82f6;
    --text:#f4f4f5;
    --text2:#a1a1aa;
    --text3:#71717a;
    --border:#27272a;
    --border2:#3f3f46;
    --hover:#27272e;
    --msg-out:#1e3a2f;
    --msg-in:#27272e;
    --hl:rgba(16,185,129,0.25);
    --shadow:0 2px 8px rgba(0,0,0,0.3);
    --shadow-lg:0 8px 32px rgba(0,0,0,0.4);
    --radius:12px;
    --radius-lg:16px;
}}
/* Light theme */
.light{{
    --bg:#f5f5f7;
    --bg2:#ffffff;
    --card:#ffffff;
    --card2:#f0f0f2;
    --accent:#059669;
    --accent2:#10b981;
    --accent-bg:rgba(5,150,105,0.1);
    --text:#1a1a1a;
    --text2:#52525b;
    --text3:#71717a;
    --border:#e4e4e7;
    --border2:#d4d4d8;
    --hover:#f4f4f5;
    --msg-out:#d1fae5;
    --msg-in:#ffffff;
    --hl:rgba(5,150,105,0.15);
    --shadow:0 1px 3px rgba(0,0,0,0.08);
    --shadow-lg:0 4px 12px rgba(0,0,0,0.1);
}}
html,body{{height:100%;overflow:hidden}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;transition:background 0.3s,color 0.3s}}

/* Theme toggle */
.theme-toggle{{
    position:fixed;bottom:20px;right:20px;z-index:1000;
    width:48px;height:48px;border-radius:50%;
    background:var(--card);border:1px solid var(--border);
    cursor:pointer;display:flex;align-items:center;justify-content:center;
    box-shadow:var(--shadow-lg);transition:all 0.2s;font-size:20px
}}
.theme-toggle:hover{{transform:scale(1.1);border-color:var(--accent)}}

.app{{display:flex;height:100%;max-width:1400px;margin:0 auto;background:var(--card);box-shadow:var(--shadow-lg);border-radius:var(--radius-lg);overflow:hidden;border:1px solid var(--border)}}

/* Sidebar */
.sidebar{{width:380px;min-width:380px;display:flex;flex-direction:column;border-right:1px solid var(--border);background:var(--bg2)}}
.sidebar-header{{padding:20px 24px;background:linear-gradient(135deg,var(--card) 0%,var(--card2) 100%);border-bottom:1px solid var(--border)}}
.sidebar-header h1{{font-size:18px;font-weight:700;margin-bottom:6px;letter-spacing:-0.5px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sidebar-header small{{font-size:12px;color:var(--text2)}}

.search-box{{padding:16px 20px;border-bottom:1px solid var(--border);background:var(--bg2)}}
.search-box input{{
    width:100%;padding:12px 16px 12px 44px;
    border:1px solid var(--border);border-radius:var(--radius);
    font-size:14px;background:var(--card) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' fill='none' stroke='%2371717a' stroke-width='2'%3E%3Ccircle cx='8' cy='8' r='6'/%3E%3Cpath d='M13 13l4 4'/%3E%3C/svg%3E") 14px center no-repeat;
    outline:none;transition:all 0.2s;color:var(--text)
}}
.search-box input::placeholder{{color:var(--text3)}}
.search-box input:focus{{border-color:var(--accent);background-color:var(--card2);box-shadow:0 0 0 3px var(--accent-bg)}}

.tabs{{display:flex;gap:4px;padding:8px 16px;border-bottom:1px solid var(--border);background:var(--bg2)}}
.tab{{flex:1;padding:10px 12px;font-size:13px;font-weight:600;text-align:center;color:var(--text2);cursor:pointer;border-radius:8px;transition:all 0.2s}}
.tab:hover{{color:var(--text);background:var(--hover)}}
.tab.active{{color:var(--accent);background:var(--accent-bg)}}

.sidebar-stats{{padding:12px 24px;font-size:12px;color:var(--text3);background:var(--card);font-weight:500;border-bottom:1px solid var(--border)}}

.chat-list{{flex:1;overflow-y:auto;background:var(--bg2)}}
.chat-list::-webkit-scrollbar{{width:6px}}
.chat-list::-webkit-scrollbar-track{{background:transparent}}
.chat-list::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:3px}}
.chat-list::-webkit-scrollbar-thumb:hover{{background:var(--text3)}}
.chat-radio{{display:none}}

.chat-item{{
    display:flex;align-items:center;gap:14px;
    padding:14px 20px;cursor:pointer;
    border-bottom:1px solid var(--border);
    transition:all 0.15s
}}
.chat-item:hover{{background:var(--hover)}}
.chat-radio:checked+.chat-item{{background:var(--accent-bg);border-left:3px solid var(--accent);padding-left:17px}}

.avatar{{
    width:48px;height:48px;border-radius:14px;
    background:linear-gradient(135deg,var(--purple),var(--pink));color:#fff;
    display:flex;align-items:center;justify-content:center;
    font-size:18px;font-weight:700;flex-shrink:0;
    box-shadow:var(--shadow);overflow:hidden
}}
.avatar img{{width:100%;height:100%;object-fit:cover}}
.avatar.sm{{width:36px;height:36px;font-size:14px;border-radius:10px}}
/* Avatar color variants */
.chat-item:nth-child(3n+1) .avatar{{background:linear-gradient(135deg,var(--accent),#059669)}}
.chat-item:nth-child(3n+2) .avatar{{background:linear-gradient(135deg,var(--blue),var(--purple))}}
.chat-item:nth-child(3n) .avatar{{background:linear-gradient(135deg,var(--orange),var(--pink))}}

.chat-info{{flex:1;min-width:0}}
.chat-name{{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)}}
.chat-preview{{font-size:13px;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:4px}}
.preview-sender{{color:var(--accent);font-weight:500}}

.chat-meta{{text-align:right;flex-shrink:0}}
.chat-time{{display:block;font-size:11px;color:var(--text3);font-weight:500}}
.chat-badge{{
    display:inline-flex;align-items:center;justify-content:center;margin-top:8px;
    min-width:24px;height:24px;
    background:linear-gradient(135deg,var(--accent),var(--accent2));color:#000;
    font-size:11px;font-weight:700;padding:0 8px;border-radius:12px
}}

/* Search Results */
.search-results{{flex:1;overflow-y:auto;display:none;background:var(--bg2)}}
.search-results.active{{display:block}}
.search-result{{display:flex;gap:14px;padding:14px 20px;cursor:pointer;border-bottom:1px solid var(--border);transition:all 0.15s}}
.search-result:hover{{background:var(--hover)}}
.result-info{{flex:1;min-width:0}}
.result-chat{{font-size:14px;font-weight:600;color:var(--text)}}
.result-sender{{font-size:12px;color:var(--accent);font-weight:500;margin-top:3px}}
.result-text{{font-size:13px;color:var(--text2);margin-top:6px;line-height:1.5}}
.result-text mark{{background:var(--accent-bg);color:var(--accent2);padding:2px 4px;border-radius:4px;font-weight:600}}

/* Main content */
.main{{flex:1;display:flex;flex-direction:column;background:var(--bg);position:relative}}
.placeholder{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text3);font-size:15px;gap:12px}}
.placeholder::before{{content:'💬';font-size:48px;opacity:0.5}}

.chat-panel{{
    position:absolute;top:0;left:0;right:0;bottom:0;
    display:none;flex-direction:column;background:var(--bg)
}}
.chat-radio:checked~.main .placeholder{{display:none}}
#c0:checked~.main #p0,#c1:checked~.main #p1,#c2:checked~.main #p2,#c3:checked~.main #p3,#c4:checked~.main #p4,
#c5:checked~.main #p5,#c6:checked~.main #p6,#c7:checked~.main #p7,#c8:checked~.main #p8,#c9:checked~.main #p9,
#c10:checked~.main #p10,#c11:checked~.main #p11,#c12:checked~.main #p12,#c13:checked~.main #p13,#c14:checked~.main #p14,
#c15:checked~.main #p15,#c16:checked~.main #p16,#c17:checked~.main #p17,#c18:checked~.main #p18,#c19:checked~.main #p19,
#c20:checked~.main #p20,#c21:checked~.main #p21,#c22:checked~.main #p22,#c23:checked~.main #p23,#c24:checked~.main #p24,
#c25:checked~.main #p25,#c26:checked~.main #p26,#c27:checked~.main #p27,#c28:checked~.main #p28,#c29:checked~.main #p29,
#c30:checked~.main #p30,#c31:checked~.main #p31,#c32:checked~.main #p32,#c33:checked~.main #p33,#c34:checked~.main #p34,
#c35:checked~.main #p35,#c36:checked~.main #p36,#c37:checked~.main #p37,#c38:checked~.main #p38,#c39:checked~.main #p39,
#c40:checked~.main #p40,#c41:checked~.main #p41,#c42:checked~.main #p42,#c43:checked~.main #p43,#c44:checked~.main #p44,
#c45:checked~.main #p45,#c46:checked~.main #p46,#c47:checked~.main #p47,#c48:checked~.main #p48,#c49:checked~.main #p49{{display:flex}}
/* Extended for more chats */
#c50:checked~.main #p50,#c51:checked~.main #p51,#c52:checked~.main #p52,#c53:checked~.main #p53,#c54:checked~.main #p54,
#c55:checked~.main #p55,#c56:checked~.main #p56,#c57:checked~.main #p57,#c58:checked~.main #p58,#c59:checked~.main #p59,
#c60:checked~.main #p60,#c61:checked~.main #p61,#c62:checked~.main #p62,#c63:checked~.main #p63,#c64:checked~.main #p64,
#c65:checked~.main #p65,#c66:checked~.main #p66,#c67:checked~.main #p67,#c68:checked~.main #p68,#c69:checked~.main #p69,
#c70:checked~.main #p70,#c71:checked~.main #p71,#c72:checked~.main #p72,#c73:checked~.main #p73,#c74:checked~.main #p74,
#c75:checked~.main #p75,#c76:checked~.main #p76,#c77:checked~.main #p77,#c78:checked~.main #p78,#c79:checked~.main #p79,
#c80:checked~.main #p80,#c81:checked~.main #p81,#c82:checked~.main #p82,#c83:checked~.main #p83,#c84:checked~.main #p84,
#c85:checked~.main #p85,#c86:checked~.main #p86,#c87:checked~.main #p87,#c88:checked~.main #p88,#c89:checked~.main #p89,
#c90:checked~.main #p90,#c91:checked~.main #p91,#c92:checked~.main #p92,#c93:checked~.main #p93,#c94:checked~.main #p94,
#c95:checked~.main #p95,#c96:checked~.main #p96,#c97:checked~.main #p97,#c98:checked~.main #p98,#c99:checked~.main #p99{{display:flex}}
/* 100-199 */
#c100:checked~.main #p100,#c101:checked~.main #p101,#c102:checked~.main #p102,#c103:checked~.main #p103,#c104:checked~.main #p104,
#c105:checked~.main #p105,#c106:checked~.main #p106,#c107:checked~.main #p107,#c108:checked~.main #p108,#c109:checked~.main #p109,
#c110:checked~.main #p110,#c111:checked~.main #p111,#c112:checked~.main #p112,#c113:checked~.main #p113,#c114:checked~.main #p114,
#c115:checked~.main #p115,#c116:checked~.main #p116,#c117:checked~.main #p117,#c118:checked~.main #p118,#c119:checked~.main #p119,
#c120:checked~.main #p120,#c121:checked~.main #p121,#c122:checked~.main #p122,#c123:checked~.main #p123,#c124:checked~.main #p124,
#c125:checked~.main #p125,#c126:checked~.main #p126,#c127:checked~.main #p127,#c128:checked~.main #p128,#c129:checked~.main #p129,
#c130:checked~.main #p130,#c131:checked~.main #p131,#c132:checked~.main #p132,#c133:checked~.main #p133,#c134:checked~.main #p134,
#c135:checked~.main #p135,#c136:checked~.main #p136,#c137:checked~.main #p137,#c138:checked~.main #p138,#c139:checked~.main #p139,
#c140:checked~.main #p140,#c141:checked~.main #p141,#c142:checked~.main #p142,#c143:checked~.main #p143,#c144:checked~.main #p144,
#c145:checked~.main #p145,#c146:checked~.main #p146,#c147:checked~.main #p147,#c148:checked~.main #p148,#c149:checked~.main #p149,
#c150:checked~.main #p150,#c151:checked~.main #p151,#c152:checked~.main #p152,#c153:checked~.main #p153,#c154:checked~.main #p154,
#c155:checked~.main #p155,#c156:checked~.main #p156,#c157:checked~.main #p157,#c158:checked~.main #p158,#c159:checked~.main #p159,
#c160:checked~.main #p160,#c161:checked~.main #p161,#c162:checked~.main #p162,#c163:checked~.main #p163,#c164:checked~.main #p164,
#c165:checked~.main #p165,#c166:checked~.main #p166,#c167:checked~.main #p167,#c168:checked~.main #p168,#c169:checked~.main #p169,
#c170:checked~.main #p170,#c171:checked~.main #p171,#c172:checked~.main #p172,#c173:checked~.main #p173,#c174:checked~.main #p174,
#c175:checked~.main #p175,#c176:checked~.main #p176,#c177:checked~.main #p177,#c178:checked~.main #p178,#c179:checked~.main #p179,
#c180:checked~.main #p180,#c181:checked~.main #p181,#c182:checked~.main #p182,#c183:checked~.main #p183,#c184:checked~.main #p184,
#c185:checked~.main #p185,#c186:checked~.main #p186,#c187:checked~.main #p187,#c188:checked~.main #p188,#c189:checked~.main #p189,
#c190:checked~.main #p190,#c191:checked~.main #p191,#c192:checked~.main #p192,#c193:checked~.main #p193,#c194:checked~.main #p194,
#c195:checked~.main #p195,#c196:checked~.main #p196,#c197:checked~.main #p197,#c198:checked~.main #p198,#c199:checked~.main #p199{{display:flex}}
/* 200-299 */
#c200:checked~.main #p200,#c201:checked~.main #p201,#c202:checked~.main #p202,#c203:checked~.main #p203,#c204:checked~.main #p204,
#c205:checked~.main #p205,#c206:checked~.main #p206,#c207:checked~.main #p207,#c208:checked~.main #p208,#c209:checked~.main #p209,
#c210:checked~.main #p210,#c211:checked~.main #p211,#c212:checked~.main #p212,#c213:checked~.main #p213,#c214:checked~.main #p214,
#c215:checked~.main #p215,#c216:checked~.main #p216,#c217:checked~.main #p217,#c218:checked~.main #p218,#c219:checked~.main #p219,
#c220:checked~.main #p220,#c221:checked~.main #p221,#c222:checked~.main #p222,#c223:checked~.main #p223,#c224:checked~.main #p224,
#c225:checked~.main #p225,#c226:checked~.main #p226,#c227:checked~.main #p227,#c228:checked~.main #p228,#c229:checked~.main #p229,
#c230:checked~.main #p230,#c231:checked~.main #p231,#c232:checked~.main #p232,#c233:checked~.main #p233,#c234:checked~.main #p234,
#c235:checked~.main #p235,#c236:checked~.main #p236,#c237:checked~.main #p237,#c238:checked~.main #p238,#c239:checked~.main #p239,
#c240:checked~.main #p240,#c241:checked~.main #p241,#c242:checked~.main #p242,#c243:checked~.main #p243,#c244:checked~.main #p244,
#c245:checked~.main #p245,#c246:checked~.main #p246,#c247:checked~.main #p247,#c248:checked~.main #p248,#c249:checked~.main #p249,
#c250:checked~.main #p250,#c251:checked~.main #p251,#c252:checked~.main #p252,#c253:checked~.main #p253,#c254:checked~.main #p254,
#c255:checked~.main #p255,#c256:checked~.main #p256,#c257:checked~.main #p257,#c258:checked~.main #p258,#c259:checked~.main #p259,
#c260:checked~.main #p260,#c261:checked~.main #p261,#c262:checked~.main #p262,#c263:checked~.main #p263,#c264:checked~.main #p264,
#c265:checked~.main #p265,#c266:checked~.main #p266,#c267:checked~.main #p267,#c268:checked~.main #p268,#c269:checked~.main #p269,
#c270:checked~.main #p270,#c271:checked~.main #p271,#c272:checked~.main #p272,#c273:checked~.main #p273,#c274:checked~.main #p274,
#c275:checked~.main #p275,#c276:checked~.main #p276,#c277:checked~.main #p277,#c278:checked~.main #p278,#c279:checked~.main #p279,
#c280:checked~.main #p280,#c281:checked~.main #p281,#c282:checked~.main #p282,#c283:checked~.main #p283,#c284:checked~.main #p284,
#c285:checked~.main #p285,#c286:checked~.main #p286,#c287:checked~.main #p287,#c288:checked~.main #p288,#c289:checked~.main #p289,
#c290:checked~.main #p290,#c291:checked~.main #p291,#c292:checked~.main #p292,#c293:checked~.main #p293,#c294:checked~.main #p294,
#c295:checked~.main #p295,#c296:checked~.main #p296,#c297:checked~.main #p297,#c298:checked~.main #p298,#c299:checked~.main #p299{{display:flex}}
/* 300-399 */
#c300:checked~.main #p300,#c301:checked~.main #p301,#c302:checked~.main #p302,#c303:checked~.main #p303,#c304:checked~.main #p304,
#c305:checked~.main #p305,#c306:checked~.main #p306,#c307:checked~.main #p307,#c308:checked~.main #p308,#c309:checked~.main #p309,
#c310:checked~.main #p310,#c311:checked~.main #p311,#c312:checked~.main #p312,#c313:checked~.main #p313,#c314:checked~.main #p314,
#c315:checked~.main #p315,#c316:checked~.main #p316,#c317:checked~.main #p317,#c318:checked~.main #p318,#c319:checked~.main #p319,
#c320:checked~.main #p320,#c321:checked~.main #p321,#c322:checked~.main #p322,#c323:checked~.main #p323,#c324:checked~.main #p324,
#c325:checked~.main #p325,#c326:checked~.main #p326,#c327:checked~.main #p327,#c328:checked~.main #p328,#c329:checked~.main #p329,
#c330:checked~.main #p330,#c331:checked~.main #p331,#c332:checked~.main #p332,#c333:checked~.main #p333,#c334:checked~.main #p334,
#c335:checked~.main #p335,#c336:checked~.main #p336,#c337:checked~.main #p337,#c338:checked~.main #p338,#c339:checked~.main #p339,
#c340:checked~.main #p340,#c341:checked~.main #p341,#c342:checked~.main #p342,#c343:checked~.main #p343,#c344:checked~.main #p344,
#c345:checked~.main #p345,#c346:checked~.main #p346,#c347:checked~.main #p347,#c348:checked~.main #p348,#c349:checked~.main #p349,
#c350:checked~.main #p350,#c351:checked~.main #p351,#c352:checked~.main #p352,#c353:checked~.main #p353,#c354:checked~.main #p354,
#c355:checked~.main #p355,#c356:checked~.main #p356,#c357:checked~.main #p357,#c358:checked~.main #p358,#c359:checked~.main #p359,
#c360:checked~.main #p360,#c361:checked~.main #p361,#c362:checked~.main #p362,#c363:checked~.main #p363,#c364:checked~.main #p364,
#c365:checked~.main #p365,#c366:checked~.main #p366,#c367:checked~.main #p367,#c368:checked~.main #p368,#c369:checked~.main #p369,
#c370:checked~.main #p370,#c371:checked~.main #p371,#c372:checked~.main #p372,#c373:checked~.main #p373,#c374:checked~.main #p374,
#c375:checked~.main #p375,#c376:checked~.main #p376,#c377:checked~.main #p377,#c378:checked~.main #p378,#c379:checked~.main #p379,
#c380:checked~.main #p380,#c381:checked~.main #p381,#c382:checked~.main #p382,#c383:checked~.main #p383,#c384:checked~.main #p384,
#c385:checked~.main #p385,#c386:checked~.main #p386,#c387:checked~.main #p387,#c388:checked~.main #p388,#c389:checked~.main #p389,
#c390:checked~.main #p390,#c391:checked~.main #p391,#c392:checked~.main #p392,#c393:checked~.main #p393,#c394:checked~.main #p394,
#c395:checked~.main #p395,#c396:checked~.main #p396,#c397:checked~.main #p397,#c398:checked~.main #p398,#c399:checked~.main #p399{{display:flex}}

.panel-header{{
    display:flex;align-items:center;gap:14px;
    padding:16px 20px;background:var(--card);
    border-bottom:1px solid var(--border);
    box-shadow:var(--shadow)
}}
.back-btn{{
    display:none;width:40px;height:40px;
    border:none;background:var(--hover);border-radius:var(--radius);
    font-size:20px;cursor:pointer;text-align:center;line-height:40px;
    text-decoration:none;color:var(--text);transition:all 0.2s
}}
.back-btn:hover{{background:var(--accent-bg);color:var(--accent)}}
.header-info{{flex:1;min-width:0}}
.header-name{{font-size:16px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-0.3px}}
.header-sub{{font-size:12px;color:var(--text3);margin-top:3px}}

.search-toggle{{
    width:44px;height:44px;border:none;
    background:var(--hover);cursor:pointer;
    border-radius:var(--radius);color:var(--text2);
    display:flex;align-items:center;justify-content:center;
    transition:all 0.2s
}}
.search-toggle:hover{{background:var(--accent-bg);color:var(--accent)}}

.panel-search{{
    display:none;align-items:center;gap:10px;
    padding:12px 20px;background:var(--card2);
    border-bottom:1px solid var(--border)
}}
.panel-search.active{{display:flex}}
.panel-search input{{
    flex:1;padding:10px 14px;border:1px solid var(--border);
    border-radius:var(--radius);font-size:14px;outline:none;transition:all 0.2s;
    background:var(--card);color:var(--text)
}}
.panel-search input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-bg)}}
.search-info{{font-size:12px;color:var(--text2);min-width:60px;text-align:center;font-weight:600}}
.panel-search button{{
    width:36px;height:36px;border:1px solid var(--border);
    background:var(--card);border-radius:8px;cursor:pointer;font-size:14px;
    display:flex;align-items:center;justify-content:center;transition:all 0.2s;color:var(--text2)
}}
.panel-search button:hover{{background:var(--hover);border-color:var(--accent);color:var(--accent)}}

/* Pinned */
.pinned{{margin:14px 20px;background:var(--card);border-radius:var(--radius);border:1px solid var(--border)}}
.pinned summary{{padding:14px;cursor:pointer;font-size:13px;color:var(--accent);font-weight:600;list-style:none}}
.pinned summary::-webkit-details-marker{{display:none}}
.pinned-list{{padding:12px;max-height:200px;overflow-y:auto;border-top:1px solid var(--border)}}

/* Messages */
.messages{{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:8px;position:relative}}
.messages::-webkit-scrollbar{{width:6px}}
.messages::-webkit-scrollbar-track{{background:transparent}}
.messages::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:3px}}
.date-sep{{text-align:center;margin:20px 0;position:sticky;top:0;z-index:3;padding:8px 0;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}}
.date-sep span{{background:var(--card2);padding:8px 16px;border-radius:20px;font-size:12px;font-weight:600;color:var(--text2);box-shadow:0 2px 8px rgba(0,0,0,0.1)}}

.msg{{
    max-width:70%;padding:12px 16px;border-radius:18px;
    font-size:14px;line-height:1.6;background:var(--msg-in);
    box-shadow:var(--shadow);word-wrap:break-word
}}
.msg.out{{background:var(--msg-out);align-self:flex-end;border-bottom-right-radius:6px}}
.msg:not(.out){{align-self:flex-start;border-bottom-left-radius:6px}}
.msg.hl{{background:var(--hl)!important;box-shadow:0 0 0 2px var(--accent)}}

.msg .sender{{font-size:12px;font-weight:700;color:var(--accent);margin-bottom:5px}}
.msg .text{{white-space:pre-wrap}}
.msg .tm{{font-size:11px;color:var(--text3);text-align:right;margin-top:6px}}

.msg .quote{{
    border-left:3px solid var(--purple);padding:8px 12px;margin:8px 0;
    background:rgba(139,92,246,0.1);border-radius:0 10px 10px 0;font-size:13px
}}
.msg .quote b{{color:var(--purple)}}

.msg .file{{
    display:flex;gap:10px;align-items:center;
    background:var(--card2);padding:10px 12px;
    border-radius:10px;margin-top:8px
}}
.msg .file a{{color:var(--accent);text-decoration:none;font-size:13px;font-weight:600}}
.msg .file a:hover{{text-decoration:underline}}

/* Mobile */
@media(max-width:768px){{
    .app{{flex-direction:column;height:100vh}}
    .sidebar{{width:100%;min-width:100%;height:100%;position:absolute;top:0;left:0;z-index:10;background:var(--bg2)}}
    .sidebar.hidden{{display:none}}
    .main{{position:absolute;top:0;left:0;width:100%;height:100%;display:none;z-index:20;background:var(--bg)}}
    .main.active{{display:flex}}
    .chat-panel{{display:none!important}}
    .chat-panel.mobile-active{{display:flex!important}}
    .back-btn{{display:flex}}
    .msg{{max-width:85%}}
    .messages{{padding:10px}}
    .panel-header{{position:sticky;top:0;z-index:5}}
    .search-box input{{font-size:16px}}
    .theme-toggle{{bottom:80px;right:16px;width:44px;height:44px}}
}}
</style>
</head>
<body class="light">

<button class="theme-toggle" onclick="toggleTheme()" title="Сменить тему">☀️</button>

<div class="app">
    {sidebar_items}

    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h1>📦 VK Teams Export</h1>
            <small>📅 {export_date} · 💬 {len(chats)} чатов · 📨 {total_messages} сообщений</small>
        </div>
        <div class="search-box">
            <input type="text" id="globalSearch" placeholder="Поиск..." oninput="globalSearchFn()">
        </div>
        <div class="tabs">
            <div class="tab active" onclick="switchTab('chats')">Контакты и группы</div>
            <div class="tab" onclick="switchTab('messages')">Сообщения</div>
        </div>
        <div class="sidebar-stats" id="stats">Контактов и групп: {len(chats)}</div>
        <div class="chat-list" id="chatList"></div>
        <div class="search-results" id="searchResults"></div>
    </div>

    <div class="main" id="main">
        <div class="placeholder">👈 Выберите чат</div>
        {content_panels}
    </div>
</div>

<script>
// Theme toggle (light is default)
function toggleTheme(){{
    var body=document.body;
    var btn=document.querySelector('.theme-toggle');
    body.classList.toggle('light');
    var isLight=body.classList.contains('light');
    btn.textContent=isLight?'☀️':'🌙';
    localStorage.setItem('theme',isLight?'light':'dark');
}}
// Restore saved theme (light is default)
(function(){{
    var saved=localStorage.getItem('theme');
    if(saved==='dark'){{
        document.body.classList.remove('light');
        document.querySelector('.theme-toggle').textContent='🌙';
    }}
}})();

(function(){{
    var chatItems=document.querySelectorAll('.chat-item');
    var chatList=document.getElementById('chatList');
    var searchResults=document.getElementById('searchResults');
    var stats=document.getElementById('stats');
    var tabs=document.querySelectorAll('.tab');
    var currentTab='chats';
    var isMobile=window.innerWidth<=768;

    // Scroll chat to bottom (latest messages)
    function scrollChatToBottom(panelId){{
        setTimeout(function(){{
            var panel=document.getElementById(panelId);
            if(!panel)return;
            var messagesContainer=panel.querySelector('.messages');
            if(messagesContainer){{
                messagesContainer.scrollTop=messagesContainer.scrollHeight;
            }}
        }},50);
    }}

    // Mobile: open chat panel
    function openChatMobile(idx){{
        if(!isMobile)return;
        // Hide all panels, show selected one
        document.querySelectorAll('.chat-panel').forEach(function(p){{p.classList.remove('mobile-active')}});
        var panel=document.getElementById('p'+idx);
        if(panel){{
            panel.classList.add('mobile-active');
            scrollChatToBottom('p'+idx);
        }}
        document.getElementById('sidebar').classList.add('hidden');
        document.getElementById('main').classList.add('active');
    }}

    // Move chat items to chat-list
    chatItems.forEach(function(item){{chatList.appendChild(item)}});

    // Scroll first chat to bottom on page load
    if(!isMobile){{
        scrollChatToBottom('p0');
    }}

    // Index messages for search
    var msgIndex=[];
    document.querySelectorAll('.chat-panel').forEach(function(panel,ci){{
        var name=panel.querySelector('.header-name').textContent;
        panel.querySelectorAll('.msg').forEach(function(m,mi){{
            var t=m.querySelector('.text');
            var s=m.querySelector('.sender');
            if(t&&t.textContent)msgIndex.push({{ci:ci,mi:mi,name:name,text:t.textContent,sender:s?s.textContent:''}});
        }});
    }});

    window.switchTab=function(tab){{
        currentTab=tab;
        tabs.forEach(function(t,i){{t.classList.toggle('active',i===(tab==='chats'?0:1))}});
        globalSearchFn();
    }};

    var st;
    window.globalSearchFn=function(){{
        clearTimeout(st);st=setTimeout(doSearch,150);
    }};

    function doSearch(){{
        var q=document.getElementById('globalSearch').value.toLowerCase().trim();
        if(currentTab==='chats'){{
            chatList.style.display='';
            searchResults.classList.remove('active');
            var vis=0;
            chatItems.forEach(function(it){{
                var n=it.querySelector('.chat-name').textContent.toLowerCase();
                var show=!q||n.indexOf(q)>=0;
                it.style.display=show?'':'none';
                if(show)vis++;
            }});
            stats.textContent='Контактов и групп: '+vis;
        }}else{{
            chatList.style.display='none';
            searchResults.classList.add('active');
            if(q.length<2){{
                searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--text2)">Введите минимум 2 символа</div>';
                stats.textContent='Сообщений: 0';
                return;
            }}
            var res=[];
            for(var i=0;i<msgIndex.length;i++){{
                if(msgIndex[i].text.toLowerCase().indexOf(q)>=0)res.push(msgIndex[i]);
            }}
            stats.textContent='Сообщений: '+res.length;
            if(!res.length){{
                searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--text2)">Ничего не найдено</div>';
                return;
            }}
            var h='';
            res.forEach(function(r){{
                var snip=r.text.substring(0,150);
                var esc=q.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&');
                var hl=snip.replace(new RegExp('('+esc+')','gi'),'<mark>$1</mark>');
                h+='<div class="search-result" onclick="openFromSearch('+r.ci+','+r.mi+')">'+
                    '<div class="avatar sm">'+(r.name[0]||'?').toUpperCase()+'</div>'+
                    '<div class="result-info"><div class="result-chat">'+r.name+'</div>'+
                    (r.sender?'<div class="result-sender">'+r.sender+'</div>':'')+
                    '<div class="result-text">'+hl+'</div></div></div>';
            }});
            searchResults.innerHTML=h;
        }}
    }}

    window.openFromSearch=function(ci,mi){{
        var radio=document.getElementById('c'+ci);
        if(radio)radio.checked=true;
        if(isMobile){{
            openChatMobile(ci);
        }}
        // Увеличенный таймаут для отрисовки
        setTimeout(function(){{
            var panel=document.getElementById('p'+ci);
            if(!panel)return;
            var msgs=panel.querySelectorAll('.msg');
            var target=msgs[mi];
            if(target){{
                // Скроллим контейнер сообщений
                var container=panel.querySelector('.messages');
                if(container){{
                    target.scrollIntoView({{behavior:'smooth',block:'center'}});
                }}
                target.classList.add('hl');
                setTimeout(function(){{target.classList.remove('hl')}},3000);
            }}
        }},200);
    }};

    chatItems.forEach(function(item){{
        item.addEventListener('click',function(){{
            var idx=item.getAttribute('data-idx');
            if(isMobile){{
                openChatMobile(idx);
            }}else{{
                // Desktop: scroll to bottom when chat is opened
                scrollChatToBottom('p'+idx);
            }}
        }});
    }});

    // Search in chat
    window.toggleSearch=function(btn){{
        var bar=btn.closest('.chat-panel').querySelector('.panel-search');
        bar.classList.toggle('active');
        if(bar.classList.contains('active'))bar.querySelector('input').focus();
    }};

    window.closeSearch=function(btn){{
        var panel=btn.closest('.chat-panel');
        panel.querySelector('.panel-search').classList.remove('active');
        panel.querySelector('.panel-search input').value='';
        panel.querySelectorAll('.msg.hl').forEach(function(m){{m.classList.remove('hl')}});
        panel._matches=null;
    }};

    window.searchInChat=function(input,e){{
        var panel=input.closest('.chat-panel');
        var q=input.value.toLowerCase().trim();

        // Enter - переход к следующему
        if(e&&e.key==='Enter'){{
            e.preventDefault();
            if(panel._matches&&panel._matches.length){{
                navInPanel(panel,e.shiftKey?-1:1);
            }}
            return;
        }}

        var msgs=panel.querySelectorAll('.msg');
        var matches=[];
        msgs.forEach(function(m){{
            m.classList.remove('hl');
            var t=m.querySelector('.text');
            if(t&&q.length>=2&&t.textContent.toLowerCase().indexOf(q)>=0){{
                m.classList.add('hl');
                matches.push(m);
            }}
        }});
        var info=panel.querySelector('.search-info');
        info.textContent=matches.length?matches.length+' найдено':'';
        panel._matches=matches;
        panel._idx=-1;
        // Автоскролл к первому результату
        if(matches.length){{
            panel._idx=0;
            matches[0].scrollIntoView({{behavior:'smooth',block:'center'}});
            info.textContent='1/'+matches.length;
        }}
    }};

    function navInPanel(panel,dir){{
        var m=panel._matches;
        if(!m||!m.length)return;
        if(dir>0)panel._idx=(panel._idx+1)%m.length;
        else panel._idx=panel._idx<=0?m.length-1:panel._idx-1;
        m[panel._idx].scrollIntoView({{behavior:'smooth',block:'center'}});
        panel.querySelector('.search-info').textContent=(panel._idx+1)+'/'+m.length;
    }}

    window.navSearch=function(btn,dir){{
        var panel=btn.closest('.chat-panel');
        navInPanel(panel,dir);
    }};

    // Back button for mobile
    document.querySelectorAll('.back-btn').forEach(function(btn){{
        btn.addEventListener('click',function(e){{
            e.preventDefault();
            // Hide all mobile-active panels
            document.querySelectorAll('.chat-panel').forEach(function(p){{p.classList.remove('mobile-active')}});
            document.getElementById('sidebar').classList.remove('hidden');
            document.getElementById('main').classList.remove('active');
        }});
    }});

    // Handle resize
    window.addEventListener('resize',function(){{
        isMobile=window.innerWidth<=768;
        if(!isMobile){{
            document.getElementById('sidebar').classList.remove('hidden');
            document.getElementById('main').classList.remove('active');
            document.querySelectorAll('.chat-panel').forEach(function(p){{p.classList.remove('mobile-active')}});
        }}
    }});
}})();
</script>
</body>
</html>'''


def render_message(msg: dict, pinned: bool = False, chat_members: dict = None, chat_sn: str = "", is_personal: bool = False, names: dict = None, files_url_map: dict = None) -> str:
    """Рендер одного сообщения"""
    names = names or {}
    files_url_map = files_url_map or {}
    is_outgoing = msg.get("outgoing", False)

    sender_sn = (
        msg.get("chat", {}).get("sender") or
        msg.get("senderSn") or
        msg.get("sn") or
        msg.get("sender") or
        ""
    )

    if is_personal:
        sender_name = ""
    else:
        # Приоритет: словарь имён > chat_members > senderNick > friendly > sn
        sender_name = names.get(sender_sn) or ""
        if not sender_name and chat_members and sender_sn:
            member_info = chat_members.get(sender_sn, {})
            sender_name = member_info.get("friendly") or member_info.get("name") or ""
        if not sender_name:
            sender_name = msg.get("senderNick") or msg.get("friendly") or ""
        if not sender_name and sender_sn:
            sender_name = sender_sn

    sender = escape(sender_name or "")
    timestamp = msg.get("time", 0)
    time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M") if timestamp else ""

    content = ""
    parts = msg.get("parts", [])

    if parts:
        for part in parts:
            mt = part.get("mediaType")
            if mt == "text":
                cap = part.get("captionedContent") or {}
                text = cap.get("caption") or part.get("text", "")
                if text:
                    content += f'<div class="text">{escape(text)}</div>'
            elif mt == "quote":
                qs = escape(part.get("sn", ""))
                qt = escape(str(part.get("text", ""))[:200])
                content += f'<div class="quote"><b>↩ {qs}</b><br>{qt}</div>'
            elif mt == "forward":
                fs = escape(part.get("sn", ""))
                cap = part.get("captionedContent") or {}
                ft = escape(str(cap.get("caption") or part.get("text", ""))[:200])
                content += f'<div class="quote" style="border-color:#9c27b0"><b style="color:#9c27b0">⤵ {fs}</b><br>{ft}</div>'
    elif msg.get("text"):
        content += f'<div class="text">{escape(msg["text"])}</div>'

    for file in msg.get("filesharing", []):
        name = escape(file.get("name", "файл"))
        orig_url = file.get("original_url", "")
        url = escape(files_url_map.get(orig_url, orig_url) if orig_url else "#")
        size = format_size(file.get("size"))
        icon = get_file_icon(file.get("mime", ""))
        content += f'<div class="file">{icon} <a href="{url}" target="_blank">{name}</a> <small>{size}</small></div>'

    cls = "msg out" if is_outgoing else "msg"
    sender_html = f'<div class="sender">{sender}</div>' if sender and not is_outgoing else ""

    return f'<div class="{cls}">{sender_html}{content}<div class="tm">{time_str}</div></div>'


def format_size(size) -> str:
    if not size:
        return ""
    try:
        size = int(size)
    except:
        return ""
    if size < 1024:
        return f"{size} Б"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} КБ"
    return f"{size / (1024 * 1024):.1f} МБ"


def get_file_icon(mime: str) -> str:
    if not mime:
        return "📎"
    if mime.startswith("image/"):
        return "🖼"
    if mime.startswith("video/"):
        return "🎬"
    if mime.startswith("audio/"):
        return "🎵"
    if "pdf" in mime:
        return "📄"
    if "zip" in mime or "rar" in mime:
        return "📦"
    return "📎"
