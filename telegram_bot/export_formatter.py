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
    """Форматирование в HTML с поддержкой поиска и тёмной темы"""

    chats_html = ""
    total_messages = 0

    for chat in data.get("chats", []):
        chat_name = escape(chat.get("chat_name", chat.get("chat_sn", "Чат")))
        messages = chat.get("messages", [])
        total_messages += len(messages)

        # Собираем информацию об участниках из сообщений
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

        messages_html = ""
        for msg in messages:
            messages_html += render_message(msg, chat_members=chat_members)

        # Закреплённые сообщения
        pinned_html = ""
        pinned = chat.get("pinned_messages", [])
        if pinned:
            pinned_items = "".join(render_message(m, pinned=True, chat_members=chat_members) for m in pinned)
            pinned_html = f'''
            <div class="pinned-section">
                <h3>📌 Закреплённые ({len(pinned)})</h3>
                {pinned_items}
            </div>
            '''

        chats_html += f'''
        <div class="chat-section" id="chat-{escape(chat.get('chat_sn', ''))}">
            <h2 class="chat-title">💬 {chat_name}</h2>
            <div class="chat-meta">
                📊 Сообщений: {len(messages)}
            </div>
            {pinned_html}
            <div class="messages">
                {messages_html}
            </div>
        </div>
        '''

    # Навигация по чатам
    nav_items = ""
    for chat in data.get("chats", []):
        chat_name = escape(chat.get("chat_name", chat.get("chat_sn", ""))[:25])
        sn = escape(chat.get("chat_sn", ""))
        nav_items += f'<a href="#chat-{sn}" class="nav-item">{chat_name}</a>'

    export_date = data.get("export_date", datetime.now().isoformat())

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VK Teams Export</title>
    <style>
        :root {{
            --bg: #f0f2f5;
            --card: #ffffff;
            --text: #1a1a1a;
            --text-secondary: #65676b;
            --accent: #0077ff;
            --border: #e4e6eb;
            --outgoing-bg: #e7f3ff;
            --nav-bg: #ffffff;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #18191a;
                --card: #242526;
                --text: #e4e6eb;
                --text-secondary: #b0b3b8;
                --accent: #4599ff;
                --border: #3e4042;
                --outgoing-bg: #263951;
                --nav-bg: #242526;
            }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
        }}
        .header {{
            background: var(--card);
            padding: 20px;
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        .header h1 {{
            font-size: 20px;
            margin-bottom: 10px;
        }}
        .header-meta {{
            font-size: 14px;
            color: var(--text-secondary);
        }}
        .search-box {{
            margin-top: 15px;
        }}
        .search-box input {{
            width: 100%;
            max-width: 400px;
            padding: 10px 15px;
            border: 1px solid var(--border);
            border-radius: 20px;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
        }}
        .container {{
            display: flex;
            max-width: 1400px;
            margin: 0 auto;
        }}
        .nav {{
            width: 250px;
            background: var(--nav-bg);
            border-right: 1px solid var(--border);
            height: calc(100vh - 120px);
            overflow-y: auto;
            position: sticky;
            top: 120px;
            padding: 10px;
        }}
        .nav-item {{
            display: block;
            padding: 10px 12px;
            color: var(--text);
            text-decoration: none;
            border-radius: 8px;
            margin-bottom: 4px;
            font-size: 14px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .nav-item:hover {{
            background: var(--bg);
        }}
        .content {{
            flex: 1;
            padding: 20px;
            min-width: 0;
        }}
        .chat-section {{
            background: var(--card);
            border-radius: 12px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .chat-title {{
            padding: 20px;
            border-bottom: 1px solid var(--border);
            font-size: 18px;
        }}
        .chat-meta {{
            padding: 10px 20px;
            font-size: 13px;
            color: var(--text-secondary);
            background: var(--bg);
        }}
        .pinned-section {{
            padding: 15px 20px;
            background: #fffde7;
            border-left: 4px solid #ffc107;
        }}
        .pinned-section h3 {{
            font-size: 14px;
            margin-bottom: 10px;
            color: #f57c00;
        }}
        @media (prefers-color-scheme: dark) {{
            .pinned-section {{
                background: #3e3a00;
            }}
        }}
        .messages {{
            padding: 10px;
        }}
        .message {{
            padding: 12px 16px;
            margin: 6px 10px;
            border-radius: 12px;
            background: var(--bg);
            max-width: 85%;
        }}
        .message.outgoing {{
            background: var(--outgoing-bg);
            margin-left: auto;
        }}
        .message.pinned {{
            border-left: 3px solid #ffc107;
        }}
        .message.hidden {{ display: none; }}
        .msg-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 13px;
        }}
        .sender {{
            font-weight: 600;
            color: var(--accent);
        }}
        .time {{
            color: var(--text-secondary);
        }}
        .text {{
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .quote {{
            border-left: 3px solid var(--accent);
            padding: 8px 12px;
            margin: 8px 0;
            background: var(--card);
            border-radius: 0 8px 8px 0;
            font-size: 13px;
        }}
        .quote-sender {{
            font-weight: 600;
            color: var(--accent);
            font-size: 12px;
        }}
        .file {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--card);
            padding: 8px 12px;
            border-radius: 8px;
            margin-top: 8px;
            font-size: 13px;
        }}
        .file a {{
            color: var(--accent);
            text-decoration: none;
        }}
        .file a:hover {{ text-decoration: underline; }}

        @media (max-width: 768px) {{
            .nav {{ display: none; }}
            .container {{ display: block; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📦 VK Teams Export</h1>
        <div class="header-meta">
            📅 {export_date[:10]} · 💬 {len(data.get('chats', []))} чатов · 📨 {total_messages} сообщений
        </div>
        <div class="search-box">
            <input type="text" id="search" placeholder="🔍 Поиск по сообщениям..." autocomplete="off">
        </div>
    </div>

    <div class="container">
        <nav class="nav">
            <h3 style="padding: 10px; font-size: 14px; color: var(--text-secondary);">Чаты</h3>
            {nav_items}
        </nav>
        <div class="content">
            {chats_html}
        </div>
    </div>

    <script>
        const searchInput = document.getElementById('search');
        searchInput.addEventListener('input', (e) => {{
            const q = e.target.value.toLowerCase().trim();
            document.querySelectorAll('.message').forEach(msg => {{
                const text = msg.textContent.toLowerCase();
                msg.classList.toggle('hidden', q && !text.includes(q));
            }});
        }});

        document.addEventListener('keydown', (e) => {{
            if (e.key === '/' && document.activeElement !== searchInput) {{
                e.preventDefault();
                searchInput.focus();
            }}
        }});
    </script>
</body>
</html>'''


def render_message(msg: dict, pinned: bool = False, chat_members: dict = None) -> str:
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

    # Пытаемся найти имя по sn в списке участников
    sender_name = msg.get("senderNick") or msg.get("friendly") or ""

    # Если есть словарь участников, ищем там
    if chat_members and sender_sn:
        member_info = chat_members.get(sender_sn, {})
        sender_name = member_info.get("friendly") or member_info.get("name") or sender_name

    # Если имя не найдено, показываем полный email/sn
    if not sender_name and sender_sn:
        sender_name = sender_sn

    sender = escape(sender_name or "Неизвестный")

    # Время
    timestamp = msg.get("time", 0)
    time_str = datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M") if timestamp else ""

    # Контент
    content_html = ""

    # Обрабатываем parts
    parts = msg.get("parts", [])
    if parts:
        for part in parts:
            media_type = part.get("mediaType")

            if media_type == "text":
                captioned = part.get("captionedContent") or {}
                text = captioned.get("caption") or part.get("text", "")
                content_html += f'<div class="text">{escape(text)}</div>'

            elif media_type == "quote":
                quote_sender = escape(part.get("sn", ""))
                quote_text = escape(str(part.get("text", ""))[:200])
                content_html += f'''
                    <div class="quote">
                        <div class="quote-sender">↩️ {quote_sender}</div>
                        <div>{quote_text}</div>
                    </div>
                '''

            elif media_type == "forward":
                fwd_sender = escape(part.get("sn", ""))
                captioned = part.get("captionedContent") or {}
                fwd_text = escape(
                    str(captioned.get("caption") or part.get("text", ""))[:300]
                )
                content_html += f'''
                    <div class="quote" style="border-color: #9c27b0;">
                        <div class="quote-sender" style="color: #9c27b0;">⤵️ Переслано от {fwd_sender}</div>
                        <div>{fwd_text}</div>
                    </div>
                '''
    elif msg.get("text"):
        content_html += f'<div class="text">{escape(msg["text"])}</div>'

    # Файлы
    files_html = ""
    for file in msg.get("filesharing", []):
        name = escape(file.get("name", "файл"))
        url = escape(file.get("original_url", "#"))
        size = format_size(file.get("size"))
        icon = get_file_icon(file.get("mime", ""))
        files_html += f'''
            <div class="file">
                {icon} <a href="{url}" target="_blank">{name}</a>
                <span style="color: var(--text-secondary);">{size}</span>
            </div>
        '''

    classes = ["message"]
    if is_outgoing:
        classes.append("outgoing")
    if pinned:
        classes.append("pinned")

    return f'''
    <div class="{' '.join(classes)}">
        <div class="msg-header">
            <span class="sender">{sender}</span>
            <span class="time">{time_str}</span>
        </div>
        {content_html}
        {files_html}
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
