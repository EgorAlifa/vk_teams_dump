/**
 * VK Teams Chat Exporter v2.0
 *
 * Использование:
 * 1. Открой нужный чат в VK Teams (веб-версия)
 * 2. Открой DevTools (F12) -> Console
 * 3. Скопируй и вставь этот скрипт
 * 4. Запусти: await exportChat()
 *
 * Опции:
 * - exportChat() - экспорт текущего чата в JSON
 * - exportChat({ format: 'html' }) - экспорт в HTML с поиском
 * - exportChat({ maxMessages: 1000 }) - ограничить количество
 * - exportAllChats() - экспорт всех чатов (осторожно!)
 */

(function() {
    'use strict';

    const CONFIG = {
        messagesPerRequest: 50,
        delayBetweenRequests: 500, // мс между запросами
        maxMessages: Infinity,
        format: 'json', // 'json' или 'html'
        apiBase: 'https://u.myteam.vmailru.net/api/v139/rapi'
    };

    // Получаем aimsid из заголовков/localStorage
    function getAimsid() {
        // Пробуем найти в localStorage
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            const value = localStorage.getItem(key);
            if (value && value.includes('@') && value.includes('.')) {
                // Похоже на aimsid формата "XXX.XXX.XXX:email@domain"
                if (/^\d+\.\d+\.\d+:/.test(value)) {
                    return value;
                }
            }
        }

        // Пробуем из sessionStorage
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            const value = sessionStorage.getItem(key);
            if (value && /^\d+\.\d+\.\d+:/.test(value)) {
                return value;
            }
        }

        // Спрашиваем у пользователя
        return prompt(
            'Не удалось найти aimsid автоматически.\n\n' +
            'Найди его в Network tab -> Headers -> x-teams-aimsid\n' +
            'Формат: 010.XXXXXXXXX.XXXXXXXXX:your.email@domain.com'
        );
    }

    // Получаем текущий sn чата
    function getCurrentChatSn() {
        // Из URL hash
        const hashMatch = window.location.hash.match(/sn=([^&]+)/);
        if (hashMatch) return decodeURIComponent(hashMatch[1]);

        // Из URL path
        const url = window.location.href;
        const chatMatch = url.match(/(\d+@chat\.agent)/);
        if (chatMatch) return chatMatch[1];

        // Ищем в DOM
        const chatElements = document.querySelectorAll('[class*="chat"]');
        for (const el of chatElements) {
            const sn = el.getAttribute('data-sn') || el.getAttribute('data-chat-id');
            if (sn && sn.includes('@')) return sn;
        }

        return prompt(
            'Не удалось определить ID чата.\n\n' +
            'Найди его в Network tab -> Payload -> params.sn\n' +
            'Формат: 687589145@chat.agent или user@domain.com'
        );
    }

    // Генерация уникального reqId
    function generateReqId() {
        return `${Math.floor(Math.random() * 10000)}-${Date.now()}`;
    }

    // Запрос истории чата
    async function fetchHistory(aimsid, sn, fromMsgId = null, count = -CONFIG.messagesPerRequest) {
        const params = {
            sn: sn,
            count: count,
            lang: 'ru',
            mentions: { resolve: true },
            patchVersion: '1'
        };

        if (fromMsgId) {
            params.fromMsgId = fromMsgId;
        }

        const body = {
            reqId: generateReqId(),
            aimsid: aimsid,
            params: params
        };

        const response = await fetch(`${CONFIG.apiBase}/getHistory`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'x-teams-aimsid': aimsid
            },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        return response.json();
    }

    // Получаем список чатов
    async function fetchChatList(aimsid) {
        const body = {
            reqId: generateReqId(),
            aimsid: aimsid,
            params: { lang: 'ru' }
        };

        const response = await fetch(`${CONFIG.apiBase}/getContactList`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'x-teams-aimsid': aimsid
            },
            body: JSON.stringify(body)
        });

        return response.json();
    }

    // Основная функция экспорта одного чата
    async function exportChat(options = {}) {
        const config = { ...CONFIG, ...options };

        console.log('🚀 VK Teams Exporter v2.0');
        console.log('========================\n');

        const aimsid = options.aimsid || getAimsid();
        if (!aimsid) {
            console.error('❌ aimsid не указан');
            return null;
        }
        console.log('✅ aimsid получен');

        const chatSn = options.sn || options.chatId || getCurrentChatSn();
        if (!chatSn) {
            console.error('❌ ID чата не указан');
            return null;
        }
        console.log(`📱 Чат: ${chatSn}\n`);

        const allMessages = [];
        const pinnedMessages = [];
        let fromMsgId = null;
        let hasMore = true;
        let requestCount = 0;
        let chatInfo = null;

        while (hasMore && allMessages.length < config.maxMessages) {
            requestCount++;
            process.stdout ? null : console.log(`📥 Запрос #${requestCount} | Сообщений: ${allMessages.length}`);

            try {
                const data = await fetchHistory(aimsid, chatSn, fromMsgId);

                if (data.status?.code !== 20000) {
                    console.error('❌ Ошибка API:', data.status);
                    break;
                }

                const results = data.results;

                // Сохраняем закрепленные сообщения (один раз)
                if (requestCount === 1 && results.pinned) {
                    pinnedMessages.push(...results.pinned);
                    console.log(`📌 Закрепленных: ${results.pinned.length}`);
                }

                // Сохраняем информацию о чате из первого сообщения
                if (!chatInfo && results.messages?.length > 0) {
                    chatInfo = {
                        sn: chatSn,
                        name: results.messages[0]?.chat?.name || chatSn
                    };
                }

                const messages = results.messages || [];

                if (messages.length === 0) {
                    hasMore = false;
                    console.log('\n✅ Достигнуто начало истории');
                    break;
                }

                allMessages.push(...messages);
                console.log(`📥 Запрос #${requestCount} | Загружено: ${allMessages.length}`);

                // Используем olderMsgId для следующего запроса
                if (results.olderMsgId) {
                    fromMsgId = results.olderMsgId;
                } else {
                    hasMore = false;
                }

                // Если вернулось меньше сообщений чем запрашивали - это конец
                if (messages.length < Math.abs(config.messagesPerRequest)) {
                    hasMore = false;
                }

                // Пауза между запросами
                await sleep(config.delayBetweenRequests);

            } catch (error) {
                console.error('❌ Ошибка:', error.message);
                // Пробуем продолжить после паузы
                await sleep(2000);
                if (requestCount > 3 && allMessages.length === 0) {
                    break;
                }
            }
        }

        // Сортируем по времени (старые первые)
        allMessages.sort((a, b) => a.time - b.time);

        console.log(`\n${'='.repeat(40)}`);
        console.log(`✅ Экспорт завершён!`);
        console.log(`📊 Всего сообщений: ${allMessages.length}`);
        console.log(`📌 Закреплённых: ${pinnedMessages.length}`);

        const exportData = {
            exportDate: new Date().toISOString(),
            chatSn: chatSn,
            chatName: chatInfo?.name || chatSn,
            totalMessages: allMessages.length,
            pinnedMessages: pinnedMessages,
            messages: allMessages
        };

        // Сохраняем файл
        if (config.format === 'html') {
            downloadAsHtml(exportData);
        } else {
            downloadAsJson(exportData);
        }

        // Сохраняем в глобальную переменную для доступа
        window.lastExport = exportData;
        console.log('\n💡 Данные также доступны в window.lastExport');

        return exportData;
    }

    // Экспорт всех чатов
    async function exportAllChats(options = {}) {
        const config = { ...CONFIG, ...options };

        console.log('🚀 Экспорт ВСЕХ чатов');
        console.log('⚠️  Это может занять много времени!\n');

        const aimsid = options.aimsid || getAimsid();
        if (!aimsid) return null;

        // Получаем список чатов
        console.log('📋 Загружаем список чатов...');
        const chatListData = await fetchChatList(aimsid);

        if (!chatListData.results?.contacts) {
            console.error('❌ Не удалось получить список чатов');
            return null;
        }

        const chats = chatListData.results.contacts;
        console.log(`📱 Найдено чатов: ${chats.length}\n`);

        const allExports = [];

        for (let i = 0; i < chats.length; i++) {
            const chat = chats[i];
            const sn = chat.sn || chat.aimId;
            const name = chat.friendly || chat.nick || sn;

            console.log(`\n[${ i + 1}/${chats.length}] 💬 ${name}`);

            try {
                const exportData = await exportChat({
                    ...config,
                    aimsid: aimsid,
                    sn: sn,
                    format: 'none' // Не скачиваем каждый отдельно
                });

                if (exportData) {
                    allExports.push(exportData);
                }

                // Пауза между чатами
                await sleep(1000);

            } catch (error) {
                console.error(`   ❌ Ошибка: ${error.message}`);
            }
        }

        // Сохраняем всё в один файл
        const fullExport = {
            exportDate: new Date().toISOString(),
            totalChats: allExports.length,
            chats: allExports
        };

        downloadAsJson(fullExport, 'vkteams_all_chats');
        window.allChatsExport = fullExport;

        console.log(`\n${'='.repeat(40)}`);
        console.log(`✅ Экспорт всех чатов завершён!`);
        console.log(`📊 Чатов: ${allExports.length}`);

        return fullExport;
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    // Скачивание JSON
    function downloadAsJson(data, customName = null) {
        const json = JSON.stringify(data, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const chatName = customName || data.chatName || data.chatSn || 'export';
        const safeName = String(chatName).replace(/[^a-zA-Zа-яА-Я0-9_-]/g, '_').substring(0, 50);
        const filename = `vkteams_${safeName}_${new Date().toISOString().slice(0, 10)}.json`;

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        URL.revokeObjectURL(url);
        console.log(`💾 Сохранено: ${filename}`);
    }

    // Скачивание HTML
    function downloadAsHtml(data) {
        const chatName = data.chatName || data.chatSn || 'Чат';

        const messagesHtml = data.messages.map(msg => renderMessage(msg)).join('\n');
        const pinnedHtml = data.pinnedMessages?.length
            ? `<div class="pinned-section">
                <h2>📌 Закреплённые сообщения</h2>
                ${data.pinnedMessages.map(msg => renderMessage(msg, true)).join('\n')}
               </div>`
            : '';

        const html = `<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(chatName)} - VK Teams Export</title>
    <style>
        :root {
            --bg: #f0f2f5;
            --card: #ffffff;
            --text: #1a1a1a;
            --text-secondary: #65676b;
            --accent: #0077ff;
            --border: #e4e6eb;
            --outgoing-bg: #e7f3ff;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #18191a;
                --card: #242526;
                --text: #e4e6eb;
                --text-secondary: #b0b3b8;
                --accent: #4599ff;
                --border: #3e4042;
                --outgoing-bg: #263951;
            }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: var(--card);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        h1 {
            font-size: 24px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .meta {
            color: var(--text-secondary);
            font-size: 14px;
        }
        .meta span { margin-right: 20px; }
        .search-box {
            position: sticky;
            top: 0;
            z-index: 100;
            background: var(--bg);
            padding: 12px 0;
        }
        .search-box input {
            width: 100%;
            padding: 12px 20px;
            border: 2px solid var(--border);
            border-radius: 24px;
            font-size: 15px;
            background: var(--card);
            color: var(--text);
            outline: none;
            transition: border-color 0.2s;
        }
        .search-box input:focus {
            border-color: var(--accent);
        }
        .pinned-section {
            background: var(--card);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }
        .pinned-section h2 {
            font-size: 16px;
            margin-bottom: 12px;
            color: var(--text-secondary);
        }
        .message {
            background: var(--card);
            padding: 14px 18px;
            margin: 6px 0;
            border-radius: 12px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: opacity 0.2s;
        }
        .message.outgoing {
            background: var(--outgoing-bg);
            margin-left: 40px;
        }
        .message.pinned {
            border-left: 3px solid #ffc107;
        }
        .message.hidden { display: none; }
        .msg-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .sender {
            font-weight: 600;
            color: var(--accent);
            font-size: 14px;
        }
        .time {
            font-size: 12px;
            color: var(--text-secondary);
        }
        .text {
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 15px;
        }
        .quote {
            border-left: 3px solid var(--accent);
            padding: 8px 12px;
            margin: 8px 0;
            background: var(--bg);
            border-radius: 0 8px 8px 0;
            font-size: 14px;
        }
        .quote-sender {
            font-weight: 600;
            color: var(--accent);
            font-size: 13px;
        }
        .quote-text {
            color: var(--text-secondary);
            margin-top: 4px;
        }
        .file {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--bg);
            padding: 10px 14px;
            border-radius: 8px;
            margin: 8px 4px 0 0;
            font-size: 14px;
        }
        .file a {
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
        }
        .file a:hover { text-decoration: underline; }
        .file-size {
            color: var(--text-secondary);
            font-size: 12px;
        }
        .forward {
            border-left: 3px solid #9c27b0;
            padding: 8px 12px;
            margin: 8px 0;
            background: var(--bg);
            border-radius: 0 8px 8px 0;
        }
        .forward-label {
            font-size: 12px;
            color: #9c27b0;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .stats {
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 14px;
        }
        .jump-top {
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--accent);
            color: white;
            border: none;
            font-size: 20px;
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            display: none;
        }
        .jump-top.visible { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>💬 ${escapeHtml(chatName)}</h1>
            <div class="meta">
                <span>📅 Экспорт: ${new Date(data.exportDate).toLocaleString('ru-RU')}</span>
                <span>📊 Сообщений: ${data.totalMessages}</span>
                ${data.pinnedMessages?.length ? `<span>📌 Закреплено: ${data.pinnedMessages.length}</span>` : ''}
            </div>
        </header>

        <div class="search-box">
            <input type="text" id="search" placeholder="🔍 Поиск по сообщениям..." autocomplete="off">
        </div>

        ${pinnedHtml}

        <div id="messages">
            ${messagesHtml}
        </div>

        <div class="stats">
            Конец истории · ${data.totalMessages} сообщений
        </div>
    </div>

    <button class="jump-top" id="jumpTop" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>

    <script>
        // Поиск
        const searchInput = document.getElementById('search');
        const messages = document.querySelectorAll('.message:not(.pinned)');
        let searchTimeout;

        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const q = e.target.value.toLowerCase().trim();
                messages.forEach(msg => {
                    const text = msg.textContent.toLowerCase();
                    msg.classList.toggle('hidden', q && !text.includes(q));
                });
            }, 200);
        });

        // Кнопка наверх
        const jumpBtn = document.getElementById('jumpTop');
        window.addEventListener('scroll', () => {
            jumpBtn.classList.toggle('visible', window.scrollY > 500);
        });

        // Горячие клавиши
        document.addEventListener('keydown', (e) => {
            if (e.key === '/' && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
            }
            if (e.key === 'Escape') {
                searchInput.value = '';
                searchInput.dispatchEvent(new Event('input'));
                searchInput.blur();
            }
        });
    </script>
</body>
</html>`;

        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const safeName = String(chatName).replace(/[^a-zA-Zа-яА-Я0-9_-]/g, '_').substring(0, 50);
        const filename = `vkteams_${safeName}_${new Date().toISOString().slice(0, 10)}.html`;

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        URL.revokeObjectURL(url);
        console.log(`💾 Сохранено: ${filename}`);
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatTime(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toLocaleString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    function formatSize(bytes) {
        if (!bytes) return '';
        bytes = parseInt(bytes, 10);
        if (bytes < 1024) return bytes + ' Б';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ';
        return (bytes / (1024 * 1024)).toFixed(1) + ' МБ';
    }

    function renderMessage(msg, isPinned = false) {
        const isOutgoing = msg.outgoing === true;
        const sender = msg.chat?.sender || msg.senderNick || msg.sender || 'Unknown';
        const time = formatTime(msg.time);

        let contentHtml = '';

        // Обрабатываем parts
        if (msg.parts && msg.parts.length > 0) {
            for (const part of msg.parts) {
                if (part.mediaType === 'text') {
                    contentHtml += `<div class="text">${escapeHtml(part.captionedContent?.caption || part.text || '')}</div>`;
                }
                if (part.mediaType === 'quote') {
                    contentHtml += `
                        <div class="quote">
                            <div class="quote-sender">↩️ ${escapeHtml(part.sn || '')}</div>
                            <div class="quote-text">${escapeHtml(truncate(part.text, 200))}</div>
                        </div>`;
                }
                if (part.mediaType === 'forward') {
                    contentHtml += `
                        <div class="forward">
                            <div class="forward-label">⤵️ Переслано от ${escapeHtml(part.sn || '')}</div>
                            <div class="text">${escapeHtml(truncate(part.captionedContent?.caption || part.text || '', 300))}</div>
                        </div>`;
                }
            }
        } else if (msg.text) {
            contentHtml += `<div class="text">${escapeHtml(msg.text)}</div>`;
        }

        // Файлы
        let filesHtml = '';
        if (msg.filesharing && msg.filesharing.length > 0) {
            for (const file of msg.filesharing) {
                const icon = getFileIcon(file.mime);
                filesHtml += `
                    <div class="file">
                        ${icon}
                        <a href="${escapeHtml(file.original_url)}" target="_blank" rel="noopener">${escapeHtml(file.name || 'файл')}</a>
                        <span class="file-size">${formatSize(file.size)}</span>
                    </div>`;
            }
        }

        const classes = ['message'];
        if (isOutgoing) classes.push('outgoing');
        if (isPinned) classes.push('pinned');

        return `
        <div class="${classes.join(' ')}" data-msgid="${msg.msgId}" data-time="${msg.time}">
            <div class="msg-header">
                <span class="sender">${escapeHtml(sender)}</span>
                <span class="time">${time}</span>
            </div>
            ${contentHtml}
            ${filesHtml}
        </div>`;
    }

    function truncate(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    function getFileIcon(mime) {
        if (!mime) return '📎';
        if (mime.startsWith('image/')) return '🖼️';
        if (mime.startsWith('video/')) return '🎬';
        if (mime.startsWith('audio/')) return '🎵';
        if (mime.includes('pdf')) return '📄';
        if (mime.includes('zip') || mime.includes('rar') || mime.includes('7z')) return '📦';
        if (mime.includes('word') || mime.includes('document')) return '📝';
        if (mime.includes('excel') || mime.includes('spreadsheet')) return '📊';
        if (mime.includes('presentation') || mime.includes('powerpoint')) return '📽️';
        return '📎';
    }

    // Экспортируем функции глобально
    window.exportChat = exportChat;
    window.exportAllChats = exportAllChats;
    window.VKTeamsExporter = {
        exportChat,
        exportAllChats,
        fetchHistory,
        fetchChatList,
        getAimsid,
        getCurrentChatSn,
        CONFIG
    };

    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║           VK Teams Chat Exporter v2.0 загружен!               ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  📥 Экспорт текущего чата:                                    ║
║     await exportChat()                                        ║
║     await exportChat({ format: 'html' })                      ║
║                                                               ║
║  📥 С параметрами:                                            ║
║     await exportChat({ sn: '12345@chat.agent' })              ║
║     await exportChat({ maxMessages: 500 })                    ║
║                                                               ║
║  📥 Экспорт ВСЕХ чатов:                                       ║
║     await exportAllChats()                                    ║
║                                                               ║
║  💡 Подсказки:                                                ║
║  • aimsid ищи в Network → Headers → x-teams-aimsid            ║
║  • sn чата ищи в Network → Payload → params.sn                ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    `);

})();
