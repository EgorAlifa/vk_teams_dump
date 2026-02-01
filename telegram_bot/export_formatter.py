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
    """
    Форматирование в HTML - универсальный интерфейс

    Работает везде:
    - iOS Files (без JS): details/summary раскрываются нативно
    - iOS Safari (с JS): улучшенный интерфейс
    - Android: работает везде
    - ПК (с JS): двухпанельный интерфейс как мессенджер
    """

    chats = data.get("chats", [])
    total_messages = sum(len(c.get("messages", [])) for c in chats)
    export_date = data.get("export_date", datetime.now().isoformat())[:10]

    # Генерируем чаты
    chats_html = ""

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
                    messages_html += f'<div class="date-sep"><span>{msg_date}</span></div>'

            messages_html += render_message(msg, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal)

        # Закреплённые
        pinned = chat.get("pinned_messages", [])
        pinned_html = ""
        if pinned:
            pinned_html = f'''
            <details class="pinned">
                <summary>📌 Закреплённых: {len(pinned)}</summary>
                <div class="pinned-list">
                    {"".join(render_message(m, pinned=True, chat_members=chat_members, chat_sn=chat_sn, is_personal=is_personal) for m in pinned)}
                </div>
            </details>
            '''

        # Чат как details/summary - работает ВЕЗДЕ без JS
        chats_html += f'''
<details class="chat" data-id="{idx}">
    <summary class="chat-header">
        <span class="avatar">{chat_name[0].upper()}</span>
        <span class="info">
            <span class="name">{chat_name[:35]}{"…" if len(chat_name) > 35 else ""}</span>
            <span class="preview">{last_text}</span>
        </span>
        <span class="meta">
            <span class="time">{last_time}</span>
            <span class="count">{msg_count}</span>
        </span>
    </summary>
    <div class="chat-body">
        <div class="chat-title">
            <strong>{chat_name}</strong>
            <span>{msg_count} сообщений</span>
        </div>
        {pinned_html}
        <div class="messages">
            {messages_html}
        </div>
    </div>
</details>
'''

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5">
<title>VK Teams Export</title>
<style>
:root {{
    --bg:#f5f5f5; --card:#fff; --text:#222; --text2:#666;
    --accent:#00a884; --border:#e0e0e0; --in:#fff; --out:#dcf8c6;
}}
@media(prefers-color-scheme:dark) {{
    :root {{
        --bg:#0a0a0a; --card:#1a1a1a; --text:#eee; --text2:#888;
        --accent:#00a884; --border:#333; --in:#1a1a1a; --out:#054640;
    }}
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,system-ui,sans-serif; background:var(--bg); color:var(--text); }}

/* Header */
.header {{
    position:sticky; top:0; z-index:100;
    background:var(--card); padding:12px 16px;
    border-bottom:1px solid var(--border);
}}
.header h1 {{ font-size:18px; margin-bottom:4px; }}
.header small {{ color:var(--text2); font-size:12px; }}

/* Search */
.search {{
    position:sticky; top:58px; z-index:99;
    background:var(--card); padding:8px 16px;
    border-bottom:1px solid var(--border);
}}
.search input {{
    width:100%; padding:10px 14px; border:none; border-radius:8px;
    background:var(--bg); color:var(--text); font-size:15px;
}}

/* Chat list */
.list {{ max-width:800px; margin:0 auto; }}

/* Each chat - details/summary */
.chat {{
    background:var(--card);
    border-bottom:1px solid var(--border);
}}
.chat[open] {{ background:var(--bg); }}
.chat[open] .chat-header {{ background:var(--accent); color:#fff; }}
.chat[open] .chat-header .text2,
.chat[open] .chat-header .time {{ color:rgba(255,255,255,0.8); }}

.chat-header {{
    display:flex; align-items:center; gap:12px;
    padding:12px 16px; cursor:pointer;
    list-style:none;
}}
.chat-header::-webkit-details-marker {{ display:none; }}

.avatar {{
    width:48px; height:48px; border-radius:50%;
    background:var(--accent); color:#fff;
    display:flex; align-items:center; justify-content:center;
    font-size:20px; font-weight:500; flex-shrink:0;
}}
.chat[open] .avatar {{ background:rgba(255,255,255,0.2); }}

.info {{ flex:1; min-width:0; }}
.name {{ display:block; font-weight:500; font-size:15px; }}
.preview {{ display:block; font-size:13px; color:var(--text2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

.meta {{ text-align:right; flex-shrink:0; }}
.time {{ display:block; font-size:11px; color:var(--text2); }}
.count {{
    display:inline-block; margin-top:4px;
    background:var(--accent); color:#fff;
    font-size:11px; padding:2px 8px; border-radius:10px;
}}

/* Chat body */
.chat-body {{ padding:12px; background:var(--bg); }}

.chat-title {{
    background:var(--card); padding:12px 16px; border-radius:8px;
    margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;
}}
.chat-title strong {{ font-size:16px; }}
.chat-title span {{ font-size:12px; color:var(--text2); }}

/* Pinned */
.pinned {{ margin-bottom:12px; }}
.pinned summary {{
    background:#fff3cd; color:#856404; padding:10px 14px;
    border-radius:8px; cursor:pointer; font-size:13px;
    list-style:none;
}}
.pinned summary::-webkit-details-marker {{ display:none; }}
@media(prefers-color-scheme:dark) {{
    .pinned summary {{ background:#3d3200; color:#ffc107; }}
}}
.pinned-list {{
    background:var(--card); border-radius:8px; margin-top:8px;
    padding:10px; max-height:250px; overflow-y:auto;
}}

/* Messages */
.messages {{ display:flex; flex-direction:column; gap:4px; }}

.date-sep {{ text-align:center; margin:16px 0; }}
.date-sep span {{
    background:var(--card); padding:4px 12px; border-radius:12px;
    font-size:11px; color:var(--text2);
}}

.msg {{
    max-width:80%; padding:8px 12px; border-radius:12px;
    background:var(--in); font-size:14px; word-wrap:break-word;
}}
.msg.out {{ background:var(--out); align-self:flex-end; }}

.msg .sender {{ font-size:12px; font-weight:600; color:var(--accent); margin-bottom:2px; }}
.msg .text {{ white-space:pre-wrap; line-height:1.4; }}
.msg .tm {{ font-size:10px; color:var(--text2); text-align:right; margin-top:2px; }}

.msg .quote {{
    border-left:3px solid var(--accent); padding:4px 8px; margin:4px 0;
    background:rgba(0,0,0,0.05); border-radius:0 6px 6px 0; font-size:12px;
}}
.msg .quote b {{ color:var(--accent); }}

.msg .file {{
    display:flex; gap:8px; align-items:center;
    background:rgba(0,0,0,0.05); padding:8px; border-radius:6px; margin-top:6px;
}}
.msg .file a {{ color:var(--accent); text-decoration:none; font-size:13px; }}

/* Mobile tweaks */
@media(max-width:600px) {{
    .chat-header {{ padding:10px 12px; gap:10px; }}
    .avatar {{ width:42px; height:42px; font-size:18px; }}
    .name {{ font-size:14px; }}
    .preview {{ font-size:12px; }}
    .msg {{ max-width:88%; }}
}}

/* Hide filtered */
.chat.hidden {{ display:none; }}

/* Search results */
.search-results {{
    max-height:300px; overflow-y:auto; margin-top:8px;
    background:var(--card); border-radius:8px; display:none;
}}
.search-results.active {{ display:block; }}
.search-result {{
    padding:10px 14px; border-bottom:1px solid var(--border);
    cursor:pointer; font-size:13px;
}}
.search-result:hover {{ background:var(--bg); }}
.search-result:last-child {{ border-bottom:none; }}
.search-result .chat-name {{ font-weight:600; color:var(--accent); }}
.search-result .msg-text {{ color:var(--text2); margin-top:4px; }}
.search-result .msg-text mark {{ background:#ffeb3b; padding:0 2px; border-radius:2px; }}
@media(prefers-color-scheme:dark) {{
    .search-result .msg-text mark {{ background:#5d4d00; color:#fff; }}
}}
.search-info {{
    padding:10px 14px; color:var(--text2); font-size:12px;
    border-bottom:1px solid var(--border);
}}

/* === DESKTOP: Two-panel layout with JS === */
body.desktop .list {{ display:flex; max-width:1200px; height:100vh; overflow:hidden; }}
body.desktop .sidebar {{
    width:360px; flex-shrink:0; overflow-y:auto;
    border-right:1px solid var(--border); background:var(--card);
}}
body.desktop .main {{
    flex:1; display:flex; flex-direction:column;
    background:var(--bg); overflow:hidden;
}}
body.desktop .main-placeholder {{
    flex:1; display:flex; align-items:center; justify-content:center;
    color:var(--text2); font-size:16px;
}}
body.desktop .main-chat {{
    display:none; flex-direction:column; height:100%; overflow:hidden;
}}
body.desktop .main-chat.active {{ display:flex; }}
body.desktop .main-chat .chat-title {{ margin:0; border-radius:0; border-bottom:1px solid var(--border); }}
body.desktop .main-chat .messages {{ flex:1; overflow-y:auto; padding:16px 40px; }}

body.desktop .chat {{ border-bottom:1px solid var(--border); }}
body.desktop .chat .chat-body {{ display:none !important; }}
body.desktop .chat[open] .chat-header {{ background:var(--hover, var(--accent)); }}
body.desktop .chat-header:hover {{ background:var(--border); }}
</style>
</head>
<body>

<div class="header">
    <h1>📦 VK Teams Export</h1>
    <small>📅 {export_date} · 💬 {len(chats)} чатов · 📨 {total_messages} сообщений</small>
</div>

<div class="search">
    <input type="text" id="search" placeholder="🔍 Поиск по чатам и сообщениям...">
    <div id="search-results" class="search-results"></div>
</div>

<div class="list" id="list">
    {chats_html}
</div>

<script>
(function() {{
    // Поиск по чатам И сообщениям
    var search = document.getElementById('search');
    var searchResults = document.getElementById('search-results');
    var chatEls = document.querySelectorAll('.chat');

    // Индексируем все сообщения для быстрого поиска
    var messageIndex = [];
    chatEls.forEach(function(chatEl, chatIdx) {{
        var chatName = chatEl.querySelector('.name');
        chatName = chatName ? chatName.textContent : 'Чат ' + chatIdx;

        var messages = chatEl.querySelectorAll('.msg');
        messages.forEach(function(msgEl, msgIdx) {{
            var textEl = msgEl.querySelector('.text');
            var text = textEl ? textEl.textContent : '';
            if (text) {{
                messageIndex.push({{
                    chatIdx: chatIdx,
                    chatName: chatName,
                    text: text,
                    msgIdx: msgIdx,
                    chatEl: chatEl,
                    msgEl: msgEl
                }});
            }}
        }});
    }});

    console.log('Indexed ' + messageIndex.length + ' messages for search');

    var searchTimeout = null;

    if (search) {{
        search.addEventListener('input', function() {{
            var q = this.value.toLowerCase().trim();

            // Отложенный поиск чтобы не лагало
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {{
                // Сначала фильтруем чаты по названию
                chatEls.forEach(function(c) {{
                    var name = c.querySelector('.name');
                    var t = name ? name.textContent.toLowerCase() : '';
                    c.classList.toggle('hidden', q.length >= 2 && t.indexOf(q) < 0);
                }});

                // Сквозной поиск по сообщениям
                if (q.length >= 2) {{
                    var results = [];
                    var seenChats = {{}};

                    for (var i = 0; i < messageIndex.length && results.length < 50; i++) {{
                        var item = messageIndex[i];
                        if (item.text.toLowerCase().indexOf(q) >= 0) {{
                            // Показываем чат в списке
                            item.chatEl.classList.remove('hidden');

                            // Добавляем в результаты (макс 3 на чат)
                            seenChats[item.chatIdx] = (seenChats[item.chatIdx] || 0) + 1;
                            if (seenChats[item.chatIdx] <= 3) {{
                                results.push(item);
                            }}
                        }}
                    }}

                    // Показываем результаты
                    if (results.length > 0) {{
                        var html = '<div class="search-info">Найдено совпадений: ' + results.length + (results.length >= 50 ? '+' : '') + '</div>';
                        results.forEach(function(r) {{
                            var snippet = r.text.substring(0, 150);
                            var highlighted = snippet.replace(new RegExp('(' + q.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi'), '<mark>$1</mark>');
                            html += '<div class="search-result" data-chat="' + r.chatIdx + '" data-msg="' + r.msgIdx + '">' +
                                '<div class="chat-name">' + r.chatName + '</div>' +
                                '<div class="msg-text">' + highlighted + '</div></div>';
                        }});
                        searchResults.innerHTML = html;
                        searchResults.classList.add('active');

                        // Клик по результату
                        searchResults.querySelectorAll('.search-result').forEach(function(el) {{
                            el.addEventListener('click', function() {{
                                var chatIdx = parseInt(this.dataset.chat);
                                var msgIdx = parseInt(this.dataset.msg);
                                var chat = chatEls[chatIdx];

                                // Открываем чат
                                chat.setAttribute('open', '');

                                // Скроллим к сообщению
                                setTimeout(function() {{
                                    var msgs = chat.querySelectorAll('.msg');
                                    if (msgs[msgIdx]) {{
                                        msgs[msgIdx].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                        msgs[msgIdx].style.background = '#ffeb3b';
                                        setTimeout(function() {{
                                            msgs[msgIdx].style.background = '';
                                        }}, 2000);
                                    }}
                                }}, 100);

                                searchResults.classList.remove('active');
                            }});
                        }});
                    }} else {{
                        searchResults.innerHTML = '<div class="search-info">Ничего не найдено</div>';
                        searchResults.classList.add('active');
                    }}
                }} else {{
                    searchResults.classList.remove('active');
                    searchResults.innerHTML = '';
                    // Показываем все чаты
                    chatEls.forEach(function(c) {{ c.classList.remove('hidden'); }});
                }}
            }}, 200);
        }});
    }}

    // Desktop: превращаем в двухпанельный интерфейс
    var isDesktop = window.innerWidth > 800;
    var desktopPanels = [];  // Для поиска на desktop

    if (isDesktop) {{
        document.body.classList.add('desktop');

        var list = document.getElementById('list');

        // Создаём sidebar и main
        var sidebar = document.createElement('div');
        sidebar.className = 'sidebar';

        var main = document.createElement('div');
        main.className = 'main';
        main.innerHTML = '<div class="main-placeholder">👈 Выберите чат</div>';

        // Переносим чаты в sidebar
        while (list.firstChild) {{
            sidebar.appendChild(list.firstChild);
        }}

        list.appendChild(sidebar);
        list.appendChild(main);

        // Создаём контент для каждого чата (используем оригинальные chatEls!)
        chatEls.forEach(function(chat, idx) {{
            var body = chat.querySelector('.chat-body');
            if (!body) return;

            // Создаём панель для main
            var panel = document.createElement('div');
            panel.className = 'main-chat';
            panel.dataset.idx = idx;
            panel.innerHTML = body.innerHTML;
            main.appendChild(panel);
            desktopPanels[idx] = panel;

            // Клик по чату
            var header = chat.querySelector('.chat-header');
            header.addEventListener('click', function(e) {{
                e.preventDefault();

                // Закрываем все
                chatEls.forEach(function(c) {{ c.removeAttribute('open'); }});
                main.querySelectorAll('.main-chat').forEach(function(p) {{ p.classList.remove('active'); }});
                var placeholder = main.querySelector('.main-placeholder');
                if (placeholder) placeholder.style.display = 'none';

                // Открываем выбранный
                chat.setAttribute('open', '');
                panel.classList.add('active');

                // Скролл вниз
                var msgs = panel.querySelector('.messages');
                if (msgs) msgs.scrollTop = msgs.scrollHeight;
            }});
        }});

        // Открываем первый чат
        if (chatEls.length > 0) {{
            chatEls[0].querySelector('.chat-header').click();
        }}

        // Обновляем обработчик клика для результатов поиска на desktop
        searchResults.addEventListener('click', function(e) {{
            var result = e.target.closest('.search-result');
            if (!result) return;

            var chatIdx = parseInt(result.dataset.chat);
            var msgIdx = parseInt(result.dataset.msg);
            var chat = chatEls[chatIdx];
            var panel = desktopPanels[chatIdx];

            if (chat && panel) {{
                // Закрываем все
                chatEls.forEach(function(c) {{ c.removeAttribute('open'); }});
                main.querySelectorAll('.main-chat').forEach(function(p) {{ p.classList.remove('active'); }});
                var placeholder = main.querySelector('.main-placeholder');
                if (placeholder) placeholder.style.display = 'none';

                // Открываем выбранный
                chat.setAttribute('open', '');
                panel.classList.add('active');

                // Скроллим к сообщению в панели
                setTimeout(function() {{
                    var msgs = panel.querySelectorAll('.msg');
                    if (msgs[msgIdx]) {{
                        msgs[msgIdx].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        msgs[msgIdx].style.background = '#ffeb3b';
                        setTimeout(function() {{
                            msgs[msgIdx].style.background = '';
                        }}, 2000);
                    }}
                }}, 100);

                searchResults.classList.remove('active');
            }}
        }});
    }}
}})();
</script>

</body>
</html>'''


def render_message(msg: dict, pinned: bool = False, chat_members: dict = None, chat_sn: str = "", is_personal: bool = False) -> str:
    """Рендер одного сообщения"""
    is_outgoing = msg.get("outgoing", False)

    sender_sn = (
        msg.get("chat", {}).get("sender") or
        msg.get("senderSn") or
        msg.get("sn") or
        msg.get("sender") or
        ""
    )

    if is_personal:
        sender_name = "Вы" if is_outgoing else chat_sn
    else:
        sender_name = msg.get("senderNick") or msg.get("friendly") or ""
        if chat_members and sender_sn:
            member_info = chat_members.get(sender_sn, {})
            sender_name = member_info.get("friendly") or member_info.get("name") or sender_name
        if not sender_name and sender_sn:
            sender_name = sender_sn

    sender = escape(sender_name or "?")
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
        url = escape(file.get("original_url", "#"))
        size = format_size(file.get("size"))
        icon = get_file_icon(file.get("mime", ""))
        content += f'<div class="file">{icon} <a href="{url}" target="_blank">{name}</a> <small>{size}</small></div>'

    cls = "msg out" if is_outgoing else "msg"
    sender_html = "" if is_outgoing or is_personal else f'<div class="sender">{sender}</div>'

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
