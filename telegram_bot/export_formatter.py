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

        # Элемент списка чатов (tabindex и role для iOS)
        chat_list_html += f'''
        <div class="chat-item" data-chat-id="{idx}" tabindex="0" role="button">
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
            <div class="pinned-bar" data-pinned-id="{idx}" tabindex="0" role="button">
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
                <button class="back-btn" type="button">←</button>
                <div class="chat-header-info">
                    <div class="chat-header-name">{chat_name}</div>
                    <div class="chat-header-meta">{msg_count} сообщений</div>
                </div>
                <button class="search-chat-btn" type="button" data-search-chat="{idx}">🔍</button>
            </div>
            <div class="chat-search-bar" id="chat-search-{idx}" style="display:none;">
                <input type="text" placeholder="Поиск в этом чате..." data-chat-search-input="{idx}">
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
                <input type="text" id="globalSearch" placeholder="🔍 Поиск...">
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

    <noscript>
        <div style="padding:20px;text-align:center;background:#ff6b6b;color:white;">
            ⚠️ JavaScript отключен. Откройте файл в Safari для полной функциональности.
        </div>
    </noscript>
    <script>
        (function() {{
            'use strict';

            var currentChat = -1;
            var isMobile = window.innerWidth <= 768;

            // === Основные функции ===
            function selectChat(idx) {{
                var items = document.querySelectorAll('.chat-item');
                var contents = document.querySelectorAll('.chat-content');

                for (var i = 0; i < items.length; i++) {{
                    items[i].classList.remove('active');
                }}
                for (var i = 0; i < contents.length; i++) {{
                    contents[i].style.display = 'none';
                }}

                document.getElementById('searchResults').style.display = 'none';

                if (items[idx]) items[idx].classList.add('active');
                var content = document.getElementById('chat-content-' + idx);
                if (content) content.style.display = 'flex';
                document.getElementById('placeholder').style.display = 'none';

                currentChat = idx;

                var container = document.getElementById('messages-' + idx);
                if (container) container.scrollTop = container.scrollHeight;

                if (isMobile) {{
                    document.getElementById('sidebar').classList.add('hidden');
                }}
            }}

            function showChatList() {{
                document.getElementById('sidebar').classList.remove('hidden');
                if (currentChat >= 0) {{
                    var content = document.getElementById('chat-content-' + currentChat);
                    if (content) content.style.display = 'none';
                }}
                document.getElementById('placeholder').style.display = 'flex';
            }}

            function togglePinned(idx) {{
                var el = document.getElementById('pinned-' + idx);
                if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
            }}

            function toggleChatSearch(idx) {{
                var el = document.getElementById('chat-search-' + idx);
                if (!el) return;
                el.style.display = el.style.display === 'none' ? 'flex' : 'none';
                if (el.style.display === 'flex') {{
                    var input = el.querySelector('input');
                    if (input) input.focus();
                }}
            }}

            function searchInChat(idx, query) {{
                var q = (query || '').toLowerCase().trim();
                var container = document.getElementById('messages-' + idx);
                if (!container) return;

                var messages = container.querySelectorAll('.message');
                var dateSeparators = container.querySelectorAll('.date-separator');
                var found = 0;

                for (var i = 0; i < messages.length; i++) {{
                    var msg = messages[i];
                    var text = msg.textContent.toLowerCase();
                    var match = !q || text.indexOf(q) !== -1;
                    msg.classList.toggle('hidden', q && !match);
                    msg.classList.toggle('highlight', q && match);
                    if (q && match) found++;
                }}

                for (var i = 0; i < dateSeparators.length; i++) {{
                    var sep = dateSeparators[i];
                    if (!q) {{
                        sep.classList.remove('hidden');
                        continue;
                    }}
                    var hasVisibleMessages = false;
                    var next = sep.nextElementSibling;
                    while (next && !next.classList.contains('date-separator')) {{
                        if (next.classList.contains('message') && !next.classList.contains('hidden')) {{
                            hasVisibleMessages = true;
                            break;
                        }}
                        next = next.nextElementSibling;
                    }}
                    sep.classList.toggle('hidden', !hasVisibleMessages);
                }}

                var countEl = document.getElementById('search-count-' + idx);
                if (countEl) countEl.textContent = q ? 'Найдено: ' + found : '';
            }}

            function escapeHtml(text) {{
                var div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }}

            function highlightText(text, query) {{
                if (!query || !text) return escapeHtml(text);
                var escaped = escapeHtml(text);
                var q = query.toLowerCase();
                var result = '';
                var lowerText = text.toLowerCase();
                var lastIdx = 0;
                var idx = lowerText.indexOf(q);
                while (idx !== -1) {{
                    result += escapeHtml(text.substring(lastIdx, idx));
                    result += '<mark>' + escapeHtml(text.substring(idx, idx + query.length)) + '</mark>';
                    lastIdx = idx + query.length;
                    idx = lowerText.indexOf(q, lastIdx);
                }}
                result += escapeHtml(text.substring(lastIdx));
                return result;
            }}

            function globalSearchHandler() {{
                var searchInput = document.getElementById('globalSearch');
                var query = (searchInput ? searchInput.value : '').toLowerCase().trim();
                var modeRadio = document.querySelector('input[name="searchMode"]:checked');
                var mode = modeRadio ? modeRadio.value : 'chats';
                var resultsContainer = document.getElementById('searchResults');
                var placeholder = document.getElementById('placeholder');
                var chatItems = document.querySelectorAll('.chat-item');

                if (!query) {{
                    for (var i = 0; i < chatItems.length; i++) {{
                        chatItems[i].classList.remove('hidden');
                    }}
                    resultsContainer.style.display = 'none';
                    resultsContainer.innerHTML = '';
                    if (currentChat < 0) placeholder.style.display = 'flex';
                    return;
                }}

                if (mode === 'chats') {{
                    resultsContainer.style.display = 'none';
                    if (currentChat < 0) placeholder.style.display = 'flex';
                    for (var i = 0; i < chatItems.length; i++) {{
                        var name = chatItems[i].querySelector('.chat-item-name');
                        var nameText = name ? name.textContent.toLowerCase() : '';
                        chatItems[i].classList.toggle('hidden', nameText.indexOf(query) === -1);
                    }}
                }} else {{
                    placeholder.style.display = 'none';
                    var contents = document.querySelectorAll('.chat-content');
                    for (var i = 0; i < contents.length; i++) {{
                        contents[i].style.display = 'none';
                    }}

                    var resultsHtml = '<div class="search-results-header">🔍 Результаты поиска</div><div class="search-results-list">';
                    var totalFound = 0;

                    for (var i = 0; i < chatItems.length; i++) {{
                        var item = chatItems[i];
                        var chatNameEl = item.querySelector('.chat-item-name');
                        var chatName = chatNameEl ? chatNameEl.textContent : '';
                        var messages = document.querySelectorAll('#messages-' + i + ' .message');
                        var chatHasMatch = false;

                        for (var j = 0; j < messages.length; j++) {{
                            var msg = messages[j];
                            var text = msg.textContent.toLowerCase();
                            if (text.indexOf(query) !== -1) {{
                                chatHasMatch = true;
                                totalFound++;
                                var msgText = msg.querySelector('.msg-text');
                                var msgTime = msg.querySelector('.msg-time');
                                var msgSender = msg.querySelector('.msg-sender');

                                var textPreview = msgText ? msgText.textContent.substring(0, 150) : '...';
                                var time = msgTime ? msgTime.textContent : '';
                                var sender = msgSender ? msgSender.textContent : '';
                                var msgId = msg.getAttribute('data-msgid') || '';

                                resultsHtml += '<div class="search-result-item" data-goto-chat="' + i + '" data-goto-msg="' + escapeHtml(msgId) + '" tabindex="0" role="button">';
                                resultsHtml += '<div class="search-result-chat">' + escapeHtml(chatName) + '</div>';
                                resultsHtml += '<div class="search-result-sender">' + escapeHtml(sender) + ' ' + escapeHtml(time) + '</div>';
                                resultsHtml += '<div class="search-result-text">' + highlightText(textPreview, query) + '</div>';
                                resultsHtml += '</div>';
                            }}
                        }}

                        item.classList.toggle('hidden', !chatHasMatch);
                    }}

                    resultsHtml += '</div>';
                    resultsHtml = resultsHtml.replace('Результаты поиска', 'Результаты поиска (' + totalFound + ')');
                    resultsContainer.innerHTML = resultsHtml;
                    resultsContainer.style.display = 'flex';
                }}
            }}

            function goToMessage(chatIdx, msgId) {{
                selectChat(chatIdx);
                document.getElementById('searchResults').style.display = 'none';

                if (msgId) {{
                    var msg = document.querySelector('#messages-' + chatIdx + ' .message[data-msgid="' + msgId + '"]');
                    if (msg) {{
                        msg.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        msg.classList.add('highlight');
                        setTimeout(function() {{ msg.classList.remove('highlight'); }}, 2000);
                    }}
                }}
            }}

            // === Event Delegation (работает на iOS) ===
            document.addEventListener('click', function(e) {{
                var target = e.target;

                // Поиск родительского элемента с нужным классом/атрибутом
                var chatItem = target.closest('.chat-item');
                var backBtn = target.closest('.back-btn');
                var searchBtn = target.closest('.search-chat-btn');
                var pinnedBar = target.closest('.pinned-bar');
                var searchResult = target.closest('.search-result-item');

                if (chatItem) {{
                    var idx = parseInt(chatItem.getAttribute('data-chat-id'), 10);
                    if (!isNaN(idx)) selectChat(idx);
                    return;
                }}

                if (backBtn) {{
                    showChatList();
                    return;
                }}

                if (searchBtn) {{
                    var idx = parseInt(searchBtn.getAttribute('data-search-chat'), 10);
                    if (!isNaN(idx)) toggleChatSearch(idx);
                    return;
                }}

                if (pinnedBar) {{
                    var idx = parseInt(pinnedBar.getAttribute('data-pinned-id'), 10);
                    if (!isNaN(idx)) togglePinned(idx);
                    return;
                }}

                if (searchResult) {{
                    var chatIdx = parseInt(searchResult.getAttribute('data-goto-chat'), 10);
                    var msgId = searchResult.getAttribute('data-goto-msg') || '';
                    if (!isNaN(chatIdx)) goToMessage(chatIdx, msgId);
                    return;
                }}
            }}, false);

            // Поиск - input события
            var globalSearch = document.getElementById('globalSearch');
            if (globalSearch) {{
                globalSearch.addEventListener('input', globalSearchHandler, false);
            }}

            // Поиск в чате - делегирование
            document.addEventListener('input', function(e) {{
                var target = e.target;
                if (target.hasAttribute('data-chat-search-input')) {{
                    var idx = parseInt(target.getAttribute('data-chat-search-input'), 10);
                    if (!isNaN(idx)) searchInChat(idx, target.value);
                }}
            }}, false);

            // Radio buttons
            var radios = document.querySelectorAll('input[name="searchMode"]');
            for (var i = 0; i < radios.length; i++) {{
                radios[i].addEventListener('change', globalSearchHandler, false);
            }}

            // Keyboard shortcuts
            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Escape') showChatList();
                if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {{
                    e.preventDefault();
                    if (globalSearch) globalSearch.focus();
                }}
            }}, false);

            // Открываем первый чат на десктопе
            if (!isMobile && {len(chats)} > 0) {{
                selectChat(0);
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
