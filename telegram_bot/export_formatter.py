"""
Форматирование экспорта VK Teams в различные форматы
"""

import json
from datetime import datetime
from html import escape


def format_as_json(data: dict) -> str:
    """Форматирование в JSON"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_as_html(data: dict) -> str:
    """Форматирование в HTML - мини-мессенджер"""

    chats = data.get("chats", [])
    total_messages = sum(len(c.get("messages", [])) for c in chats)
    export_date = data.get("export_date", datetime.now().isoformat())[:10]

    # Генерируем список чатов для сайдбара
    chat_list_html = ""
    chats_content_html = ""

    for idx, chat in enumerate(chats):
        chat_sn = chat.get("chat_sn", "")
        chat_name = escape(chat.get("chat_name", chat_sn or "Чат"))
        messages = chat.get("messages", [])
        is_personal = "@chat.agent" not in chat_sn
        msg_count = len(messages)

        # Последнее сообщение для превью
        last_msg = messages[-1] if messages else {}
        last_text = ""
        if last_msg:
            parts = last_msg.get("parts", [])
            for p in parts:
                if p.get("mediaType") == "text":
                    last_text = p.get("text", "")[:50]
                    break
            if not last_text:
                last_text = last_msg.get("text", "")[:50]
        last_text = escape(last_text) if last_text else "..."

        # Время последнего сообщения
        last_time = ""
        if last_msg.get("time"):
            last_time = datetime.fromtimestamp(last_msg["time"]).strftime("%d.%m")

        # Элемент списка чатов
        chat_list_html += f'''
        <div class="chat-item" data-chat-id="{idx}" onclick="selectChat({idx})">
            <div class="chat-avatar">{chat_name[0].upper()}</div>
            <div class="chat-item-info">
                <div class="chat-item-header">
                    <span class="chat-item-name">{chat_name[:25]}{"..." if len(chat_name) > 25 else ""}</span>
                    <span class="chat-item-time">{last_time}</span>
                </div>
                <div class="chat-item-preview">{last_text}</div>
            </div>
            <div class="chat-item-badge">{msg_count}</div>
        </div>
        '''

        # Собираем участников
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
                chat_members[sender_sn] = {
                    "friendly": msg.get("senderNick") or msg.get("friendly") or "",
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
                    messages_html += f'<div class="date-separator"><span>{msg_date}</span></div>'

            messages_html += render_message(msg, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal)

        # Закреплённые
        pinned = chat.get("pinned_messages", [])
        pinned_html = ""
        if pinned:
            pinned_html = f'''
            <div class="pinned-bar" onclick="togglePinned({idx})">
                📌 Закреплённых: {len(pinned)} <span class="expand-icon">▼</span>
            </div>
            <div class="pinned-messages" id="pinned-{idx}" style="display:none;">
                {"".join(render_message(m, pinned=True, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal) for m in pinned)}
            </div>
            '''

        # Контент чата
        chats_content_html += f'''
        <div class="chat-content" id="chat-content-{idx}" style="display:none;">
            <div class="chat-header-bar">
                <button class="back-btn" onclick="showChatList()">←</button>
                <div class="chat-header-info">
                    <div class="chat-header-name">{chat_name}</div>
                    <div class="chat-header-meta">{msg_count} сообщений</div>
                </div>
                <button class="search-chat-btn" onclick="toggleChatSearch({idx})">🔍</button>
            </div>
            <div class="chat-search-bar" id="chat-search-{idx}" style="display:none;">
                <input type="text" placeholder="Поиск в этом чате..." onkeyup="searchInChat({idx}, this.value)">
                <span class="search-results-count" id="search-count-{idx}"></span>
            </div>
            {pinned_html}
            <div class="messages-container" id="messages-{idx}">
                {messages_html}
            </div>
        </div>
        '''

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>VK Teams Export</title>
    <style>
        :root {{
            --bg: #f0f2f5;
            --sidebar-bg: #ffffff;
            --chat-bg: #e5ddd5;
            --card: #ffffff;
            --text: #1a1a1a;
            --text-secondary: #667781;
            --accent: #00a884;
            --accent-light: #d9fdd3;
            --border: #e9edef;
            --incoming: #ffffff;
            --outgoing: #d9fdd3;
            --hover: #f5f6f6;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #111b21;
                --sidebar-bg: #111b21;
                --chat-bg: #0b141a;
                --card: #202c33;
                --text: #e9edef;
                --text-secondary: #8696a0;
                --accent: #00a884;
                --accent-light: #005c4b;
                --border: #222d34;
                --incoming: #202c33;
                --outgoing: #005c4b;
                --hover: #2a3942;
            }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            overflow: hidden;
        }}
        .app {{
            display: flex;
            height: 100vh;
            max-width: 1600px;
            margin: 0 auto;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}

        /* Sidebar */
        .sidebar {{
            width: 400px;
            background: var(--sidebar-bg);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }}
        .sidebar-header {{
            padding: 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
        }}
        .sidebar-header h1 {{
            font-size: 18px;
            margin-bottom: 5px;
        }}
        .sidebar-meta {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        .global-search {{
            padding: 10px 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
        }}
        .global-search input {{
            width: 100%;
            padding: 10px 15px;
            border: none;
            border-radius: 8px;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
        }}
        .global-search input:focus {{ outline: 2px solid var(--accent); }}
        .search-mode {{
            display: flex;
            gap: 10px;
            margin-top: 8px;
            font-size: 12px;
        }}
        .search-mode label {{
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
            color: var(--text-secondary);
            touch-action: manipulation;
            -webkit-user-select: none;
            user-select: none;
        }}
        .search-mode input[type="radio"] {{ accent-color: var(--accent); }}
        .chat-list {{
            flex: 1;
            overflow-y: auto;
        }}
        .chat-item {{
            display: flex;
            align-items: center;
            padding: 12px 15px;
            cursor: pointer;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
            touch-action: manipulation;
            -webkit-user-select: none;
            user-select: none;
        }}
        .chat-item:hover {{ background: var(--hover); }}
        .chat-item.active {{ background: var(--hover); }}
        .chat-item.hidden {{ display: none; }}
        .chat-avatar {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--accent);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            font-weight: 500;
            margin-right: 12px;
            flex-shrink: 0;
        }}
        .chat-item-info {{
            flex: 1;
            min-width: 0;
        }}
        .chat-item-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 3px;
        }}
        .chat-item-name {{
            font-weight: 500;
            font-size: 15px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .chat-item-time {{
            font-size: 12px;
            color: var(--text-secondary);
            flex-shrink: 0;
            margin-left: 8px;
        }}
        .chat-item-preview {{
            font-size: 13px;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .chat-item-badge {{
            background: var(--text-secondary);
            color: white;
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 10px;
            margin-left: 8px;
        }}

        /* Chat content */
        .chat-area {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--chat-bg);
            min-width: 0;
        }}
        .chat-placeholder {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-secondary);
            font-size: 16px;
        }}
        .chat-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }}
        .chat-header-bar {{
            display: flex;
            align-items: center;
            padding: 10px 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
        }}
        .back-btn {{
            display: none;
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            padding: 5px 10px;
            margin-right: 10px;
            color: var(--text);
            touch-action: manipulation;
        }}
        .chat-header-info {{ flex: 1; }}
        .chat-header-name {{
            font-weight: 600;
            font-size: 16px;
        }}
        .chat-header-meta {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        .search-chat-btn {{
            background: none;
            border: none;
            font-size: 18px;
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            touch-action: manipulation;
        }}
        .search-chat-btn:hover {{ background: var(--hover); }}
        .chat-search-bar {{
            padding: 10px 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .chat-search-bar input {{
            flex: 1;
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            background: var(--bg);
            color: var(--text);
        }}
        .search-results-count {{
            font-size: 12px;
            color: var(--text-secondary);
        }}
        .pinned-bar {{
            padding: 10px 15px;
            background: #fff3cd;
            color: #856404;
            font-size: 13px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            touch-action: manipulation;
        }}
        @media (prefers-color-scheme: dark) {{
            .pinned-bar {{ background: #3d3200; color: #ffc107; }}
        }}
        .pinned-messages {{
            background: var(--card);
            border-bottom: 1px solid var(--border);
            max-height: 200px;
            overflow-y: auto;
        }}
        .messages-container {{
            flex: 1;
            overflow-y: auto;
            padding: 10px 60px;
            display: flex;
            flex-direction: column;
        }}
        .date-separator {{
            text-align: center;
            margin: 15px 0;
        }}
        .date-separator span {{
            background: var(--card);
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 12px;
            color: var(--text-secondary);
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}
        .message {{
            max-width: 65%;
            margin: 2px 0;
            padding: 8px 12px;
            border-radius: 8px;
            background: var(--incoming);
            position: relative;
            box-shadow: 0 1px 1px rgba(0,0,0,0.05);
            word-wrap: break-word;
        }}
        .message.outgoing {{
            background: var(--outgoing);
            align-self: flex-end;
        }}
        .message.highlight {{ background: #ffeb3b !important; }}
        .message.hidden {{ display: none; }}
        .msg-sender {{
            font-size: 13px;
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 3px;
        }}
        .msg-text {{
            font-size: 14px;
            white-space: pre-wrap;
            line-height: 1.4;
        }}
        .msg-time {{
            font-size: 11px;
            color: var(--text-secondary);
            text-align: right;
            margin-top: 4px;
        }}
        .msg-quote {{
            border-left: 3px solid var(--accent);
            padding: 6px 10px;
            margin: 6px 0;
            background: rgba(0,0,0,0.05);
            border-radius: 0 6px 6px 0;
            font-size: 13px;
        }}
        .msg-quote-sender {{
            font-weight: 600;
            color: var(--accent);
            font-size: 12px;
        }}
        .msg-file {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(0,0,0,0.05);
            padding: 8px 10px;
            border-radius: 6px;
            margin-top: 6px;
        }}
        .msg-file a {{
            color: var(--accent);
            text-decoration: none;
            font-size: 13px;
        }}
        .msg-file a:hover {{ text-decoration: underline; }}

        /* Search Results */
        .search-results {{
            flex: 1;
            flex-direction: column;
            background: var(--sidebar-bg);
            overflow: hidden;
        }}
        .search-results-header {{
            padding: 15px 20px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 16px;
        }}
        .search-results-list {{
            flex: 1;
            overflow-y: auto;
            padding: 10px 0;
        }}
        .search-result-item {{
            padding: 12px 20px;
            cursor: pointer;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
            touch-action: manipulation;
        }}
        .search-result-item:hover {{
            background: var(--hover);
        }}
        .search-result-chat {{
            font-weight: 600;
            font-size: 13px;
            color: var(--accent);
            margin-bottom: 4px;
        }}
        .search-result-sender {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }}
        .search-result-text {{
            font-size: 14px;
            line-height: 1.4;
        }}
        .search-result-text mark {{
            background: #ffeb3b;
            color: #000;
            padding: 1px 2px;
            border-radius: 2px;
        }}
        .date-separator.hidden {{ display: none; }}

        /* Mobile */
        @media (max-width: 768px) {{
            .sidebar {{ width: 100%; position: absolute; z-index: 10; height: 100vh; }}
            .sidebar.hidden {{ display: none !important; }}
            .chat-area {{ width: 100%; }}
            .back-btn {{ display: block; }}
            .messages-container {{ padding: 8px 10px; }}
            .message {{ max-width: 90%; font-size: 14px; padding: 6px 10px; }}
            .chat-placeholder {{ display: none; }}
            .chat-item {{ padding: 10px 12px; -webkit-tap-highlight-color: transparent; }}
            .chat-avatar {{ width: 45px; height: 45px; font-size: 18px; margin-right: 10px; }}
            .chat-item-name {{ font-size: 14px; }}
            .chat-item-preview {{ font-size: 12px; }}
            .sidebar-header {{ padding: 12px; }}
            .sidebar-header h1 {{ font-size: 16px; }}
            .global-search {{ padding: 8px 12px; }}
            .global-search input {{ padding: 8px 12px; font-size: 14px; }}
            .search-mode {{ font-size: 11px; }}
            .chat-header-bar {{ padding: 8px 10px; }}
            .chat-header-name {{ font-size: 14px; }}
            .msg-sender {{ font-size: 12px; }}
            .msg-text {{ font-size: 13px; }}
            .msg-time {{ font-size: 10px; }}
            .pinned-bar {{ padding: 8px 12px; font-size: 12px; }}
        }}
    </style>
</head>
<body>
    <div class="app">
        <div class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <h1>📦 VK Teams Export</h1>
                <div class="sidebar-meta">📅 {export_date} · 💬 {len(chats)} чатов · 📨 {total_messages} сообщений</div>
            </div>
            <div class="global-search">
                <input type="text" id="globalSearch" placeholder="🔍 Поиск..." oninput="globalSearchHandler()">
                <div class="search-mode">
                    <label><input type="radio" name="searchMode" value="chats" checked> По названиям</label>
                    <label><input type="radio" name="searchMode" value="messages"> По сообщениям</label>
                </div>
            </div>
            <div class="chat-list" id="chatList">
                {chat_list_html}
            </div>
        </div>

        <div class="chat-area" id="chatArea">
            <div class="chat-placeholder" id="placeholder">
                Выберите чат для просмотра
            </div>
            <div class="search-results" id="searchResults" style="display:none;"></div>
            {chats_content_html}
        </div>
    </div>

    <script>
        let currentChat = -1;
        const isMobile = window.innerWidth <= 768;

        function selectChat(idx) {{
            // Убираем выделение со всех
            document.querySelectorAll('.chat-item').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.chat-content').forEach(el => el.style.display = 'none');

            // Скрываем результаты глобального поиска
            document.getElementById('searchResults').style.display = 'none';

            // Выделяем выбранный
            document.querySelectorAll('.chat-item')[idx].classList.add('active');
            document.getElementById('chat-content-' + idx).style.display = 'flex';
            document.getElementById('placeholder').style.display = 'none';

            currentChat = idx;

            // Скроллим вниз
            const container = document.getElementById('messages-' + idx);
            container.scrollTop = container.scrollHeight;

            // На мобилке скрываем сайдбар
            if (isMobile) {{
                document.getElementById('sidebar').classList.add('hidden');
            }}
        }}

        function showChatList() {{
            document.getElementById('sidebar').classList.remove('hidden');
            if (currentChat >= 0) {{
                document.getElementById('chat-content-' + currentChat).style.display = 'none';
            }}
            document.getElementById('placeholder').style.display = 'flex';
        }}

        function togglePinned(idx) {{
            const el = document.getElementById('pinned-' + idx);
            el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }}

        function toggleChatSearch(idx) {{
            const el = document.getElementById('chat-search-' + idx);
            el.style.display = el.style.display === 'none' ? 'flex' : 'none';
            if (el.style.display === 'flex') {{
                el.querySelector('input').focus();
            }}
        }}

        function searchInChat(idx, query) {{
            const q = query.toLowerCase().trim();
            const container = document.getElementById('messages-' + idx);
            const messages = container.querySelectorAll('.message');
            const dateSeparators = container.querySelectorAll('.date-separator');
            let found = 0;

            // Сначала обрабатываем сообщения
            messages.forEach(msg => {{
                const text = msg.textContent.toLowerCase();
                const match = !q || text.includes(q);
                msg.classList.toggle('hidden', q && !match);
                msg.classList.toggle('highlight', q && match);
                if (q && match) found++;
            }});

            // Скрываем разделители дат, если вокруг них нет видимых сообщений
            dateSeparators.forEach(sep => {{
                if (!q) {{
                    sep.classList.remove('hidden');
                    return;
                }}
                // Проверяем есть ли видимые сообщения после этого разделителя до следующего
                let hasVisibleMessages = false;
                let next = sep.nextElementSibling;
                while (next && !next.classList.contains('date-separator')) {{
                    if (next.classList.contains('message') && !next.classList.contains('hidden')) {{
                        hasVisibleMessages = true;
                        break;
                    }}
                    next = next.nextElementSibling;
                }}
                sep.classList.toggle('hidden', !hasVisibleMessages);
            }});

            document.getElementById('search-count-' + idx).textContent = q ? `Найдено: ${{found}}` : '';
        }}

        function globalSearchHandler() {{
            const query = document.getElementById('globalSearch').value.toLowerCase().trim();
            const mode = document.querySelector('input[name="searchMode"]:checked').value;
            const resultsContainer = document.getElementById('searchResults');
            const placeholder = document.getElementById('placeholder');

            // Сброс глобального поиска
            if (!query) {{
                document.querySelectorAll('.chat-item').forEach(item => item.classList.remove('hidden'));
                resultsContainer.style.display = 'none';
                resultsContainer.innerHTML = '';
                if (currentChat < 0) placeholder.style.display = 'flex';
                return;
            }}

            if (mode === 'chats') {{
                // Поиск по названиям чатов
                resultsContainer.style.display = 'none';
                if (currentChat < 0) placeholder.style.display = 'flex';
                document.querySelectorAll('.chat-item').forEach(item => {{
                    const name = item.querySelector('.chat-item-name').textContent.toLowerCase();
                    item.classList.toggle('hidden', !name.includes(query));
                }});
            }} else {{
                // Поиск по сообщениям - показываем результаты справа
                placeholder.style.display = 'none';
                document.querySelectorAll('.chat-content').forEach(el => el.style.display = 'none');

                let resultsHtml = '<div class="search-results-header">🔍 Результаты поиска</div><div class="search-results-list">';
                let totalFound = 0;

                document.querySelectorAll('.chat-item').forEach((item, idx) => {{
                    const chatName = item.querySelector('.chat-item-name').textContent;
                    const messages = document.querySelectorAll('#messages-' + idx + ' .message');
                    let chatHasMatch = false;

                    messages.forEach(msg => {{
                        const text = msg.textContent.toLowerCase();
                        if (text.includes(query)) {{
                            chatHasMatch = true;
                            totalFound++;
                            const msgText = msg.querySelector('.msg-text');
                            const msgTime = msg.querySelector('.msg-time');
                            const msgSender = msg.querySelector('.msg-sender');

                            const textPreview = msgText ? msgText.textContent.substring(0, 150) : '...';
                            const time = msgTime ? msgTime.textContent : '';
                            const sender = msgSender ? msgSender.textContent : '';

                            resultsHtml += `
                                <div class="search-result-item" onclick="goToMessage(${{idx}}, '${{msg.getAttribute('data-msgid') || ''}}')">
                                    <div class="search-result-chat">${{chatName}}</div>
                                    <div class="search-result-sender">${{sender}} ${{time}}</div>
                                    <div class="search-result-text">${{highlightText(textPreview, query)}}</div>
                                </div>
                            `;
                        }}
                    }});

                    item.classList.toggle('hidden', !chatHasMatch);
                }});

                resultsHtml += '</div>';
                resultsHtml = resultsHtml.replace('Результаты поиска', `Результаты поиска (${{totalFound}})`);
                resultsContainer.innerHTML = resultsHtml;
                resultsContainer.style.display = 'flex';
            }}
        }}

        function highlightText(text, query) {{
            if (!query) return text;
            const regex = new RegExp(`(${{query.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&')}})`, 'gi');
            return text.replace(regex, '<mark>$1</mark>');
        }}

        function goToMessage(chatIdx, msgId) {{
            selectChat(chatIdx);
            document.getElementById('searchResults').style.display = 'none';

            // Подсветить найденное сообщение
            if (msgId) {{
                const msg = document.querySelector(`#messages-${{chatIdx}} .message[data-msgid="${{msgId}}"]`);
                if (msg) {{
                    msg.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    msg.classList.add('highlight');
                    setTimeout(() => msg.classList.remove('highlight'), 2000);
                }}
            }}
        }}

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') showChatList();
            if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {{
                e.preventDefault();
                document.getElementById('globalSearch').focus();
            }}
        }});

        // Открываем первый чат на десктопе
        if (!isMobile && {len(chats)} > 0) {{
            selectChat(0);
        }}
    </script>
</body>
</html>'''


def render_message(msg: dict, pinned: bool = False, chat_members: dict = None, chat_sn: str = "", is_personal: bool = False) -> str:
    """Рендер одного сообщения в HTML"""
    is_outgoing = msg.get("outgoing", False)

    # Определяем отправителя
    sender_sn = (
        msg.get("chat", {}).get("sender") or
        msg.get("senderSn") or
        msg.get("sn") or
        msg.get("sender") or
        ""
    )

    # Для личных чатов определяем отправителя по outgoing
    if is_personal:
        if is_outgoing:
            sender_name = "Вы"
        else:
            sender_name = chat_sn
    else:
        sender_name = msg.get("senderNick") or msg.get("friendly") or ""
        if chat_members and sender_sn:
            member_info = chat_members.get(sender_sn, {})
            sender_name = member_info.get("friendly") or member_info.get("name") or sender_name
        if not sender_name and sender_sn:
            sender_name = sender_sn

    sender = escape(sender_name or "Неизвестный")

    # Время
    timestamp = msg.get("time", 0)
    time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M") if timestamp else ""

    # Контент
    content_html = ""
    parts = msg.get("parts", [])

    if parts:
        for part in parts:
            media_type = part.get("mediaType")

            if media_type == "text":
                captioned = part.get("captionedContent") or {}
                text = captioned.get("caption") or part.get("text", "")
                if text:
                    content_html += f'<div class="msg-text">{escape(text)}</div>'

            elif media_type == "quote":
                quote_sender = escape(part.get("sn", ""))
                quote_text = escape(str(part.get("text", ""))[:200])
                content_html += f'''
                    <div class="msg-quote">
                        <div class="msg-quote-sender">↩️ {quote_sender}</div>
                        <div>{quote_text}</div>
                    </div>
                '''

            elif media_type == "forward":
                fwd_sender = escape(part.get("sn", ""))
                captioned = part.get("captionedContent") or {}
                fwd_text = escape(str(captioned.get("caption") or part.get("text", ""))[:300])
                content_html += f'''
                    <div class="msg-quote" style="border-color:#9c27b0;">
                        <div class="msg-quote-sender" style="color:#9c27b0;">⤵️ {fwd_sender}</div>
                        <div>{fwd_text}</div>
                    </div>
                '''
    elif msg.get("text"):
        content_html += f'<div class="msg-text">{escape(msg["text"])}</div>'

    # Файлы
    for file in msg.get("filesharing", []):
        name = escape(file.get("name", "файл"))
        url = escape(file.get("original_url", "#"))
        size = format_size(file.get("size"))
        icon = get_file_icon(file.get("mime", ""))
        content_html += f'''
            <div class="msg-file">
                {icon} <a href="{url}" target="_blank">{name}</a>
                <span style="color:var(--text-secondary);font-size:11px;">{size}</span>
            </div>
        '''

    classes = "message outgoing" if is_outgoing else "message"
    msg_id = msg.get("msgId", "")

    # Показываем отправителя только для входящих в группах
    sender_html = ""
    if not is_outgoing and not is_personal:
        sender_html = f'<div class="msg-sender">{sender}</div>'

    return f'''
    <div class="{classes}" data-msgid="{msg_id}">
        {sender_html}
        {content_html}
        <div class="msg-time">{time_str}</div>
    </div>
    '''


def format_size(size) -> str:
    """Форматирование размера файла"""
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
    else:
        return f"{size / (1024 * 1024):.1f} МБ"


def get_file_icon(mime: str) -> str:
    """Иконка по MIME типу"""
    if not mime:
        return "📎"
    if mime.startswith("image/"):
        return "🖼️"
    if mime.startswith("video/"):
        return "🎬"
    if mime.startswith("audio/"):
        return "🎵"
    if "pdf" in mime:
        return "📄"
    if "zip" in mime or "rar" in mime:
        return "📦"
    if "word" in mime or "document" in mime:
        return "📝"
    if "excel" in mime or "spreadsheet" in mime:
        return "📊"
    return "📎"
