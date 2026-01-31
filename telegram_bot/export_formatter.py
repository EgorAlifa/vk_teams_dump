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
    """Форматирование в HTML - гибридный интерфейс (работает и без JS на iOS)"""

    chats = data.get("chats", [])
    total_messages = sum(len(c.get("messages", [])) for c in chats)
    export_date = data.get("export_date", datetime.now().isoformat())[:10]

    # Генерируем чаты
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
            <details class="pinned-details">
                <summary class="pinned-bar">📌 Закреплённых: {len(pinned)}</summary>
                <div class="pinned-messages">
                    {"".join(render_message(m, pinned=True, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal) for m in pinned)}
                </div>
            </details>
            '''

        # Элемент списка чатов (для sidebar на ПК и для no-JS)
        chat_list_html += f'''
        <a href="#chat-{idx}" class="chat-item" data-chat-id="{idx}">
            <div class="chat-avatar">{chat_name[0].upper()}</div>
            <div class="chat-item-info">
                <div class="chat-item-header">
                    <span class="chat-item-name">{chat_name[:30]}{"..." if len(chat_name) > 30 else ""}</span>
                    <span class="chat-item-time">{last_time}</span>
                </div>
                <div class="chat-item-preview">{last_text}</div>
            </div>
            <div class="chat-item-badge">{msg_count}</div>
        </a>
        '''

        # Контент чата
        chats_content_html += f'''
        <div class="chat-content" id="chat-{idx}" data-chat-id="{idx}">
            <div class="chat-header-bar">
                <button class="back-btn" type="button" onclick="showSidebar()">← Назад</button>
                <div class="chat-header-info">
                    <div class="chat-header-name">{chat_name}</div>
                    <div class="chat-header-meta">{msg_count} сообщений</div>
                </div>
            </div>
            {pinned_html}
            <div class="messages-container">
                {messages_html}
            </div>
        </div>
        '''

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
    <title>VK Teams Export</title>
    <style>
        :root {{
            --bg: #f0f2f5;
            --card: #ffffff;
            --text: #1a1a1a;
            --text-secondary: #667781;
            --accent: #00a884;
            --border: #e9edef;
            --incoming: #ffffff;
            --outgoing: #d9fdd3;
            --hover: #f5f6f6;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #111b21;
                --card: #202c33;
                --text: #e9edef;
                --text-secondary: #8696a0;
                --accent: #00a884;
                --border: #222d34;
                --incoming: #202c33;
                --outgoing: #005c4b;
                --hover: #2a3942;
            }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.4;
        }}

        /* === DESKTOP LAYOUT (with JS) === */
        .app {{
            display: flex;
            height: 100vh;
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Sidebar */
        .sidebar {{
            width: 380px;
            background: var(--card);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            height: 100vh;
            overflow: hidden;
        }}
        .sidebar-header {{
            padding: 15px;
            border-bottom: 1px solid var(--border);
        }}
        .sidebar-header h1 {{ font-size: 18px; margin-bottom: 5px; }}
        .sidebar-meta {{ font-size: 12px; color: var(--text-secondary); }}

        .search-box {{
            padding: 10px 15px;
            border-bottom: 1px solid var(--border);
        }}
        .search-box input {{
            width: 100%;
            padding: 10px 15px;
            border: none;
            border-radius: 8px;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
        }}

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
            text-decoration: none;
            color: inherit;
            transition: background 0.15s;
        }}
        .chat-item:hover, .chat-item.active {{ background: var(--hover); }}
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
        .chat-item-info {{ flex: 1; min-width: 0; }}
        .chat-item-header {{ display: flex; justify-content: space-between; margin-bottom: 3px; }}
        .chat-item-name {{ font-weight: 500; font-size: 15px; }}
        .chat-item-time {{ font-size: 12px; color: var(--text-secondary); }}
        .chat-item-preview {{ font-size: 13px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .chat-item-badge {{
            background: var(--accent);
            color: white;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
            margin-left: 8px;
        }}

        /* Chat area */
        .chat-area {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg);
            min-width: 0;
            height: 100vh;
            overflow: hidden;
        }}
        .chat-placeholder {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-secondary);
        }}

        .chat-content {{
            display: none;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
        }}
        .chat-content:target,
        .chat-content.active {{
            display: flex;
        }}

        .chat-header-bar {{
            display: flex;
            align-items: center;
            padding: 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
            gap: 15px;
        }}
        .back-btn {{
            display: none;
            background: none;
            border: none;
            font-size: 16px;
            cursor: pointer;
            color: var(--accent);
            padding: 5px 10px;
        }}
        .chat-header-info {{ flex: 1; }}
        .chat-header-name {{ font-weight: 600; font-size: 16px; }}
        .chat-header-meta {{ font-size: 12px; color: var(--text-secondary); }}

        .messages-container {{
            flex: 1;
            overflow-y: auto;
            padding: 15px 50px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        /* Pinned */
        .pinned-details {{ margin: 10px 15px; }}
        .pinned-bar {{
            padding: 10px 15px;
            background: #fff3cd;
            color: #856404;
            font-size: 13px;
            cursor: pointer;
            border-radius: 8px;
            list-style: none;
        }}
        .pinned-bar::-webkit-details-marker {{ display: none; }}
        @media (prefers-color-scheme: dark) {{
            .pinned-bar {{ background: #3d3200; color: #ffc107; }}
        }}
        .pinned-messages {{
            background: var(--card);
            border-radius: 8px;
            margin-top: 5px;
            padding: 10px;
            max-height: 200px;
            overflow-y: auto;
        }}

        /* Messages */
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
        }}
        .message {{
            max-width: 65%;
            padding: 8px 12px;
            border-radius: 8px;
            background: var(--incoming);
            word-wrap: break-word;
        }}
        .message.outgoing {{
            background: var(--outgoing);
            align-self: flex-end;
        }}
        .msg-sender {{
            font-size: 12px;
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 2px;
        }}
        .msg-text {{
            font-size: 14px;
            white-space: pre-wrap;
        }}
        .msg-time {{
            font-size: 10px;
            color: var(--text-secondary);
            text-align: right;
            margin-top: 2px;
        }}
        .msg-quote {{
            border-left: 3px solid var(--accent);
            padding: 5px 10px;
            margin: 5px 0;
            background: rgba(0,0,0,0.05);
            border-radius: 0 6px 6px 0;
            font-size: 12px;
        }}
        .msg-quote-sender {{ font-weight: 600; color: var(--accent); font-size: 11px; }}
        .msg-file {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(0,0,0,0.05);
            padding: 8px 10px;
            border-radius: 6px;
            margin-top: 5px;
        }}
        .msg-file a {{ color: var(--accent); text-decoration: none; font-size: 13px; }}

        /* === MOBILE === */
        @media (max-width: 768px) {{
            .app {{
                flex-direction: column;
                height: auto;
            }}
            .sidebar {{
                width: 100%;
                height: auto;
                max-height: 100vh;
                position: fixed;
                top: 0;
                left: 0;
                z-index: 100;
                transition: transform 0.3s;
            }}
            .sidebar.hidden {{
                transform: translateX(-100%);
            }}
            .chat-area {{
                width: 100%;
                height: 100vh;
            }}
            .chat-placeholder {{ display: none; }}
            .back-btn {{ display: block; }}
            .messages-container {{ padding: 10px 15px; }}
            .message {{ max-width: 85%; }}
            .chat-item {{ padding: 10px 12px; }}
            .chat-avatar {{ width: 45px; height: 45px; font-size: 18px; }}

            /* No-JS: показываем чат по :target */
            .chat-content:target {{
                display: flex;
            }}
        }}

        /* === NO-JS FALLBACK === */
        .no-js-index {{
            display: none;
            padding: 15px;
            background: var(--card);
            border-bottom: 1px solid var(--border);
        }}
        .no-js-index a {{
            color: var(--accent);
            margin-right: 10px;
            text-decoration: none;
            font-size: 13px;
        }}

        /* Show no-js elements when JS is disabled */
        @media (max-width: 768px) {{
            .no-js-note {{
                display: block;
                padding: 10px 15px;
                background: #e3f2fd;
                color: #1565c0;
                font-size: 12px;
                text-align: center;
            }}
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
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Поиск по названию чата...">
            </div>
            <div class="chat-list" id="chatList">
                {chat_list_html}
            </div>
        </div>

        <div class="chat-area" id="chatArea">
            <div class="chat-placeholder" id="placeholder">
                👈 Выберите чат для просмотра
            </div>
            {chats_content_html}
        </div>
    </div>

    <script>
        (function() {{
            var sidebar = document.getElementById('sidebar');
            var chatArea = document.getElementById('chatArea');
            var placeholder = document.getElementById('placeholder');
            var searchInput = document.getElementById('searchInput');
            var chatItems = document.querySelectorAll('.chat-item');
            var chatContents = document.querySelectorAll('.chat-content');
            var isMobile = window.innerWidth <= 768;

            // Поиск
            if (searchInput) {{
                searchInput.addEventListener('input', function() {{
                    var q = this.value.toLowerCase().trim();
                    chatItems.forEach(function(item) {{
                        var name = item.querySelector('.chat-item-name');
                        var text = name ? name.textContent.toLowerCase() : '';
                        item.classList.toggle('hidden', q && text.indexOf(q) === -1);
                    }});
                }});
            }}

            // Клик по чату
            chatItems.forEach(function(item) {{
                item.addEventListener('click', function(e) {{
                    e.preventDefault();
                    var chatId = this.getAttribute('data-chat-id');
                    selectChat(chatId);
                }});
            }});

            function selectChat(chatId) {{
                // Убираем активный класс
                chatItems.forEach(function(i) {{ i.classList.remove('active'); }});
                chatContents.forEach(function(c) {{ c.classList.remove('active'); }});

                // Активируем выбранный
                var item = document.querySelector('.chat-item[data-chat-id="' + chatId + '"]');
                var content = document.getElementById('chat-' + chatId);

                if (item) item.classList.add('active');
                if (content) {{
                    content.classList.add('active');
                    placeholder.style.display = 'none';
                    // Скролл вниз
                    var messages = content.querySelector('.messages-container');
                    if (messages) messages.scrollTop = messages.scrollHeight;
                }}

                // На мобильном скрываем sidebar
                if (isMobile) {{
                    sidebar.classList.add('hidden');
                }}
            }}

            // Показать sidebar
            window.showSidebar = function() {{
                sidebar.classList.remove('hidden');
                chatContents.forEach(function(c) {{ c.classList.remove('active'); }});
                placeholder.style.display = 'flex';
            }};

            // Обработка хеша (для no-JS навигации)
            function handleHash() {{
                var hash = window.location.hash;
                if (hash && hash.startsWith('#chat-')) {{
                    var chatId = hash.replace('#chat-', '');
                    selectChat(chatId);
                }}
            }}
            window.addEventListener('hashchange', handleHash);
            if (window.location.hash) handleHash();

            // На десктопе открываем первый чат
            if (!isMobile && chatItems.length > 0) {{
                selectChat('0');
            }}
        }})();
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
