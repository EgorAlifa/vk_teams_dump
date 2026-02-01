"""
Форматирование экспорта VK Teams в различные форматы
Стиль VK Teams - синий/белый
"""

import json
from datetime import datetime
from html import escape


def format_as_json(data: dict) -> str:
    """Форматирование в JSON"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_as_html(data: dict) -> str:
    """
    Форматирование в HTML - стиль VK Teams
    Синий/белый дизайн, вкладки поиска, поиск внутри чата
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
        last_sender = ""
        if last_msg:
            parts = last_msg.get("parts", [])
            for p in parts:
                if p.get("mediaType") == "text":
                    last_text = p.get("text", "")[:60]
                    break
            if not last_text:
                last_text = last_msg.get("text", "")[:60]
            last_sender = last_msg.get("senderNick") or last_msg.get("friendly") or ""
        last_text = escape(last_text) if last_text else ""
        last_sender = escape(last_sender[:20]) if last_sender else ""

        # Время последнего сообщения
        last_time = ""
        if last_msg.get("time"):
            last_time = datetime.fromtimestamp(last_msg["time"]).strftime("%d.%m")

        avatar_letter = chat_name[0].upper() if chat_name else "?"

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

        # Превью
        preview = f'<b>{last_sender}:</b> {last_text}' if last_sender and not is_personal else last_text

        chats_html += f'''
<div class="chat-item" data-idx="{idx}">
    <div class="avatar">{avatar_letter}</div>
    <div class="chat-info">
        <div class="chat-name">{chat_name[:35]}{"…" if len(chat_name) > 35 else ""}</div>
        <div class="chat-preview">{preview if preview else "..."}</div>
    </div>
    <div class="chat-meta">
        <span class="chat-time">{last_time}</span>
        <span class="chat-count">{msg_count}</span>
    </div>
</div>
<div class="chat-content" data-idx="{idx}">
    <div class="content-header">
        <button class="back-btn">←</button>
        <div class="avatar sm">{avatar_letter}</div>
        <div class="content-title">
            <div class="title-name">{chat_name}</div>
            <div class="title-sub">{msg_count} сообщений</div>
        </div>
        <button class="search-btn">🔍</button>
    </div>
    <div class="content-search">
        <input type="text" placeholder="Поиск в чате...">
        <span class="search-nav">
            <span class="search-count"></span>
            <button class="prev-btn">↑</button>
            <button class="next-btn">↓</button>
        </span>
        <button class="close-btn">✕</button>
    </div>
    {pinned_html}
    <div class="messages">{messages_html}</div>
</div>
'''

    return f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5">
<title>VK Teams Export</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
:root {{
    --bg: #f0f2f5;
    --card: #ffffff;
    --text: #19191a;
    --text2: #818c99;
    --accent: #0077ff;
    --accent-light: #e3f0ff;
    --border: #dce1e6;
    --hover: #f5f7fa;
    --out: #cce4ff;
    --highlight: #fff3a8;
}}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    height: 100vh;
    overflow: hidden;
}}

/* === LAYOUT === */
.container {{
    display: flex;
    height: 100vh;
    max-width: 1400px;
    margin: 0 auto;
    background: var(--card);
    box-shadow: 0 0 20px rgba(0,0,0,0.08);
}}

/* === SIDEBAR === */
.sidebar {{
    width: 360px;
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
}}

.header {{
    padding: 14px 16px;
    background: var(--accent);
    color: #fff;
}}
.header h1 {{ font-size: 15px; font-weight: 600; }}
.header small {{ font-size: 11px; opacity: 0.85; }}

/* Search */
.search-box {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
}}
.search-input {{
    width: 100%;
    padding: 9px 12px 9px 34px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 14px;
    background: var(--bg) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23818c99' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E") 10px center no-repeat;
    outline: none;
}}
.search-input:focus {{ border-color: var(--accent); }}

/* Tabs */
.tabs {{
    display: flex;
    border-bottom: 1px solid var(--border);
}}
.tab {{
    flex: 1;
    padding: 11px 12px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text2);
    text-align: center;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
}}
.tab:hover {{ color: var(--accent); }}
.tab.active {{
    color: var(--accent);
    border-bottom-color: var(--accent);
}}

/* Stats */
.stats {{
    padding: 8px 16px;
    font-size: 12px;
    color: var(--text2);
    background: var(--bg);
    border-bottom: 1px solid var(--border);
}}

/* Chat list */
.chat-list {{
    flex: 1;
    overflow-y: auto;
}}
.chat-item {{
    display: flex;
    align-items: center;
    padding: 10px 14px;
    gap: 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
}}
.chat-item:hover {{ background: var(--hover); }}
.chat-item.active {{ background: var(--accent-light); }}
.chat-item.hidden {{ display: none; }}

.avatar {{
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 17px;
    font-weight: 500;
    flex-shrink: 0;
}}
.avatar.sm {{ width: 36px; height: 36px; font-size: 14px; }}

.chat-info {{ flex: 1; min-width: 0; }}
.chat-name {{
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.chat-preview {{
    font-size: 13px;
    color: var(--text2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.chat-preview b {{ color: var(--text); font-weight: 500; }}

.chat-meta {{ text-align: right; flex-shrink: 0; }}
.chat-time {{ display: block; font-size: 12px; color: var(--text2); }}
.chat-count {{
    display: inline-block;
    margin-top: 4px;
    background: var(--accent);
    color: #fff;
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 10px;
}}

/* === SEARCH RESULTS === */
.search-results {{
    flex: 1;
    overflow-y: auto;
    display: none;
}}
.search-results.active {{ display: block; }}
.search-result {{
    display: flex;
    align-items: flex-start;
    padding: 10px 14px;
    gap: 12px;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
}}
.search-result:hover {{ background: var(--hover); }}
.result-info {{ flex: 1; min-width: 0; }}
.result-chat {{ font-size: 14px; font-weight: 500; }}
.result-sender {{ font-size: 13px; color: var(--accent); font-weight: 500; }}
.result-text {{
    font-size: 13px;
    color: var(--text2);
    margin-top: 3px;
    line-height: 1.35;
}}
.result-text mark {{
    background: var(--accent-light);
    color: var(--accent);
    padding: 0 2px;
    border-radius: 2px;
}}
.result-time {{ font-size: 12px; color: var(--text2); }}

/* === MAIN CONTENT === */
.main {{
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--bg);
}}
.main-placeholder {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text2);
}}

/* Chat content */
.chat-content {{ display: none; flex-direction: column; height: 100%; }}
.chat-content.active {{ display: flex; }}

.content-header {{
    display: flex;
    align-items: center;
    padding: 10px 14px;
    gap: 12px;
    background: var(--card);
    border-bottom: 1px solid var(--border);
}}
.back-btn {{
    display: none;
    width: 32px;
    height: 32px;
    border: none;
    background: var(--bg);
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
}}
.content-title {{ flex: 1; }}
.title-name {{ font-size: 15px; font-weight: 600; }}
.title-sub {{ font-size: 12px; color: var(--text2); }}
.search-btn {{
    width: 36px;
    height: 36px;
    border: none;
    background: transparent;
    cursor: pointer;
    font-size: 18px;
    border-radius: 6px;
}}
.search-btn:hover {{ background: var(--bg); }}

/* Content search */
.content-search {{
    display: none;
    align-items: center;
    padding: 8px 14px;
    gap: 8px;
    background: var(--card);
    border-bottom: 1px solid var(--border);
}}
.content-search.active {{ display: flex; }}
.content-search input {{
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
    outline: none;
}}
.content-search input:focus {{ border-color: var(--accent); }}
.search-nav {{ display: flex; align-items: center; gap: 4px; }}
.search-count {{ font-size: 12px; color: var(--text2); min-width: 60px; text-align: center; }}
.content-search button {{
    width: 28px;
    height: 28px;
    border: 1px solid var(--border);
    background: var(--card);
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
}}
.content-search button:hover {{ background: var(--bg); }}
.close-btn {{ width: 32px !important; }}

/* Pinned */
.pinned {{ margin: 12px 16px; background: var(--card); border-radius: 8px; }}
.pinned summary {{
    padding: 10px 14px;
    cursor: pointer;
    font-size: 13px;
    color: var(--accent);
    list-style: none;
}}
.pinned summary::-webkit-details-marker {{ display: none; }}
.pinned-list {{ padding: 8px; max-height: 180px; overflow-y: auto; }}

/* Messages */
.messages {{
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}}
.date-sep {{ text-align: center; margin: 14px 0; }}
.date-sep span {{
    background: rgba(0,0,0,0.08);
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    color: var(--text2);
}}

.msg {{
    max-width: 70%;
    padding: 9px 12px;
    border-radius: 14px;
    font-size: 14px;
    line-height: 1.4;
    background: var(--card);
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
    word-wrap: break-word;
}}
.msg.out {{
    background: var(--out);
    align-self: flex-end;
    border-bottom-right-radius: 4px;
}}
.msg:not(.out) {{
    align-self: flex-start;
    border-bottom-left-radius: 4px;
}}
.msg.highlight {{ background: var(--highlight) !important; }}

.msg .sender {{ font-size: 12px; font-weight: 600; color: var(--accent); margin-bottom: 3px; }}
.msg .text {{ white-space: pre-wrap; }}
.msg .tm {{ font-size: 11px; color: var(--text2); text-align: right; margin-top: 3px; }}

.msg .quote {{
    border-left: 3px solid var(--accent);
    padding: 5px 10px;
    margin: 5px 0;
    background: rgba(0,119,255,0.08);
    border-radius: 0 8px 8px 0;
    font-size: 13px;
}}
.msg .quote b {{ color: var(--accent); }}

.msg .file {{
    display: flex;
    gap: 8px;
    align-items: center;
    background: rgba(0,0,0,0.04);
    padding: 8px 10px;
    border-radius: 8px;
    margin-top: 6px;
}}
.msg .file a {{ color: var(--accent); text-decoration: none; font-size: 13px; }}
.msg .file a:hover {{ text-decoration: underline; }}

/* === MOBILE === */
@media (max-width: 768px) {{
    .container {{ flex-direction: column; }}
    .sidebar {{ width: 100%; height: 100%; }}
    .sidebar.hidden {{ display: none; }}
    .main {{ display: none; width: 100%; height: 100%; }}
    .main.active {{ display: flex; }}
    .back-btn {{ display: flex; align-items: center; justify-content: center; }}
    .msg {{ max-width: 85%; }}
    .messages {{ padding: 12px; }}
}}
</style>
</head>
<body>

<div class="container">
    <div class="sidebar" id="sidebar">
        <div class="header">
            <h1>📦 VK Teams Export</h1>
            <small>📅 {export_date} · 💬 {len(chats)} чатов · 📨 {total_messages} сообщений</small>
        </div>
        <div class="search-box">
            <input type="text" class="search-input" id="searchInput" placeholder="Поиск...">
        </div>
        <div class="tabs">
            <div class="tab active" data-tab="chats">Контакты и группы</div>
            <div class="tab" data-tab="messages">Сообщения</div>
        </div>
        <div class="stats" id="stats">Контактов и групп: {len(chats)}</div>
        <div class="chat-list" id="chatList">{chats_html}</div>
        <div class="search-results" id="searchResults"></div>
    </div>
    <div class="main" id="main">
        <div class="main-placeholder">👈 Выберите чат</div>
    </div>
</div>

<script>
(function() {{
    var sidebar = document.getElementById('sidebar');
    var main = document.getElementById('main');
    var searchInput = document.getElementById('searchInput');
    var chatList = document.getElementById('chatList');
    var searchResults = document.getElementById('searchResults');
    var stats = document.getElementById('stats');
    var tabs = document.querySelectorAll('.tab');
    var chatItems = document.querySelectorAll('.chat-item');
    var chatContents = document.querySelectorAll('.chat-content');
    var currentTab = 'chats';
    var isMobile = window.innerWidth <= 768;

    // Index messages
    var msgIndex = [];
    chatContents.forEach(function(c, ci) {{
        var item = chatItems[ci];
        var name = item ? item.querySelector('.chat-name').textContent : '';
        c.querySelectorAll('.msg').forEach(function(m, mi) {{
            var t = m.querySelector('.text');
            var s = m.querySelector('.sender');
            if (t && t.textContent) {{
                msgIndex.push({{ ci: ci, mi: mi, name: name, text: t.textContent, sender: s ? s.textContent : '' }});
            }}
        }});
    }});

    // Tabs
    tabs.forEach(function(tab) {{
        tab.onclick = function() {{
            tabs.forEach(function(t) {{ t.classList.remove('active'); }});
            this.classList.add('active');
            currentTab = this.dataset.tab;
            doSearch();
        }};
    }});

    // Search
    var st;
    searchInput.oninput = function() {{ clearTimeout(st); st = setTimeout(doSearch, 150); }};

    function doSearch() {{
        var q = searchInput.value.toLowerCase().trim();
        if (currentTab === 'chats') {{
            chatList.style.display = '';
            searchResults.classList.remove('active');
            var vis = 0;
            chatItems.forEach(function(it) {{
                var n = it.querySelector('.chat-name').textContent.toLowerCase();
                var show = !q || n.indexOf(q) >= 0;
                it.classList.toggle('hidden', !show);
                if (show) vis++;
            }});
            stats.textContent = 'Контактов и групп: ' + vis;
        }} else {{
            chatList.style.display = 'none';
            searchResults.classList.add('active');
            if (q.length < 2) {{
                searchResults.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text2)">Введите минимум 2 символа</div>';
                stats.textContent = 'Сообщений: 0';
                return;
            }}
            var res = [];
            for (var i = 0; i < msgIndex.length && res.length < 100; i++) {{
                if (msgIndex[i].text.toLowerCase().indexOf(q) >= 0) res.push(msgIndex[i]);
            }}
            stats.textContent = 'Сообщений: ' + res.length + (res.length >= 100 ? '+' : '');
            if (!res.length) {{
                searchResults.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text2)">Ничего не найдено</div>';
                return;
            }}
            var h = '';
            res.forEach(function(r) {{
                var snip = r.text.substring(0, 180);
                var hl = snip.replace(new RegExp('(' + q.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi'), '<mark>$1</mark>');
                h += '<div class="search-result" data-ci="' + r.ci + '" data-mi="' + r.mi + '">' +
                    '<div class="avatar sm">' + (r.name[0] || '?').toUpperCase() + '</div>' +
                    '<div class="result-info"><div class="result-chat">' + r.name + '</div>' +
                    (r.sender ? '<div class="result-sender">' + r.sender + '</div>' : '') +
                    '<div class="result-text">' + hl + '</div></div></div>';
            }});
            searchResults.innerHTML = h;
            searchResults.querySelectorAll('.search-result').forEach(function(el) {{
                el.onclick = function() {{
                    openChat(parseInt(this.dataset.ci), parseInt(this.dataset.mi));
                }};
            }});
        }}
    }}

    // Chat click
    chatItems.forEach(function(it, i) {{
        it.onclick = function() {{ openChat(i); }};
    }});

    function openChat(ci, scrollTo) {{
        chatItems.forEach(function(c) {{ c.classList.remove('active'); }});
        if (chatItems[ci]) chatItems[ci].classList.add('active');
        chatContents.forEach(function(c) {{ c.classList.remove('active'); }});
        var content = chatContents[ci];
        if (content) {{
            content.classList.add('active');
            main.querySelector('.main-placeholder').style.display = 'none';
            if (content.parentNode !== main) main.appendChild(content);
        }}
        if (isMobile) {{
            sidebar.classList.add('hidden');
            main.classList.add('active');
        }}
        if (scrollTo !== undefined && content) {{
            setTimeout(function() {{
                var msgs = content.querySelectorAll('.msg');
                if (msgs[scrollTo]) {{
                    msgs[scrollTo].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    msgs[scrollTo].classList.add('highlight');
                    setTimeout(function() {{ msgs[scrollTo].classList.remove('highlight'); }}, 2500);
                }}
            }}, 100);
        }} else if (content) {{
            var m = content.querySelector('.messages');
            if (m) m.scrollTop = m.scrollHeight;
        }}
    }}

    // Back button
    document.addEventListener('click', function(e) {{
        if (e.target.classList.contains('back-btn')) {{
            chatContents.forEach(function(c) {{ c.classList.remove('active'); }});
            main.querySelector('.main-placeholder').style.display = '';
            sidebar.classList.remove('hidden');
            main.classList.remove('active');
        }}
    }});

    // Search in chat
    document.addEventListener('click', function(e) {{
        if (e.target.classList.contains('search-btn')) {{
            var bar = e.target.closest('.chat-content').querySelector('.content-search');
            bar.classList.toggle('active');
            if (bar.classList.contains('active')) bar.querySelector('input').focus();
        }}
        if (e.target.classList.contains('close-btn')) {{
            var bar = e.target.closest('.content-search');
            bar.classList.remove('active');
            bar.querySelector('input').value = '';
            bar.closest('.chat-content').querySelectorAll('.msg.highlight').forEach(function(m) {{
                m.classList.remove('highlight');
            }});
        }}
    }});

    document.addEventListener('input', function(e) {{
        if (!e.target.closest('.content-search')) return;
        var content = e.target.closest('.chat-content');
        var q = e.target.value.toLowerCase().trim();
        var msgs = content.querySelectorAll('.msg');
        var matches = [];
        msgs.forEach(function(m) {{
            m.classList.remove('highlight');
            var t = m.querySelector('.text');
            if (t && q.length >= 2 && t.textContent.toLowerCase().indexOf(q) >= 0) {{
                m.classList.add('highlight');
                matches.push(m);
            }}
        }});
        content.querySelector('.search-count').textContent = matches.length + ' найдено';
        content._matches = matches;
        content._idx = -1;
    }});

    document.addEventListener('click', function(e) {{
        var content = e.target.closest('.chat-content');
        if (!content || !content._matches || !content._matches.length) return;
        var m = content._matches;
        if (e.target.classList.contains('next-btn')) {{
            content._idx = (content._idx + 1) % m.length;
            m[content._idx].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
        if (e.target.classList.contains('prev-btn')) {{
            content._idx = content._idx <= 0 ? m.length - 1 : content._idx - 1;
            m[content._idx].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
    }});

    // Open first chat on desktop
    if (!isMobile && chatItems.length) openChat(0);
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
        sender_name = ""
    else:
        sender_name = msg.get("senderNick") or msg.get("friendly") or ""
        if chat_members and sender_sn:
            member_info = chat_members.get(sender_sn, {})
            sender_name = member_info.get("friendly") or member_info.get("name") or sender_name
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
        url = escape(file.get("original_url", "#"))
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
